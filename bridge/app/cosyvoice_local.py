"""Optional local worker; the Bridge environment never imports torch."""
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
from threading import Lock
import time
import urllib.request
import wave

import numpy as np

VOICES = {"cosyvoice": "球球 · 普通话 / English"}
_process = None
_key = ""
_lock = Lock()
_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def root(data_dir):
    return Path(os.environ.get("LOCALAPPDATA", str(data_dir))) / "DesktopAiRobot" / "tts-cosyvoice"


def status(data_dir):
    directory = root(data_dir)
    installed = all((directory / item).is_file() for item in (
        "INSTALL_COMPLETE.txt", "MODELS_COMPLETE.txt", ".venv/Scripts/python.exe",
        "repo/asset/zero_shot_prompt.wav", "models/llm.pt", "models/flow.pt",
        "models/hift.pt", "models/speech_tokenizer_v3.onnx", "models/campplus.onnx",
        "models/cosyvoice3.yaml", "models/CosyVoice-BlankEN/model.safetensors",
        "models/CosyVoice-BlankEN/config.json", "models/CosyVoice-BlankEN/vocab.json",
        "models/CosyVoice-BlankEN/merges.txt", "models/CosyVoice-BlankEN/tokenizer_config.json"))
    return {"ready": installed, "running": bool(_process and _process.poll() is None)}


def start(data_dir):
    global _process, _key
    with _lock:
        if _process and _process.poll() is None:
            return
        if not status(data_dir)["ready"]:
            raise RuntimeError("球球本地声线尚未安装完成")
        directory = root(data_dir)
        script = Path(__file__).resolve().parents[2] / "scripts" / "cosyvoice_local_server.py"
        _key = secrets.token_urlsafe(32)
        env = os.environ.copy()
        env["ROBOT_COSYVOICE_WORKER_KEY"] = _key
        with (directory / "worker.log").open("ab") as log:
            _process = subprocess.Popen(
                [str(directory / ".venv/Scripts/python.exe"), str(script)],
                cwd=directory / "repo", env=env, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def stop_owned_process(process):
    # Windows venv launchers can have a real Python child. Terminating only the
    # launcher leaves the model, GPU allocation and loopback listener alive.
    if os.name == "nt":
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def stop():
    global _process, _key
    with _lock:
        if _process and _process.poll() is None:
            stop_owned_process(_process)
        _process, _key = None, ""


def synthesize(text, data_dir, voice, cancelled=None):
    start(data_dir)
    deadline = time.monotonic() + 120
    while True:
        if cancelled and cancelled():
            return None
        if not _process or _process.poll() is not None:
            raise RuntimeError("球球本地语音进程启动失败，请查看本机 worker.log")
        try:
            request = urllib.request.Request("http://127.0.0.1:9881/health",
                                             headers={"X-Worker-Key": _key})
            with _http.open(request, timeout=1) as response:
                if json.load(response).get("ready"):
                    break
        except (OSError, ValueError):
            if time.monotonic() >= deadline:
                raise RuntimeError("球球本地声线加载超时，请稍后重试") from None
            time.sleep(0.1)
    request = urllib.request.Request("http://127.0.0.1:9881/synthesize",
        data=json.dumps({"text": text, "mode": "auto"}).encode(),
        headers={"Content-Type": "application/json", "X-Worker-Key": _key})
    try:
        with _http.open(request, timeout=180) as response:
            wav = response.read(24 * 1024 * 1024 + 1)
    except OSError:
        raise RuntimeError("球球本地语音合成失败，请查看本机 worker.log") from None
    if cancelled and cancelled():
        return None
    if len(wav) > 24 * 1024 * 1024:
        raise RuntimeError("本地语音片段过长")
    with wave.open(io.BytesIO(wav), "rb") as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise RuntimeError("本地语音格式无效")
        rate = audio.getframerate()
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32) / 32768
    return samples, rate
