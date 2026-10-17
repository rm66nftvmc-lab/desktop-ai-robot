"""Offline Chinese TTS, converted to the device's 16 kHz PCM WAV format."""

import io
import os
import re
import json
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
import wave
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Callable

import numpy as np

VOICE_NAME = "Kokoro 中文女声 · zf_001"
ENGLISH_VOICE_NAME = "Kokoro 英文女声 · af_heart"
PAIMON_VOICE_NAME = "派蒙 · GPT-SoVITS（本地试听）"
_PAIMON_API = "http://127.0.0.1:9880/"
_INFERENCE_LOCK = Lock()
_PAIMON_PROCESS: subprocess.Popen | None = None
_ARPA_IPA = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "EH": "ɛ", "ER": "ɜɹ",
    "EY": "eɪ", "F": "f", "G": "ɡ", "HH": "h", "IH": "ɪ", "IY": "i",
    "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ",
    "OW": "oʊ", "OY": "ɔɪ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ",
    "T": "t", "TH": "θ", "UH": "ʊ", "UW": "u", "V": "v", "W": "w",
    "Y": "j", "Z": "z", "ZH": "ʒ",
}
_ENGLISH_WEAK_FORMS = {
    # Common function words are usually unstressed in conversational speech.
    # CMUdict's citation forms mark many of these with primary stress, which
    # makes Kokoro over-emphasize every word when passed through directly.
    "a": ("AH0",), "an": ("AH0", "N"), "the": ("DH", "AH0"),
    "and": ("AH0", "N", "D"), "or": ("ER0",), "for": ("F", "ER0"),
    "to": ("T", "AH0"), "of": ("AH0", "V"), "as": ("AH0", "Z"),
    "at": ("AH0", "T"), "from": ("F", "R", "AH0", "M"),
    "with": ("W", "IH0", "TH"), "this": ("DH", "IH0", "S"),
    "that": ("DH", "AH0", "T"), "these": ("DH", "IY0", "Z"),
    "those": ("DH", "OW0", "Z"), "is": ("IH0", "Z"),
    "are": ("ER0",), "was": ("W", "AH0", "Z"),
    "were": ("W", "ER0"), "be": ("B", "IY0"), "been": ("B", "IH0", "N"),
    "being": ("B", "IY0", "IH0", "NG"), "can": ("K", "AH0", "N"),
    "could": ("K", "UH0", "D"), "would": ("W", "UH0", "D"),
    "should": ("SH", "UH0", "D"), "will": ("W", "IH0", "L"),
    "do": ("D", "UW0"), "does": ("D", "AH0", "Z"),
    "have": ("HH", "AH0", "V"), "has": ("HH", "AH0", "Z"),
    "you": ("Y", "UW0"), "your": ("Y", "ER0"),
    "we": ("W", "IY0"), "he": ("HH", "IY0"), "she": ("SH", "IY0"),
    "they": ("DH", "EY0"), "them": ("DH", "EH0", "M"),
    "it": ("IH0", "T"), "its": ("IH0", "T", "S"),
}


class SynthesisCancelled(Exception):
    """A newer playback request replaced this one."""


def _model_files(data_dir: Path) -> tuple[Path, Path, Path]:
    folder = data_dir / "models" / "tts"
    return (folder / "kokoro-v1.1-zh.int8.onnx",
            folder / "voices-v1.1-zh.bin", folder / "config.json")


def _english_model_files(data_dir: Path) -> tuple[Path, Path]:
    folder = data_dir / "models" / "tts"
    return folder / "kokoro-v1.0.int8.onnx", folder / "voices-v1.0.bin"


