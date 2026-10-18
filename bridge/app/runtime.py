"""Shared task presentation and allowlisted, content-free diagnostic history."""

from collections import deque
from datetime import datetime, timezone
import platform
import threading


LABELS = {
    "idle": "准备就绪", "listening": "正在录音，再按一次结束",
    "transcribing": "正在本地识别", "waiting_reply": "正在等待 AI 回复",
    "approval": "等待工具审批", "synthesizing": "正在生成语音",
    "playing": "正在播放", "completed": "本轮已完成",
    "text_only": "回复已显示，语音已静音", "error": "本轮失败",
    "interrupted": "本轮语音已中断",
}


class RuntimeStatus:
    def __init__(self):
        self._lock = threading.Lock()
        self._signature = None
        self._events = deque(maxlen=60)
        self._changed_at = None

    def snapshot(self, device, speech, voice, agents):
        raw = voice.get("state", "idle")
        detail = None
        same_capture = speech.get("capture_generation") == voice.get("capture_generation")
        if device.get("listening"):
            state = "listening"
        elif device.get("playing"):
            state = "playing"
        elif device.get("last_error") and raw in {"speaking", "sent_to_device", "interrupted"}:
            state, detail = "error", device["last_error"]
        elif raw in {"error", "interrupted"}:
            state, detail = raw, voice.get("last_error")
        elif same_capture and speech.get("state") in {"queued", "transcribing"}:
            state = "transcribing"
        elif raw in {"approval_pending", "listening_for_approval"}:
            state = "approval"
        elif raw in {"queued_to_speak", "speaking", "approval_prompt"}:
            state = "synthesizing"
        elif raw in {"sending", "waiting_for_hermes", "waiting_for_agent"}:
            state = "waiting_reply"
        elif any(agent.get("running") or agent.get("pending") for agent in agents):
            state = "waiting_reply"
        elif raw == "sent_to_device":
            state = "completed"
        elif raw == "text_only":
            state = "text_only"
        else:
            state = "idle"
            detail = voice.get("last_error")
        with self._lock:
            signature = (state, voice.get("capture_generation"), voice.get("message_id"))
            if signature != self._signature:
                self._signature = signature
                self._changed_at = datetime.now(timezone.utc).isoformat()
                # Never store exception text, prompts, transcripts or session IDs.
                self._events.append({"at": self._changed_at, "state": state})
            return {"state": state, "label": LABELS[state], "detail": detail,
                    "changed_at": self._changed_at,
                    "active": state in {"listening", "transcribing", "waiting_reply", "approval", "synthesizing", "playing"}}

    def diagnostics(self, status):
        def selected(value, keys):
            return {key: value.get(key) for key in keys}
        with self._lock:
            events = list(self._events)
        return {
            "format_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime": {"python": platform.python_version(), "system": platform.system()},
            "bridge": status["bridge"],
            "task": selected(status["task"], ("state", "active", "changed_at")),
            "device": selected(status["device"], ("present", "connected", "firmware", "listening", "playing",
                "audio_down_sent", "audio_down_ack", "device_bad_crc", "reset_reason", "screen_cached_frames")),
            "speech": selected(status["speech"], ("state", "pending")),
            "agents": {name: selected(status[name], ("available", "pending", "running", "mode"))
                       for name in ("hermes", "deepseek_harness")},
            "audio_output": status["audio_output"],
            "tts": selected(status["tts"], ("active", "ready", "english_ready", "paimon_ready")),
            "store": {"consistent": status["store"]["consistent"]},
            "events": events,
        }
