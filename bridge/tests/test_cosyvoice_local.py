import io
import wave

import numpy as np
import pytest

from bridge.app import cosyvoice_local, tts


def test_local_voice_preserves_english_and_mixed_short_sentences():
    for text in ("Hello, I am your robot. Nice to meet you.",
                 "你好，我是球球。Hello, I am your robot. 很高兴见到你。"):
        assert list(tts._cosyvoice_parts(text)) == [text]
    long = "Hello, I am your robot. " * 30
    parts = list(tts._cosyvoice_parts(long))
    assert all(0 < len(part) <= 160 for part in parts)
    assert " ".join(parts) == long.strip()
    assert len(parts[0]) <= 60


def test_long_chinese_reply_starts_with_first_complete_clause():
    text = '你好，我会先回答你的问题。' + '接下来我们可以继续检查麦克风的收音效果。'*10
    parts = list(tts._cosyvoice_parts(text))
    assert parts[0] == '你好，我会先回答你的问题。'
    assert ''.join(parts) == text


def test_local_loudness_is_not_dominated_by_isolated_peaks():
    signal = np.sin(np.arange(24000) * .08).astype(np.float32) * .08
    signal[12000] = .9
    encoded = tts._cosyvoice_device_wav(signal, 24000)
    with wave.open(io.BytesIO(encoded), "rb") as wav:
        assert wav.getframerate() == 16000
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float) / 32768
    assert np.max(np.abs(pcm)) <= .036
    assert .012 < np.sqrt(np.mean(pcm**2)) < .017


def test_only_installed_local_voices_can_be_selected(tmp_path, monkeypatch):
    monkeypatch.setattr(cosyvoice_local, "status", lambda _: {"ready": False, "running": False})
    with pytest.raises(RuntimeError, match="尚未安装"):
        tts.set_selected_voice(tmp_path, "cosyvoice")
    assert tts.selected_voice(tmp_path) == "kokoro"
    with pytest.raises(ValueError):
        tts.set_selected_voice(tmp_path, "cosyvoice-anhui")
    monkeypatch.setattr(cosyvoice_local, "start", lambda _: None)
    monkeypatch.setattr(cosyvoice_local, "status", lambda _: {"ready": True, "running": False})
    with pytest.raises(ValueError):
        tts.set_selected_voice(tmp_path, "cosyvoice-yue")
    tts.set_selected_voice(tmp_path, "cosyvoice")
    assert tts.selected_voice(tmp_path) == "cosyvoice"
    assert "cosyvoice-yue" not in {item["id"] for item in tts.voice_status(tmp_path)["voices"]}
    assert "paimon" in {item["id"] for item in tts.voice_status(tmp_path)["voices"]}


def test_mixed_sentence_uses_one_local_voice_and_device_format(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tts, "selected_voice", lambda _: "cosyvoice")
    def synthesize(text, _directory, voice, _cancelled):
        calls.append((text, voice))
        return np.sin(np.arange(4800) * .1).astype(np.float32) * .3, 24000
    monkeypatch.setattr(cosyvoice_local, "synthesize", synthesize)
    chunks = list(tts.synthesize_chunks("Hello, 你好，很高兴见到你。", tmp_path))
    assert calls == [("Hello, 你好，很高兴见到你。", "cosyvoice")]
    with wave.open(io.BytesIO(chunks[0]), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    assert 0 < np.max(np.abs(samples)) <= 1967


def test_cancelled_local_generation_never_produces_a_playback_chunk(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "selected_voice", lambda _: "cosyvoice")
    monkeypatch.setattr(cosyvoice_local, "synthesize", lambda *_: None)
    with pytest.raises(tts.SynthesisCancelled):
        list(tts.synthesize_chunks("你好。", tmp_path))
    monkeypatch.setattr(cosyvoice_local, "synthesize", lambda *_: pytest.fail("must not synthesize"))
    with pytest.raises(tts.SynthesisCancelled):
        list(tts.synthesize_chunks("你好。", tmp_path, cancelled=lambda: True))


def test_switching_back_to_installed_paimon_starts_it_without_losing_selection(tmp_path, monkeypatch):
    events = []
    monkeypatch.setattr(tts, "paimon_status", lambda _: {"installed": True, "ready": False})
    monkeypatch.setattr(cosyvoice_local, "stop", lambda: events.append("stop-cosy"))
    monkeypatch.setattr(tts, "start_paimon_service", lambda _: events.append("start-paimon"))
    tts.set_selected_voice(tmp_path, "paimon")
    assert events == ["stop-cosy", "start-paimon"]
    assert tts.selected_voice(tmp_path) == "paimon"


def test_windows_shutdown_targets_only_the_owned_worker_tree(monkeypatch):
    if cosyvoice_local.os.name != "nt":
        pytest.skip("Windows venv launcher behavior")
    commands = []
    monkeypatch.setattr(cosyvoice_local.subprocess, "run", lambda command, **_: commands.append(command))
    class OwnedWorker:
        pid = 12345
        def wait(self, timeout):
            return 0
    cosyvoice_local.stop_owned_process(OwnedWorker())
    assert commands == [["taskkill.exe", "/PID", "12345", "/T", "/F"]]
