"""Button recording routed to the web-selected agent and conversation."""

import queue
import json
import re
import threading
from pathlib import Path

from . import faces
from .audio_output import AudioOutput
from .storage import add_message, set_delivery, get_setting, set_setting
from .tts import SynthesisCancelled, synthesize_chunks


class VoiceConversation:
    def __init__(self, database: Path, data_dir: Path, device, hermes, *, audio_output=None,
                 workers=None, validate_target=None):
        self.database = database
        self.data_dir = data_dir
        self.device = device
        self.hermes = hermes
        self.workers = workers or {"hermes": hermes}
        self.validate_target = validate_target
        self._require_session = workers is not None
        self._target_lock = threading.Lock()
        self._selected_target = {"source": "hermes", "session_id": None}
        try:
            saved = json.loads(get_setting(database, "voice_target") or "null")
            if isinstance(saved, dict) and saved.get("source") in {"hermes", "deepseek_harness", "doubao_web"}:
                self._selected_target = {"source": saved["source"], "session_id": saved.get("session_id")}
        except (ValueError, TypeError):
            pass
        self._capture_target = dict(self._selected_target)
        self._message_source = "hermes"
        self._approval_worker = hermes
        self.audio_output = audio_output if audio_output is not None else AudioOutput(data_dir)
        self._lock = threading.Lock()
        self._capture_generation = 0
        self._message_id: int | None = None
        self._state = "idle"
        self._last_error: str | None = None
        self._jobs: queue.Queue[tuple[int, str, str, int] | None] = queue.Queue(maxsize=2)
        self._output_generation = 0
        self._approval_target: dict | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="voice-reply", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=2)

    def snapshot(self) -> dict:
        with self._target_lock:
            target = dict(self._selected_target)
        with self._lock:
            return {"state": self._state, "last_error": self._last_error,
                    "message_id": self._message_id, "target": target,
                    "capture_target": dict(self._capture_target)}

    def set_target(self, source: str, session_id: str | None) -> dict:
        target = {"source": source, "session_id": session_id}
        with self._target_lock:
            set_setting(self.database, "voice_target", json.dumps(target))
            self._selected_target = target
        return dict(target)

    def on_listen_start(self, capture_generation: int) -> None:
        # Never call a network API on the serial receive thread. Selection was
        # validated by the web endpoint; snapshot it before recording begins.
        with self._target_lock:
            target = dict(self._selected_target)
        worker = self.workers.get(target["source"])
        pending = worker.pending_approval() if worker and hasattr(worker, "pending_approval") else None
        if pending and self._require_session:
            pending = pending if target["session_id"] and target["session_id"] in {
                pending.get("session_id"), pending.get("conversation_id")} else None
        with self._lock:
            same_approval = pending and self._message_source == target["source"] and (
                pending.get("message_id", self._message_id) == self._message_id)
            old_message_id = None if same_approval else self._message_id
            old_worker = self.workers.get(self._message_source)
            self._capture_generation = capture_generation
            self._capture_target = target
            self._approval_target = pending
            self._approval_worker = worker
            if not pending:
                self._message_id = None
                self._message_source = target["source"]
            else:
                self._message_id = pending.get("message_id", self._message_id)
                self._message_source = target["source"]
            self._state = "listening_for_approval" if pending else "listening"
            self._last_error = None
        if old_message_id is not None:
            cancel = getattr(old_worker, "cancel", None)
            if cancel:
                cancel(old_message_id)

    def on_transcript(self, text: str, capture_generation: int) -> None:
        with self._lock:
            if capture_generation != self._capture_generation:
                return
            approval_target = self._approval_target
            approval_worker = self._approval_worker
            target = dict(self._capture_target)
        if approval_target:
            normalized = re.sub(r"[\s，。,.！!？?、]+", "", text)
            choice = ("once" if normalized == "同意审批" else
                      "deny" if normalized in {"拒绝审批", "不同意审批"} else None)
            if choice is None:
                with self._lock:
                    self._state = "approval_pending"
                    self._last_error = "审批口令未识别；请说同意审批或拒绝审批"
                return
            try:
                accepted = approval_worker.approve(approval_target["request_id"], choice)
            except (RuntimeError, ValueError) as exc:
                accepted = False
                error = str(exc)
            else:
                error = "审批请求已失效"
            with self._lock:
                self._approval_target = None
                self._state = ("waiting_for_hermes" if target["source"] == "hermes" else "waiting_for_agent") if accepted else "error"
                self._last_error = None if accepted else error
            self.device.set_face(faces.READY if accepted else faces.ERROR)
            return
        with self._lock:
            if not text.strip():
                self._state = "idle"
                self._last_error = "未识别到语音"
                return
            self._state = "sending"
        worker = self.workers.get(target["source"])
        try:
            if worker is None:
                raise ValueError("豆包 PPT 暂未接入按键语音，请选择 Hermes 或 DeepSeek Harness")
            if self._require_session and not target["session_id"]:
                raise ValueError("请先在网页选择或新建一个会话")
            if self.validate_target and target["session_id"]:
                self.validate_target(target["source"], target["session_id"])
        except (ValueError, OSError, RuntimeError) as exc:
            with self._lock:
                if capture_generation == self._capture_generation:
                    self._state, self._last_error = "error", str(exc)
            self.device.set_face(faces.ERROR)
            return
        item = add_message(self.database, target["source"], text.strip(),
                           delivery="queued", input_method="voice", conversation_id=target["session_id"])
        with self._lock:
            if capture_generation != self._capture_generation:
                set_delivery(self.database, item["id"], "interrupted")
                return
            self._message_id = item["id"]
            self._message_source = target["source"]
        try:
            accepted = worker.enqueue(item["id"], text.strip())
        except Exception as exc:
            set_delivery(self.database, item["id"], "failed")
            self.on_agent_error(item["id"], str(exc), source=target["source"])
            return
        with self._lock:
            obsolete = capture_generation != self._capture_generation
        if obsolete:
            worker.cancel(item["id"])
            set_delivery(self.database, item["id"], "interrupted")
            return
        if accepted:
            with self._lock:
                if self._message_id == item["id"]:
                    self._state = "waiting_for_hermes" if target["source"] == "hermes" else "waiting_for_agent"
        else:
            set_delivery(self.database, item["id"], "failed")
            with self._lock:
                if self._message_id == item["id"]:
                    self._state = "error"
                    self._last_error = "当前智能体暂时无法接收语音消息"

    def on_reply(self, message_id: int, answer: str, *, source="hermes") -> None:
        with self._lock:
            if message_id != self._message_id or source != self._message_source:
                return
            self._state = "queued_to_speak" if self.audio_output.enabled else "text_only"
            output_generation = self._output_generation
            enabled = self.audio_output.enabled
        if not enabled:
            self.device.set_face(faces.READY)
            return
        try:
            self._jobs.put_nowait((message_id, answer, "reply", output_generation))
        except queue.Full:
            with self._lock:
                if message_id == self._message_id:
                    self._state = "error"
                    self._last_error = "语音播报队列已满"

    def on_hermes_error(self, message_id: int, error: str) -> None:
        self.on_agent_error(message_id, error, source="hermes")

    def on_agent_error(self, message_id: int, error: str, *, source: str) -> None:
        with self._lock:
            if message_id != self._message_id or source != self._message_source:
                return
            self._state = "error"
            self._last_error = f"{'Hermes' if source == 'hermes' else 'DeepSeek Harness'} 回复失败：{error}"
        self.device.set_face(faces.ERROR)

    def on_approval(self, message_id: int, pending: dict) -> None:
        with self._lock:
            if message_id != self._message_id or self._message_source != "hermes":
                return
            self._state = "approval_pending"
            output_generation = self._output_generation
        description = pending.get("description", "")[:100]
        self.device.set_face(faces.APPROVE)
        if not self.audio_output.enabled:
            return
        prompt = (f"Hermes 请求审批：{description}。请先在网页核对具体命令。"
                  "确认后按键说同意审批；不同意就说拒绝审批。")
        try:
            self._jobs.put_nowait((message_id, prompt, "approval", output_generation))
        except queue.Full:
            pass

    def on_output_muted(self) -> None:
        with self._lock:
            self._output_generation += 1
            if self._state in {"queued_to_speak", "speaking", "sent_to_device"}:
                self._state = "text_only"
            elif self._state == "approval_prompt":
                self._state = "approval_pending"

    def _current(self, message_id: int, output_generation: int) -> bool:
        with self._lock:
            return (self._message_id == message_id
                    and self._output_generation == output_generation
                    and self.audio_output.enabled)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            message_id, answer, kind, output_generation = job
            if not self._current(message_id, output_generation):
                continue
            generation = self.device.stop_playback()
            if generation is None:
                with self._lock:
                    if message_id == self._message_id:
                        self._state = "error"
                        self._last_error = "设备正在收音或未连接，无法播报回复"
                continue
            try:
                with self._lock:
                    if message_id == self._message_id:
                        self._state = "approval_prompt" if kind == "approval" else "speaking"
                for wav in synthesize_chunks(
                    answer, self.data_dir,
                    cancelled=lambda: not self._current(message_id, output_generation)
                    or not self.device.is_current_generation(generation),
                ):
                    if not self._current(message_id, output_generation):
                        break
                    if not self.device.append_wav(wav, generation=generation):
                        raise RuntimeError("设备已打断播报或断开连接")
                with self._lock:
                    if (message_id == self._message_id
                            and output_generation == self._output_generation):
                        self._state = "approval_pending" if kind == "approval" else "sent_to_device"
                        self._last_error = None
            except SynthesisCancelled:
                pass
            except Exception as exc:
                with self._lock:
                    if (message_id == self._message_id
                            and output_generation == self._output_generation):
                        self._state = "error"
                        self._last_error = f"{type(exc).__name__}: {exc}"
            finally:
                self.device.finish_playback(generation)
