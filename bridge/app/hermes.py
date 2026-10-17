"""Serial Hermes adapter that resumes the user's current conversation."""

import json
import os
import queue
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from .hermes_api import HermesRunsClient
from .conversations import bind_draft, message_route
from .process_utils import command_invocation
from .storage import add_message, get_setting, set_delivery, set_setting


SESSION_SETTING = "hermes_session_id"


def hermes_executable() -> str | None:
    found = shutil.which("hermes")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "bin" / "hermes.exe"
    return str(local) if local.is_file() else None


def latest_desktop_session_info(state_db: Path) -> dict | None:
    if not state_db.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{state_db.as_posix()}?mode=ro", uri=True, timeout=2) as db:
            row = db.execute(
                "SELECT id, title, last_activity_at FROM sessions WHERE source = 'desktop' "
                "AND COALESCE(archived, 0) = 0 AND COALESCE(hidden, 0) = 0 "
                "ORDER BY last_activity_at DESC LIMIT 1"
            ).fetchone()
        return {"id": row[0], "title": row[1], "last_activity_at": row[2]} if row else None
    except sqlite3.Error:
        return None


def latest_desktop_session(state_db: Path) -> str | None:
    info = latest_desktop_session_info(state_db)
    return info["id"] if info else None


def session_info(state_db: Path, session_id: str) -> dict | None:
    if not state_db.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{state_db.as_posix()}?mode=ro", uri=True, timeout=2) as db:
            row = db.execute(
                "SELECT id, title, last_activity_at FROM sessions WHERE id = ? "
                "AND COALESCE(archived, 0) = 0 AND COALESCE(hidden, 0) = 0 LIMIT 1",
                (session_id,),
            ).fetchone()
        return {"id": row[0], "title": row[1], "last_activity_at": row[2]} if row else None
    except sqlite3.Error:
        return None


def parse_result(output: str) -> tuple[str, str | None]:
    """Extract only Hermes' final result; progress events may contain tool data."""
    for line in reversed(output.splitlines()):
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if event.get("type") == "result":
            if event.get("exit_code") != 0:
                raise RuntimeError("Hermes turn failed")
            answer = event.get("text")
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Hermes returned no text")
            session = event.get("session_id")
            return answer.strip(), session if isinstance(session, str) else None
    raise RuntimeError("Hermes did not return a final result")


