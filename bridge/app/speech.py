"""Offline speech recognition. Audio and transcripts stay in process memory."""

import io
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path


class SpeechWorker:
    def __init__(self, model_cache: Path, on_transcript=None):
        self.model_cache = model_cache
        self.on_transcript = on_transcript
        self._jobs: queue.Queue[tuple[bytes, int] | None] = queue.Queue(maxsize=2)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status = {"state": "idle", "last_error": None, "last_text": None}
        self._transcripts: list[dict] = []

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
            return
        try:
            self._jobs.put_nowait((wav, capture_generation))
            with self._lock:
                self._status["state"] = "queued"
        except queue.Full:
            with self._lock:
                self._status["last_error"] = "Speech queue full"

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._status, pending=self._jobs.qsize())

    def transcripts(self) -> list[dict]:
        with self._lock:
            return list(self._transcripts)

    def _run(self) -> None:
        model = None
        while True:
            job = self._jobs.get()
            if job is None:
                return
            wav, capture_generation = job
            with self._lock:
                self._status.update(state="transcribing", last_error=None)
            try:
                if model is None:
                    from faster_whisper import WhisperModel
                    # Never download a model while processing speech.
                    model = WhisperModel(
                        "small", device="cpu", compute_type="int8",
                        download_root=str(self.model_cache), local_files_only=True,
                    )
                segments, _ = model.transcribe(
                    io.BytesIO(wav), language="zh", beam_size=5,
                    vad_filter=True, condition_on_previous_text=False,
                )
                text = "".join(segment.text for segment in segments).strip()
                with self._lock:
                    self._status.update(state="idle", last_text=text)
                    if text:
                        self._transcripts.append({
                            "id": len(self._transcripts) + 1,
                            "text": text,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        })
                        self._transcripts[:] = self._transcripts[-20:]
                if self.on_transcript:
                    self.on_transcript(text, capture_generation)
            except Exception as exc:
                with self._lock:
                    self._status.update(state="error", last_error=f"{type(exc).__name__}: {exc}")
