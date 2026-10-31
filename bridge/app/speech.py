"""Offline speech recognition. Audio and transcripts stay in process memory."""

import io
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from .speech_cleanup import SpeechCleanup


class SpeechWorker:
    def __init__(self, model_cache: Path, on_transcript=None, on_error=None):
        self.model_cache = model_cache
        self.on_transcript = on_transcript
        self.on_error = on_error
        self._jobs: queue.Queue[tuple[bytes, int] | None] = queue.Queue(maxsize=2)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status = {"state": "idle", "last_error": None, "last_text": None}
        self._transcripts: list[dict] = []
        self.cleanup = SpeechCleanup()
        self._status.update(cleanup_mode='light', cleanup_ms=0, cleanup_warning=None, last_original_text=None)

    def set_cleanup_mode(self, mode):
        if mode not in ('light', 'simplified'):
            raise ValueError('Invalid cleanup mode')
        with self._lock:
            self._status['cleanup_mode'] = mode

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="offline-speech", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            self._jobs.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=2)

    def enqueue(self, wav: bytes | None, capture_generation: int = 0) -> None:
        if wav is None or len(wav) < 44 + 16000:  # At least 0.5 seconds of PCM.
            self._failed("录音不足半秒，请重新按键录音", capture_generation)
            return
        try:
            self._jobs.put_nowait((wav, capture_generation))
            with self._lock:
                self._status.update(state="queued", last_error=None, capture_generation=capture_generation)
        except queue.Full:
            self._failed("语音识别队列已满，请稍后重新录音", capture_generation)

    def _failed(self, error, generation):
        with self._lock:
            self._status.update(state="error", last_error=error, capture_generation=generation)
        if self.on_error:
            self.on_error(error, generation)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._status, pending=self._jobs.qsize())

    def transcripts(self) -> list[dict]:
        with self._lock:
            return list(self._transcripts)

    def _load_model(self):
        from faster_whisper import WhisperModel
        return WhisperModel('small', device='cpu', compute_type='int8',
                            download_root=str(self.model_cache), local_files_only=True)

    def _run(self) -> None:
        try:
            self.cleanup.prepare()  # Load local dictionaries before the first capture.
        except Exception:
            pass  # Cleanup reports a warning and preserves text if unavailable.
        try:
            model = self._load_model()  # Preload locally before the first user recording.
        except Exception:
            model = None  # A real recording still gets the normal actionable error.
        with self._lock:
            self._status['model_ready'] = model is not None
        while True:
            job = self._jobs.get()
            if job is None:
                return
            wav, capture_generation = job
            with self._lock:
                self._status.update(state="transcribing", last_error=None, capture_generation=capture_generation)
            try:
                if model is None:
                    model = self._load_model()
                    with self._lock:
                        self._status['model_ready'] = True
                segments, _ = model.transcribe(
                    io.BytesIO(wav), language="zh", beam_size=5,
                    vad_filter=True, condition_on_previous_text=False,
                )
                original = "".join(segment.text for segment in segments).strip()
                result = self.cleanup.process(original, self.snapshot()['cleanup_mode'])
                text = result.text
                with self._lock:
                    self._status.update(state="idle", last_text=text, last_original_text=original,
                                        cleanup_ms=result.elapsed_ms, cleanup_warning=result.warning)
                    if text:
                        self._transcripts.append({
                            "id": len(self._transcripts) + 1,
                            "text": text,
                            "original_text": original,
                            "simplified_text": result.simplified,
                            "cleanup_changes": list(result.changes),
                            "cleanup_ms": result.elapsed_ms,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                        self._transcripts[:] = self._transcripts[-20:]
                if self.on_transcript:
                    self.on_transcript(text, capture_generation)
            except Exception as exc:
                self._failed(f"本地识别失败（{type(exc).__name__}），请检查模型后重新录音", capture_generation)