class HermesWorker:
    source = "hermes"
    session_setting = SESSION_SETTING
    def __init__(self, database: Path, hermes_home: Path | None = None,
                 on_reply=None, on_error=None, on_approval=None,
                 api_client: HermesRunsClient | None = None):
        self.database = database
        self.hermes_home = hermes_home or Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
        self.executable = hermes_executable()
        self.on_reply = on_reply
        self.on_error = on_error
        self.on_approval = on_approval
        self.api_client = api_client
        self._jobs: queue.Queue[tuple[int, str, str | None] | None] = queue.Queue(maxsize=8)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None
        self._run_id: str | None = None
        self._last_run_session: str | None = None
        self._pending_approval: dict | None = None
        self._current_message_id: int | None = None
        self._queued_ids: set[int] = set()
        self._cancelled: set[int] = set()
        self._lock = threading.Lock()
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hermes-delivery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            process = self._process
        if process and process.poll() is None:
            process.terminate()
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=5)

    def snapshot(self) -> dict:
        current = self._preferred_session_info()
        with self._lock:
            return {"available": bool(self.executable or self.api_client), "pending": self._jobs.qsize(),
                    "running": self._process is not None or self._run_id is not None,
                    "last_error": self._last_error, "session": current,
                    "mode": "runs-api" if self.api_client else "cli",
                    "approval": dict(self._pending_approval) if self._pending_approval else None}

    def _preferred_session_info(self) -> dict | None:
        state_db = self.hermes_home / "state.db"
        desktop = latest_desktop_session_info(state_db)
        selected_id = get_setting(self.database, SESSION_SETTING)
        selected = session_info(state_db, selected_id) if selected_id else None
        if selected and desktop and selected["id"] != desktop["id"]:
            if (desktop["last_activity_at"] or 0) > (selected["last_activity_at"] or 0):
                return desktop
        return selected or desktop

    def pending_approval(self) -> dict | None:
        with self._lock:
            return dict(self._pending_approval) if self._pending_approval else None

    def approve(self, request_id: str, choice: str) -> bool:
        with self._lock:
            pending = self._pending_approval
            if not pending or pending["request_id"] != request_id or not self.api_client:
                return False
            run_id = pending["run_id"]
        self.api_client.approve(run_id, request_id, choice)
        with self._lock:
            if self._pending_approval and self._pending_approval["request_id"] == request_id:
                self._pending_approval = None
        return True

    def enqueue(self, message_id: int, text: str, *, new_session: bool = False) -> bool:
        if not (self.executable or self.api_client) or self._stop.is_set():
            return False
        preferred = None if new_session else self._preferred_session_info()
        session = preferred["id"] if preferred else None
        try:
            with self._lock:
                self._queued_ids.add(message_id)
                try:
                    self._jobs.put_nowait((message_id, text, session))
                except queue.Full:
                    self._queued_ids.discard(message_id)
                    return False
            return True
        except Exception:
            with self._lock:
                self._queued_ids.discard(message_id)
            raise

    def cancel(self, message_id: int) -> None:
        """Interrupt a queued or running voice turn; completed turns are untouched."""
        with self._lock:
            if message_id not in self._queued_ids and message_id != self._current_message_id:
                return
            self._cancelled.add(message_id)
            process = self._process if message_id == self._current_message_id else None
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def _ask(self, text: str, session: str | None) -> str:
        if self.api_client:
            return self._ask_api(text, session)
        command = [self.executable, "chat", "--query-file", "-", "--oneshot", "-Q",
                   "--format", "stream-json", "--source", "desktop",
                   "--run-budget", "120"]
        if session:
            command.extend(["--resume", session])
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        invocation, options = command_invocation(self.executable, command[1:])
        process = subprocess.Popen(invocation, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                   errors="replace", creationflags=flags, **options)
        with self._lock:
            self._process = process
            cancelled = self._current_message_id in self._cancelled
        if cancelled:
            process.terminate()
        try:
            stdout, _stderr = process.communicate(input=text, timeout=135)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError("Hermes timed out") from None
        finally:
            with self._lock:
                self._process = None
        if process.returncode != 0:
            raise RuntimeError(f"Hermes exited with code {process.returncode}")
        answer, _session = parse_result(stdout)
        self._last_run_session = _session
        return answer

    def _ask_api(self, text: str, session: str | None) -> str:
        run_id = self.api_client.start_run(text, session)
        with self._lock:
            self._run_id = run_id
            message_id = self._current_message_id
        deadline = time.monotonic() + 300
        stop_sent = False
        last_approval_id = None
        try:
            while time.monotonic() < deadline:
                with self._lock:
                    cancelled = self._stop.is_set() or message_id in self._cancelled
                if cancelled and not stop_sent:
                    self.api_client.stop(run_id)
                    stop_sent = True
                state = self.api_client.status(run_id)
                if isinstance(state.get("session_id"), str) and state["session_id"]:
                    self._last_run_session = state["session_id"]
                status = state.get("status")
                if status == "waiting_for_approval":
                    event = state.get("approval") or {}
                    request_id = event.get("request_id")
                    if not isinstance(request_id, str) or not request_id:
                        raise RuntimeError("Hermes approval has no request ID")
                    pending = {
                        "run_id": run_id, "request_id": request_id,
                        "message_id": message_id,
                        "session_id": self._last_run_session or session,
                        "conversation_id": message_route(self.database, message_id, session)[1],
                        "command": str(event.get("command") or ""),
                        "description": str(event.get("description") or ""),
                    }
                    with self._lock:
                        self._pending_approval = pending
                    if request_id != last_approval_id:
                        last_approval_id = request_id
                        if self.on_approval:
                            self.on_approval(message_id, pending)
                else:
                    with self._lock:
                        self._pending_approval = None
                if status == "completed":
                    answer = state.get("output")
                    if not isinstance(answer, str) or not answer.strip():
                        raise RuntimeError("Hermes returned no text")
                    session_id = state.get("session_id")
                    self._last_run_session = session_id if isinstance(session_id, str) and session_id else None
                    return answer.strip()
                if status in {"failed", "cancelled", "interrupted"}:
                    raise RuntimeError(f"Hermes run {status}")
                time.sleep(0.5)
            self.api_client.stop(run_id)
            raise RuntimeError("Hermes run timed out")
        finally:
            with self._lock:
                self._run_id = None
                self._pending_approval = None

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self._jobs.get()
            if job is None:
                return
            message_id, text, session = job
            with self._lock:
                self._queued_ids.discard(message_id)
                self._current_message_id = message_id
                cancelled = message_id in self._cancelled
            if cancelled:
                set_delivery(self.database, message_id, "interrupted")
                with self._lock:
                    self._current_message_id = None
                    self._cancelled.discard(message_id)
                continue
            set_delivery(self.database, message_id, "running")
            conversation = None
            self._last_run_session = None
            try:
                session, conversation = message_route(self.database, message_id, session)
                answer = self._ask(text, session)
                with self._lock:
                    cancelled = message_id in self._cancelled
                if cancelled:
                    set_delivery(self.database, message_id, "interrupted")
                    continue
                add_message(self.database, self.source, answer, role="assistant",
                            delivery="completed", reply_to=message_id, conversation_id=conversation)
                bind_draft(self.database, conversation, self._last_run_session)
                if self._last_run_session:
                    set_setting(self.database, self.session_setting, self._last_run_session)
                set_delivery(self.database, message_id, "completed")
                with self._lock:
                    self._last_error = None
            except Exception as exc:
                with self._lock:
                    cancelled = message_id in self._cancelled
                    if not cancelled:
                        self._last_error = str(exc)
                set_delivery(self.database, message_id,
                             "interrupted" if cancelled else "failed")
                if self.on_error and not cancelled:
                    try:
                        self.on_error(message_id, str(exc))
                    except Exception:
                        pass
            else:
                if self.on_reply:
                    try:
                        self.on_reply(message_id, answer)
                    except Exception as exc:
                        with self._lock:
                            self._last_error = f"Voice callback: {exc}"
            finally:
                bind_draft(self.database, conversation, self._last_run_session)
                with self._lock:
                    self._current_message_id = None
                    self._cancelled.discard(message_id)