def voice_status(data_dir: Path) -> dict:
    ready = all(path.is_file() for path in _model_files(data_dir))
    english_ready = all(path.is_file() for path in _english_model_files(data_dir))
    selected = selected_voice(data_dir)
    paimon_ready = paimon_status(data_dir)["ready"]
    active = selected
    current = PAIMON_VOICE_NAME if active == "paimon" else (
        VOICE_NAME if ready else "Windows 中文语音")
    return {"name": current, "ready": ready, "english_ready": english_ready,
            "english_voice": ENGLISH_VOICE_NAME,
            "engine": "gpt-sovits-multilingual-local" if active == "paimon" else
                      "kokoro-local" if ready else "sapi-local",
            "selected": selected, "active": active, "paimon_ready": paimon_ready,
            "voices": [{"id": "kokoro", "name": VOICE_NAME, "ready": ready},
                       {"id": "paimon", "name": PAIMON_VOICE_NAME, "ready": paimon_ready}]}


def selected_voice(data_dir: Path) -> str:
    try:
        value = json.loads((data_dir / "tts-voice.json").read_text(encoding="utf-8"))
        return "paimon" if value.get("voice") == "paimon" else "kokoro"
    except (OSError, ValueError, AttributeError):
        return "kokoro"


def set_selected_voice(data_dir: Path, voice: str) -> None:
    if voice not in {"kokoro", "paimon"}:
        raise ValueError("Unknown voice")
    if voice == "paimon" and not paimon_status(data_dir)["ready"]:
        raise RuntimeError("派蒙本地语音引擎或模型尚未就绪")
    data_dir.mkdir(parents=True, exist_ok=True)
    temporary = data_dir / "tts-voice.json.tmp"
    temporary.write_text(json.dumps({"voice": voice}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(data_dir / "tts-voice.json")


def paimon_status(data_dir: Path) -> dict:
    root = Path(os.environ.get("LOCALAPPDATA", str(data_dir))) / "DesktopAiRobot" / "tts-paimon"
    model = root / "models" / "派蒙-e10.ckpt"
    sovits = root / "models" / "派蒙_e10_s19390.pth"
    reference = root / "models" / "平静-好耶！《特尔克西的奇幻历险》出发咯！.wav"
    code_ready = ((root / "repo" / "api.py").is_file()
                  and (root / ".venv" / "Scripts" / "python.exe").is_file()
                  and (root / "INSTALL_COMPLETE.txt").is_file())
    pretrained = root / "repo" / "GPT_SoVITS" / "pretrained_models"
    assets = (model, sovits, reference,
              root / "repo" / "GPT_SoVITS" / "text" / "G2PWModel" / "g2pW.onnx",
              pretrained / "chinese-hubert-base" / "pytorch_model.bin",
              pretrained / "chinese-roberta-wwm-ext-large" / "pytorch_model.bin")
    assets_ready = all(path.is_file() for path in assets)
    running = False
    if code_ready and assets_ready:
        try:
            with socket.create_connection(("127.0.0.1", 9880), timeout=0.12):
                running = True
        except OSError:
            pass
    return {"ready": code_ready and assets_ready and running,
            "installed": code_ready and assets_ready, "running": running,
            "note": "派蒙声线在本机合成中文、英文和中英混合语句。"}


def start_paimon_service(data_dir: Path) -> None:
    global _PAIMON_PROCESS
    root = Path(os.environ.get("LOCALAPPDATA", str(data_dir))) / "DesktopAiRobot" / "tts-paimon"
    status = paimon_status(data_dir)
    if not status["installed"]:
        return
    if status["running"] or (_PAIMON_PROCESS and _PAIMON_PROCESS.poll() is None):
        return
    repo = root / "repo"
    models = root / "models"
    pretrained = repo / "GPT_SoVITS" / "pretrained_models"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = (logs / "api.log").open("ab")
    env = os.environ.copy()
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", MODELSCOPE_OFFLINE="1")
    args = [
        str(root / ".venv" / "Scripts" / "python.exe"), "api.py",
        "-a", "127.0.0.1", "-p", "9880", "-d", "cuda", "-hp",
        "-g", str(models / "派蒙-e10.ckpt"),
        "-s", str(models / "派蒙_e10_s19390.pth"),
        "-dr", str(models / "平静-好耶！《特尔克西的奇幻历险》出发咯！.wav"),
        "-dt", "好耶！《特尔克西的奇幻历险》出发咯！", "-dl", "all_zh",
        "-hb", str(pretrained / "chinese-hubert-base"),
        "-b", str(pretrained / "chinese-roberta-wwm-ext-large"),
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        _PAIMON_PROCESS = subprocess.Popen(args, cwd=repo, env=env,
                                           stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=flags)
    except OSError:
        log.close()
        raise
    log.close()


def stop_paimon_service() -> None:
    global _PAIMON_PROCESS
    if _PAIMON_PROCESS and _PAIMON_PROCESS.poll() is None:
        _PAIMON_PROCESS.terminate()
        try:
            _PAIMON_PROCESS.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _PAIMON_PROCESS.kill()
    _PAIMON_PROCESS = None


def warm_voice(data_dir: Path) -> None:
    if voice_status(data_dir)["ready"]:
        _load_kokoro(*map(str, _model_files(data_dir)))
        _english_dictionary()
    if all(path.is_file() for path in _english_model_files(data_dir)):
        _load_english_kokoro(*map(str, _english_model_files(data_dir)))


@lru_cache(maxsize=1)
def _load_kokoro(model: str, voices: str, config: str):
    from kokoro_onnx import Kokoro
    from misaki import zh

    engine = Kokoro(model, voices, vocab_config=config)
    return engine, zh.ZHG2P(version="1.1", en_callable=_english_phonemes)


@lru_cache(maxsize=1)
def _load_english_kokoro(model: str, voices: str):
    from kokoro_onnx import Kokoro

    return Kokoro(model, voices)


@lru_cache(maxsize=1)
def _english_dictionary():
    import cmudict
    return cmudict.dict()


def _english_phonemes(text: str) -> str:
    """Convert English locally with CMU pronunciations, preserving punctuation."""
    dictionary = _english_dictionary()
    result = []
    for token in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|[^A-Za-z]+", text):
        if not re.fullmatch(r"[A-Za-z]+(?:'[A-Za-z]+)?", token):
            result.append(token)
            continue
        word = token
        # Spell short initialisms so API/GPT remain intelligible in mixed text.
        is_initialism = word.isupper() and 1 < len(word) <= 6
        parts = list(word) if is_initialism else [word]
        word_phones = []
        for part in parts:
            weak_form = not is_initialism and part.lower() in _ENGLISH_WEAK_FORMS
            phones = (list(_ENGLISH_WEAK_FORMS[part.lower()]) if weak_form
                      else dictionary.get(part.lower()))
            if weak_form:
                pass
            elif len(part) == 1:
                if part.lower() == "a" and is_initialism:
                    phones = ["EY1"]
                else:
                    # CMU gives the word "a" its weak article pronunciation
                    # (AH0) first. Preserve that instead of always spelling it
                    # as the letter name "A" (EY1).
                    phones = (phones or [["AH0"]])[0]
            elif not phones:
                # Unknown names are still spoken, letter by letter.
                phones = [phone for letter in part
                          for phone in (["EY1"] if letter.lower() == "a"
                                        else dictionary.get(letter.lower(), [["AH0"]])[0])]
            else:
                phones = phones[0]
            word_phones.append("".join(("ˈ" if p.endswith("1") else "") +
                                       ("ə" if p == "AH0" else "əɹ" if p == "ER0"
                                        else _ARPA_IPA.get(re.sub(r"\d$", "", p), ""))
                                       for p in phones))
        result.append(" ".join(word_phones))
    return "".join(result).strip()


def _to_device_wav(samples: np.ndarray, sample_rate: int, *, gain: float = 0.12,
                   target_rms: float | None = None) -> bytes:
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    if sample_rate != 16000:
        # A direct sample drop aliases high-pitched voices into audible buzz.
        # FFmpeg's local resampler low-passes before reducing the sample rate.
        import av

        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="flt", layout="mono")
        frame.sample_rate = sample_rate
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
        converted = resampler.resample(frame) + resampler.resample(None)
        samples = np.concatenate([part.to_ndarray().reshape(-1) for part in converted])
    samples = np.array(samples, dtype=np.float32, copy=True)
    fade = min(80, len(samples) // 2)
    if fade:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        samples[:fade] *= ramp
        samples[-fade:] *= ramp[::-1]
    samples *= gain
    if target_rms is not None and target_rms > 0:
        # Normalize the final device signal, after voice-specific gain. This
        # keeps English and Paimon at the same perceived speech level even
        # though their source models and configured gains differ.
        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        active = np.abs(samples) >= max(0.001, peak * 0.08)
        active_rms = float(np.sqrt(np.mean(np.square(samples[active])))) if np.any(active) else 0.0
        if active_rms > 1e-6:
            scale = min(max(target_rms / active_rms, 0.01), 3.0)
            samples *= scale
            # Keep headroom before the device volume slider and avoid sharp
            # peaks when a quiet source needs substantial normalization.
            peak = float(np.max(np.abs(samples)))
            if peak > 0.06:
                samples *= 0.06 / peak
    # This normalized baseline is what the web volume slider scales from 0 to 100%.
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(pcm.tobytes())
    return output.getvalue()


def _synthesize_kokoro(text: str, data_dir: Path,
                       cancelled: Callable[[], bool] | None = None) -> bytes:
    chunks = list(_kokoro_wav_chunks(text, data_dir, cancelled))
    if not chunks:
        raise ValueError("No speech could be generated from this text")
    pcm = b"".join(_wav_pcm(chunk) for chunk in chunks)
    return _pcm_wav(pcm)


def _wav_pcm(wav: bytes) -> bytes:
    with wave.open(io.BytesIO(wav), "rb") as audio:
        return audio.readframes(audio.getnframes())


def _pcm_wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(pcm)
    return output.getvalue()


def _speech_parts(text: str):
    first = True
    for sentence in re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?", text):
        sentence = sentence.strip()
        while sentence:
            limit = 18 if first else 60
            if len(sentence) <= limit:
                part, sentence = sentence, ""
            else:
                boundary = limit
                # Keep English words intact where there is a nearby space.
                if sentence[boundary - 1:boundary].isascii() and sentence[boundary:boundary + 1].isascii():
                    space = sentence.rfind(" ", 0, boundary)
                    if space > 4:
                        boundary = space
                part, sentence = sentence[:boundary], sentence[boundary:].lstrip()
            if part.strip():
                yield part.strip()
                first = False


def _kokoro_wav_chunks(text: str, data_dir: Path,
                       cancelled: Callable[[], bool] | None = None):
    model_path, voices_path, config_path = _model_files(data_dir)
    if cancelled and cancelled():
        raise SynthesisCancelled
    with _INFERENCE_LOCK:
        if cancelled and cancelled():
            raise SynthesisCancelled
        model, g2p = _load_kokoro(str(model_path), str(voices_path), str(config_path))
        generated = False
        for part in _speech_parts(text):
            if cancelled and cancelled():
                raise SynthesisCancelled
            phonemes, _ = g2p(part)
            if not phonemes:
                continue
            audio, rate = model.create(phonemes, voice="zf_001", speed=1.0,
                                       is_phonemes=True)
            if cancelled and cancelled():
                raise SynthesisCancelled
            if rate != 24000:
                raise RuntimeError(f"Unexpected Kokoro sample rate: {rate}")
            if generated:
                audio = np.concatenate((np.zeros(2400, dtype=np.float32), audio))
            generated = True
            yield _to_device_wav(np.asarray(audio, dtype=np.float32), 24000)


def _english_wav_chunks(text: str, data_dir: Path,
                        cancelled: Callable[[], bool] | None = None):
    model_path, voices_path = _english_model_files(data_dir)
    if not model_path.is_file() or not voices_path.is_file():
        raise RuntimeError("本地英文语音模型未安装，请运行 scripts/download_kokoro_english.py")
    if cancelled and cancelled():
        raise SynthesisCancelled
    with _INFERENCE_LOCK:
        if cancelled and cancelled():
            raise SynthesisCancelled
        model = _load_english_kokoro(str(model_path), str(voices_path))
        generated = False
        for part in _speech_parts(text):
            if cancelled and cancelled():
                raise SynthesisCancelled
            phonemes = _english_phonemes(part)
            audio, rate = model.create(phonemes, voice="af_heart", speed=1.0,
                                       is_phonemes=True)
            if cancelled and cancelled():
                raise SynthesisCancelled
            if rate != 24000:
                raise RuntimeError(f"Unexpected English Kokoro sample rate: {rate}")
            if generated:
                audio = np.concatenate((np.zeros(2400, dtype=np.float32), audio))
            generated = True
            # Kokoro's English voice is quieter than the selected Paimon
            # Chinese voice. Raise only English by ~4.4 dB so both remain
            # intelligible at the same device volume setting.
            yield _to_device_wav(np.asarray(audio, dtype=np.float32), 24000,
                                 gain=0.20, target_rms=0.0225)


def synthesize_chunks(text: str, data_dir: Path,
                      cancelled: Callable[[], bool] | None = None):
    if selected_voice(data_dir) == "paimon":
        if not paimon_status(data_dir)["ready"]:
            raise RuntimeError("派蒙本地语音服务未就绪，请稍后重试或手动切换声线")
        # Keep Paimon for Chinese and use the clearer local female Kokoro voice
        # for English. Stitch short language segments together so a mixed
        # sentence does not sound like two separate playback clips.
        yield from _mixed_paimon_wav_chunks(text, data_dir, cancelled)
        return
    if voice_status(data_dir)["ready"]:
        yield from _kokoro_wav_chunks(text, data_dir, cancelled)
    else:
        yield synthesize_wav(text, data_dir, cancelled)


def _paimon_language(text: str) -> str:
    has_english = bool(re.search(r"[A-Za-z]", text))
    has_chinese = bool(re.search(r"[\u3400-\u9fff]", text))
    return "zh" if has_english and has_chinese else "en" if has_english else "all_zh"


_ENGLISH_SPAN = re.compile(
    r"(?<![A-Za-z])[A-Za-z]+(?:['’][A-Za-z]+)*(?:[ \t]+[A-Za-z]+(?:['’][A-Za-z]+)*)*"
    r"[,.!?;:，。！？；：]*"
)


def _mixed_language_segments(text: str):
    """Yield (language, text) spans without splitting English word groups."""
    cursor = 0
    for match in _ENGLISH_SPAN.finditer(text):
        if match.start() > cursor:
            chinese = text[cursor:match.start()]
            if chinese.strip():
                yield "zh", chinese
        english = match.group().translate(str.maketrans({
            "，": ",", "。": ".", "！": "!", "？": "?", "；": ";", "：": ":",
        }))
        if english.strip():
            yield "en", english
        cursor = match.end()
    if cursor < len(text) and text[cursor:].strip():
        yield "zh", text[cursor:]


def _wav_samples(wav: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
            raise RuntimeError("语音片段必须是 16 kHz 单声道 PCM16")
        return np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32)


def _stitch_wav_segments(chunks: list[bytes], *, crossfade_ms: int = 18) -> bytes:
    """Trim codec silence and join adjacent language clips with a tiny overlap."""
    if not chunks:
        return b""
    samples = np.concatenate([_wav_samples(chunk) for chunk in chunks]) if len(chunks) == 1 else None
    if samples is None:
        pieces = []
        for chunk in chunks:
            part = _wav_samples(chunk)
            if not part.size:
                continue
            peak = float(np.max(np.abs(part)))
            threshold = max(48.0, peak * 0.008)
            active = np.flatnonzero(np.abs(part) >= threshold)
            if active.size:
                part = part[max(0, int(active[0]) - 160):min(len(part), int(active[-1]) + 321)]
            pieces.append(part)
        if not pieces:
            return b""
        samples = pieces[0]
        overlap_max = round(16000 * crossfade_ms / 1000)
        for part in pieces[1:]:
            overlap = min(overlap_max, len(samples) // 4, len(part) // 4)
            if overlap:
                fade_out = np.linspace(1.0, 0.0, overlap, endpoint=False, dtype=np.float32)
                fade_in = 1.0 - fade_out
                middle = samples[-overlap:] * fade_out + part[:overlap] * fade_in
                samples = np.concatenate((samples[:-overlap], middle, part[overlap:]))
            else:
                samples = np.concatenate((samples, part))
    output = io.BytesIO()
    pcm = np.clip(samples, -32768, 32767).astype("<i2")
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(pcm.tobytes())
    return output.getvalue()


def _mixed_paimon_wav_chunks(text: str, data_dir: Path,
                             cancelled: Callable[[], bool] | None = None):
    english_ready = all(path.is_file() for path in _english_model_files(data_dir))
    for part in _speech_parts(text):
        if cancelled and cancelled():
            raise SynthesisCancelled
        clips = []
        for language, segment in _mixed_language_segments(part):
            if cancelled and cancelled():
                raise SynthesisCancelled
            if language == "en" and english_ready:
                clips.extend(_english_wav_chunks(segment, data_dir, cancelled))
            else:
                clips.extend(_paimon_wav_chunks(segment, cancelled))
        stitched = _stitch_wav_segments(clips)
        if stitched:
            yield stitched


def _paimon_wav_chunks(text: str, cancelled: Callable[[], bool] | None = None):
    for part in _speech_parts(text):
        if cancelled and cancelled():
            raise SynthesisCancelled
        text_language = _paimon_language(part)
        request = urllib.request.Request(
            _PAIMON_API,
            data=json.dumps({"text": part, "text_language": text_language,
                             "cut_punc": "，。！？；"}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                wav = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"派蒙本地语音合成失败：{exc}") from exc
        if cancelled and cancelled():
            raise SynthesisCancelled
        with wave.open(io.BytesIO(wav), "rb") as audio:
            if audio.getsampwidth() != 2:
                raise RuntimeError("派蒙语音返回了非 16 位 PCM 音频")
            channels, rate = audio.getnchannels(), audio.getframerate()
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)
        yield _to_device_wav(samples.astype(np.float32) / 32768.0, rate,
                             gain=0.12, target_rms=0.0225)


def _synthesize_sapi(text: str, data_dir: Path) -> bytes:
    import comtypes
    import comtypes.client

    comtypes.CoInitialize()
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=data_dir, delete=False) as file:
            path = Path(file.name)
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        voices = voice.GetVoices()
        for index in range(voices.Count):
            candidate = voices.Item(index)
            if "Chinese (Simplified)" in candidate.GetDescription():
                voice.Voice = candidate
                break
        else:
            raise RuntimeError("No local Chinese Windows voice is installed")
        stream = comtypes.client.CreateObject("SAPI.SpFileStream")
        stream.Open(str(path), 3, False)
        voice.AudioOutputStream = stream
        voice.Speak(text)
        stream.Close()

        with wave.open(str(path), "rb") as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise RuntimeError("Unexpected SAPI audio format")
            rate = audio.getframerate()
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
        return _to_device_wav(samples.astype(np.float32) / 32768, rate)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
        comtypes.CoUninitialize()


def synthesize_wav(text: str, data_dir: Path,
                   cancelled: Callable[[], bool] | None = None) -> bytes:
    if cancelled and cancelled():
        raise SynthesisCancelled
    if voice_status(data_dir)["ready"]:
        return _synthesize_kokoro(text, data_dir, cancelled)
    wav = _synthesize_sapi(text, data_dir)
    if cancelled and cancelled():
        raise SynthesisCancelled
    return wav
