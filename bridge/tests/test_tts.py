import io
import wave

import numpy as np
import pytest

from bridge.app.tts import (SynthesisCancelled, _english_phonemes, _mixed_language_segments,
                            _paimon_language, _stitch_wav_segments, _to_device_wav,
                            selected_voice, set_selected_voice, synthesize_chunks,
                            synthesize_wav, voice_status)


def test_device_wav_format_and_safe_peak():
    source = np.ones(2400, dtype=np.float32)
    result = _to_device_wav(source, 24000)
    with wave.open(io.BytesIO(result), "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000)
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
    assert len(pcm) == 1600
    assert pcm[0] == pcm[-1] == 0
    assert 3800 <= int(pcm.max()) <= 4100


def test_english_phonemes_survive_chinese_model_tokenization():
    from kokoro_onnx.config import DEFAULT_VOCAB

    phonemes = _english_phonemes("Hello Hermes API")
    assert len(phonemes) > 12
    assert all(character in DEFAULT_VOCAB for character in phonemes)
    assert _english_phonemes("a clear test").startswith("ə ")
    assert _english_phonemes("API").startswith("ˈeɪ")
    assert _english_phonemes("this is a clear test") == "ðɪs ɪz ə klˈɪɹ tˈɛst"


def test_english_voice_is_normalized_to_audible_device_level(tmp_path, monkeypatch):
    from bridge.app.tts import _english_wav_chunks

    model_path, voices_path = tmp_path / "model", tmp_path / "voices"
    model_path.write_bytes(b"model")
    voices_path.write_bytes(b"voices")

    class EnglishModel:
        def create(self, *_args, **_kwargs):
            return np.full(2400, 0.5, dtype=np.float32), 24000

    monkeypatch.setattr("bridge.app.tts._english_model_files", lambda _path: (model_path, voices_path))
    monkeypatch.setattr("bridge.app.tts._load_english_kokoro", lambda *_args: EnglishModel())
    wav = next(_english_wav_chunks("Hello", tmp_path))
    with wave.open(io.BytesIO(wav), "rb") as audio:
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(float) / 32768
    assert 0.0225 < np.sqrt(np.mean(samples[100:-100] ** 2)) < 0.0238


def test_voice_loudness_normalization_matches_different_source_gains():
    tone = np.sin(2 * np.pi * 440 * np.arange(2400) / 24000).astype(np.float32) * 0.5
    rms_values = []
    for gain in (0.12, 0.20):
        with wave.open(io.BytesIO(_to_device_wav(tone, 24000, gain=gain, target_rms=0.006)), "rb") as audio:
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(float) / 32768
        rms_values.append(float(np.sqrt(np.mean(samples[100:-100] ** 2))))
    assert all(0.0055 < rms < 0.0065 for rms in rms_values)
    assert abs(rms_values[0] - rms_values[1]) < 0.0003


def test_downsampling_filters_ultrasonic_energy_instead_of_aliasing_to_speech():
    rate = 32000
    tone = np.sin(2 * np.pi * 12000 * np.arange(rate) / rate).astype(np.float32)
    with wave.open(io.BytesIO(_to_device_wav(tone, rate)), 'rb') as audio:
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(float) / 32768
    assert len(pcm) == 16000
    assert np.sqrt(np.mean(pcm[100:-100] ** 2)) < 0.001


def test_voice_status_changes_only_when_all_local_assets_exist(tmp_path):
    assert voice_status(tmp_path)["engine"] == "sapi-local"
    folder = tmp_path / "models" / "tts"
    folder.mkdir(parents=True)
    for name in ("kokoro-v1.1-zh.int8.onnx", "voices-v1.1-zh.bin"):
        (folder / name).write_bytes(b"test")
    assert voice_status(tmp_path)["ready"] is False
    (folder / "config.json").write_text("{}")
    assert voice_status(tmp_path)["engine"] == "kokoro-local"


def test_voice_status_reports_separate_english_assets(tmp_path):
    folder = tmp_path / "models" / "tts"
    folder.mkdir(parents=True)
    (folder / "kokoro-v1.0.int8.onnx").write_bytes(b"model")
    (folder / "voices-v1.0.bin").write_bytes(b"voices")
    status = voice_status(tmp_path)
    assert status["english_ready"] is True
    assert status["english_voice"] == "Kokoro 英文女声 · af_heart"


def test_superseded_speech_skips_inference(tmp_path):
    with pytest.raises(SynthesisCancelled):
        synthesize_wav("你好", tmp_path, cancelled=lambda: True)


def test_voice_choice_is_persisted_and_paimon_requires_local_readiness(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert selected_voice(tmp_path) == "kokoro"
    with pytest.raises(RuntimeError):
        set_selected_voice(tmp_path, "paimon")
    monkeypatch.setattr("bridge.app.tts.paimon_status", lambda _path: {"ready": True})
    set_selected_voice(tmp_path, "paimon")
    assert selected_voice(tmp_path) == "paimon"
    set_selected_voice(tmp_path, "kokoro")
    assert selected_voice(tmp_path) == "kokoro"


def test_selected_paimon_reports_offline_instead_of_silently_changing_voice(tmp_path, monkeypatch):
    monkeypatch.setattr("bridge.app.tts.selected_voice", lambda _path: "paimon")
    monkeypatch.setattr("bridge.app.tts.paimon_status", lambda _path: {"ready": False})
    monkeypatch.setattr("bridge.app.tts.voice_status", lambda _path: {"ready": True})
    monkeypatch.setattr("bridge.app.tts._kokoro_wav_chunks", lambda *_args: iter([b"kokoro"]))
    with pytest.raises(RuntimeError, match="派蒙"):
        list(synthesize_chunks("你好", tmp_path))


def test_mixed_sentence_routes_chinese_to_paimon_and_english_to_clear_voice(tmp_path, monkeypatch):
    monkeypatch.setattr("bridge.app.tts.selected_voice", lambda _path: "paimon")
    monkeypatch.setattr("bridge.app.tts.paimon_status", lambda _path: {"ready": True})
    calls = []

    def paimon(text, *_args, **kwargs):
        calls.append(("paimon", text))
        return iter([f"P:{text}".encode()])

    def english(text, *_args, **_kwargs):
        calls.append(("english", text))
        return iter([f"E:{text}".encode()])

    monkeypatch.setattr("bridge.app.tts._english_model_files", lambda _path: (tmp_path / "model", tmp_path / "voices"))
    (tmp_path / "model").write_bytes(b"ready")
    (tmp_path / "voices").write_bytes(b"ready")
    monkeypatch.setattr("bridge.app.tts._paimon_wav_chunks", paimon)
    monkeypatch.setattr("bridge.app.tts._english_wav_chunks", english)
    monkeypatch.setattr("bridge.app.tts._stitch_wav_segments", lambda chunks: b"|".join(chunks))
    assert list(synthesize_chunks("你好 Hermes，欢迎回来。", tmp_path)) == [
        "P:你好 |E:Hermes,|P:欢迎回来。".encode()]
    assert list(synthesize_chunks("Hello world", tmp_path)) == [b"E:Hello world"]
    assert calls == [
        ("paimon", "你好 "), ("english", "Hermes,"), ("paimon", "欢迎回来。"),
        ("english", "Hello world"),
    ]


def test_mixed_language_segmenter_keeps_word_groups_and_local_punctuation():
    assert list(_mixed_language_segments("你好，Hello world。再见")) == [
        ("zh", "你好，"), ("en", "Hello world."), ("zh", "再见")]


def test_stitching_overlaps_adjacent_language_clips_without_a_long_gap():
    def make_clip(samples):
        result = io.BytesIO()
        with wave.open(result, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(np.asarray(samples, dtype="<i2").tobytes())
        return result.getvalue()

    clip = make_clip(np.concatenate((np.zeros(800), np.full(1600, 2000), np.zeros(800))))
    stitched = _stitch_wav_segments([clip, clip])
    with wave.open(io.BytesIO(stitched), "rb") as audio:
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
    assert len(samples) < 8000  # Trimmed clip silence and overlapped the voice handoff.
    assert np.any(samples)


def test_paimon_uses_language_specific_frontend_without_changing_voice():
    assert _paimon_language("Hello, Paimon.") == "en"
    assert _paimon_language("你好，Hello！") == "zh"
    assert _paimon_language("你好，欢迎回来。") == "all_zh"


def test_paimon_uses_explicit_local_chinese_inference_and_device_pcm(monkeypatch):
    import json
    from bridge.app.tts import _paimon_wav_chunks

    sample = io.BytesIO()
    with wave.open(sample, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(32000)
        audio.writeframes(np.full(3200, 32767, dtype='<i2').tobytes())
    requests = []

    def local_inference(request, timeout):
        assert request.full_url == 'http://127.0.0.1:9880/'
        requests.append(json.loads(request.data))
        return io.BytesIO(sample.getvalue())

    monkeypatch.setattr('bridge.app.tts.urllib.request.urlopen', local_inference)
    output = list(_paimon_wav_chunks('你好。'))
    assert requests[0]['text_language'] == 'all_zh'
    with wave.open(io.BytesIO(output[0]), 'rb') as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000)
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
        assert 720 < int(pcm.max()) < 800  # Matched speech RMS keeps transitions comfortable.
