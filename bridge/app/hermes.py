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
from .answer_stream import CancellationUnconfirmed


SESSION_SETTING = "hermes_session_id"

#: Hermes 0.22.x refuses API writes into sessions owned by another surface
#: (``session_api_turn.admit_api_steps`` raises ``permission_denied`` for any
#: source outside this set). The Bridge must therefore route to sessions the
#: API itself created, never to a desktop conversation.
API_WRITABLE_SOURCES = frozenset({"api_server", "bot_room"})


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


def latest_api_session_info(state_db: Path) -> dict | None:
    """Newest session the Hermes API may write into (not a desktop session)."""
    if not state_db.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{state_db.as_posix()}?mode=ro", uri=True, timeout=2) as db:
            row = db.execute(
                "SELECT id, title, last_activity_at, source FROM sessions "
                "WHERE source IN ('api_server', 'bot_room') "
                "AND COALESCE(archived, 0) = 0 AND COALESCE(hidden, 0) = 0 "
                "ORDER BY last_activity_at DESC LIMIT 1"
            ).fetchone()
        return ({"id": row[0], "title": row[1], "last_activity_at": row[2], "source": row[3]}
                if row else None)
    except sqlite3.Error:
        return None


def session_info(state_db: Path, session_id: str) -> dict | None:
    if not state_db.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{state_db.as_posix()}?mode=ro", uri=True, timeout=2) as db:
            row = db.execute(
                "SELECT id, title, last_activity_at, source FROM sessions WHERE id = ? "
                "AND COALESCE(archived, 0) = 0 AND COALESCE(hidden, 0) = 0 LIMIT 1",
                (session_id,),
            ).fetchone()
        return ({"id": row[0], "title": row[1], "last_activity_at": row[2], "source": row[3]}
                if row else None)
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
        self.authorize_job = lambda message_id: True
        self.release_authorization = lambda message_id: None
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
        self._progress = {}
        self._progress_revision = 0

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
        probe = getattr(self.api_client, "health_snapshot", None)
        health = probe() if callable(probe) else None
        with self._lock:
            return {"available": health["available"] if health is not None else bool(self.executable or self.api_client),
                    "api_health": health, "pending": self._jobs.qsize(),
                    "running": self._current_message_id is not None,
                    "last_error": self._last_error, "session": current,
                    "mode": "runs-api" if self.api_client else "cli",
                    "approval": dict(self._pending_approval) if self._pending_approval else None}

    def _preferred_session_info(self) -> dict | None:
        """Continuation target for API delivery.

        A desktop session is read-only for the API, so it is never a default
        target: its API call would fail with ``permission_denied``. Prefer the
        newest API-created session; return ``None`` when there is none so the
        next run creates one.
        """
        state_db = self.hermes_home / "state.db"
        selected_id = get_setting(self.database, SESSION_SETTING)
        selected = session_info(state_db, selected_id) if selected_id else None
        if selected and selected.get("source") not in API_WRITABLE_SOURCES:
            selected = None
        latest_api = latest_api_session_info(state_db)
        if selected and latest_api and selected["id"] != latest_api["id"]:
            if (latest_api["last_activity_at"] or 0) > (selected["last_activity_at"] or 0):
                return latest_api
        return selected or latest_api

    def _check_api_target(self, session: str | None) -> None:
        """Refuse a desktop target with an explanation instead of an opaque 409."""
        if not self.api_client or not session:
            return
        info = session_info(self.hermes_home / "state.db", session)
        if info is None or info.get("source") in API_WRITABLE_SOURCES:
            return
        title = info.get("title") or session
        raise RuntimeError(
            f"Hermes 会话「{title}」来自 {info.get('source', '未知')} 端，"
            "Hermes API 不允许写入非 API 会话。请在网页 Hermes 分组点“+ 新建”，"
            "选中新会话后重新按键或发送。")

    def pending_approval(self) -> dict | None:
        with self._lock:
            return dict(self._pending_approval) if self._pending_approval else None

    def approve(self, request_id: str, choice: str) -> bool:
        with self._lock:
            pending = self._pending_approval
            if not pending or pending["request_id"] != request_id or not self.api_client:
                return False
            run_id = pending["run_id"]
        if not self.authorize_job(pending['message_id']):
            raise RuntimeError('访问授权已失效，请重新登录 Bridge')
        self.api_client.approve(run_id, request_id, choice)
        with self._lock:
            if self._pending_approval and self._pending_approval["request_id"] == request_id:
                self._pending_approval = None
        return True

    def enqueue(self, message_id: int, text: str, *, new_session: bool = False) -> bool:
        if not self.authorize_job(message_id):
            return False
        if not (self.executable or self.api_client) or self._stop.is_set():
            return False
        preferred = None if new_session else self._preferred_session_info()
        session = preferred["id"] if preferred else None
        with sqlite3.connect(self.database) as db:
            row = db.execute('SELECT conversation_id,text,created_at FROM messages WHERE id=?', (message_id,)).fetchone()
        try:
            with self._lock:
                self._queued_ids.add(message_id)
                self._progress[message_id] = {'message_id': message_id, 'source': self.source,
                    'session_id': row[0] if row else None, 'text': '', 'state': 'queued', 'error': None,
                    'request_text': row[1] if row else '', 'created_at': row[2] if row else ''}
                self._task_locked(message_id, state='queued')
                try:
                    self._jobs.put_nowait((message_id, text, session))
                except queue.Full:
                    self._queued_ids.discard(message_id)
                    self._task_locked(message_id, state='failed', error='发送队列已满')
                    return False
            return True
        except Exception:
            with self._lock:
                self._queued_ids.discard(message_id)
            raise

    def _task_locked(self, message_id, **changes):
        task = self._progress.get(message_id)
        if task is None:
            return
        self._progress_revision += 1
        task.update(changes, revision=self._progress_revision)
        if len(self._progress) > 64:
            for old_id in list(self._progress):
                if old_id != message_id and self._progress[old_id]['state'] in {'completed', 'interrupted', 'failed', 'stop_failed'}:
                    del self._progress[old_id]
                    if len(self._progress) <= 64:
                        break

    def _publish(self, message_id, text):
        if not isinstance(text, str):
            return
        with self._lock:
            if message_id != self._current_message_id or message_id in self._cancelled:
                return
            if self._progress.get(message_id, {}).get('state') != 'running':
                return
            self._task_locked(message_id, text=text[:200000])

    def progress_snapshot(self, conversation):
        with sqlite3.connect(self.database) as db:
            allowed = {row[0] for row in db.execute(
                'SELECT id FROM messages WHERE source=? AND conversation_id IS ?', (self.source, conversation))}
        with self._lock:
            return [dict(task) for mid, task in self._progress.items() if mid in allowed]

    def cancel(self, message_id: int) -> bool:
        """Interrupt a queued or running voice turn; completed turns are untouched."""
        with self._lock:
            if message_id not in self._queued_ids and message_id != self._current_message_id:
                return False
            if self._progress.get(message_id, {}).get('state') in {'completed', 'interrupted', 'failed', 'stop_failed'}:
                return False
            self._cancelled.add(message_id)
            queued = message_id != self._current_message_id
            self._task_locked(message_id, state='interrupted' if queued else 'stopping')
            set_delivery(self.database, message_id, 'interrupted' if queued else 'stopping')
            process = self._process if message_id == self._current_message_id else None
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        return True

    def _ask(self, text: str, session: str | None) -> str:
        if not self.authorize_job(self._current_message_id):
            raise RuntimeError('访问授权已失效，请重新登录 Bridge')
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
            deadline = time.monotonic()+135
            first = True
            while True:
                if not self.authorize_job(self._current_message_id):
                    process.kill()
                    process.communicate()
                    raise RuntimeError('访问授权已失效，已停止本轮 Hermes 进程')
                try:
                    stdout, _stderr = process.communicate(input=text if first else None, timeout=.5)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    if time.monotonic() >= deadline:
                        process.kill()
                        process.communicate()
                        raise RuntimeError('Hermes timed out') from None
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
        terminal = False
        follower_stop = threading.Event()
        follower = None
        if hasattr(self.api_client, 'follow_text'):
            follower = threading.Thread(target=self.api_client.follow_text,
                args=(run_id, lambda text: self._publish(message_id, text), follower_stop), daemon=True)
            follower.start()
        last_approval_id = None
        try:
            while time.monotonic() < deadline:
                with self._lock:
                    cancelled = self._stop.is_set() or message_id in self._cancelled
                if not self.authorize_job(message_id):
                    cancelled = True
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
                    terminal = True
                    answer = state.get("output")
                    if not isinstance(answer, str) or not answer.strip():
                        raise RuntimeError("Hermes returned no text")
                    session_id = state.get("session_id")
                    self._last_run_session = session_id if isinstance(session_id, str) and session_id else None
                    return answer.strip()
                if status in {"failed", "cancelled", "interrupted"}:
                    terminal = True
                    raise RuntimeError(f"Hermes run {status}")
                time.sleep(0.5)
            self.api_client.stop(run_id)
            raise RuntimeError("Hermes run timed out")
        except Exception as exc:
            with self._lock:
                cancelled = message_id in self._cancelled
            if cancelled and not terminal:
                raise CancellationUnconfirmed('未能确认 Hermes 已停止，任务可能仍在运行，请在 Hermes 中检查') from exc
            raise
        finally:
            follower_stop.set()
            if follower:
                follower.join(timeout=.1)
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
                self._task_locked(message_id, state='interrupted' if cancelled else 'running')
            if cancelled:
                set_delivery(self.database, message_id, "interrupted")
                with self._lock:
                    self._current_message_id = None
                    self._cancelled.discard(message_id)
                self.release_authorization(message_id)
                continue
            set_delivery(self.database, message_id, "running")
            conversation = None
            self._last_run_session = None
            try:
                if not self.authorize_job(message_id):
                    raise RuntimeError('访问授权已失效，请重新登录 Bridge')
                session, conversation = message_route(self.database, message_id, session)
                self._check_api_target(session)
                answer = self._ask(text, session)
                with self._lock:
                    cancelled = message_id in self._cancelled
                    if cancelled:
                        set_delivery(self.database, message_id, "interrupted")
                        self._task_locked(message_id, state='interrupted')
                        continue
                    # Serialize final settlement with cancel, so a successful stop
                    # cannot race between the cancellation check and publication.
                    bind_draft(self.database, conversation, self._last_run_session)
                    if self._last_run_session:
                        set_setting(self.database, self.session_setting, self._last_run_session)
                    add_message(self.database, self.source, answer, role="assistant",
                                delivery="completed", reply_to=message_id, conversation_id=conversation)
                    set_delivery(self.database, message_id, "completed")
                    self._task_locked(message_id, state='completed', text=answer, error=None)
                with self._lock:
                    self._last_error = None
            except Exception as exc:
                with self._lock:
                    cancelled = message_id in self._cancelled
                    if not cancelled:
                        self._last_error = str(exc)
                delivery = ('stop_failed' if isinstance(exc, CancellationUnconfirmed) else
                            'interrupted' if cancelled else 'failed')
                set_delivery(self.database, message_id, delivery)
                with self._lock:
                    self._task_locked(message_id, state=delivery,
                                      error=str(exc) if delivery != 'interrupted' else None)
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
                self.release_authorization(message_id)
                bind_draft(self.database, conversation, self._last_run_session)
                with self._lock:
                    self._current_message_id = None
                    self._cancelled.discard(message_id)
