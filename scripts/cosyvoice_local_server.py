"""Private loopback worker for the optional, offline CosyVoice 3 engine."""
import io
import os
from pathlib import Path
import secrets
import sys
from threading import Lock

ROOT = Path(os.environ["LOCALAPPDATA"]) / "DesktopAiRobot" / "tts-cosyvoice"
REPO = ROOT / "repo"
sys.path[:0] = [str(REPO), str(REPO / "third_party" / "Matcha-TTS")]
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", MODELSCOPE_OFFLINE="1")

import numpy as np
import soundfile as sf
import torch
from cosyvoice.cli.cosyvoice import AutoModel
from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

KEY = os.environ["ROBOT_COSYVOICE_WORKER_KEY"]
model = AutoModel(model_dir=str(ROOT / "models"), fp16=True)
torch.cuda.empty_cache()
reference = str(REPO / "asset" / "zero_shot_prompt.wav")
model.add_zero_shot_spk(
    "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。",
    reference, "qiuqiu-demo")
model.add_zero_shot_spk(
    "You are a helpful assistant. 请用广东话表达。<|endofprompt|>",
    reference, "qiuqiu-yue")
lock = Lock()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    mode: str = "auto"


def authorized(key):
    if not key or not secrets.compare_digest(key, KEY):
        raise HTTPException(401, "Unauthorized")


@app.get("/health")
def health(x_worker_key: str | None = Header(default=None)):
    authorized(x_worker_key)
    return {"ready": True, "engine": "cosyvoice3-local"}


@app.post("/synthesize")
def synthesize(body: Speech, x_worker_key: str | None = Header(default=None)):
    authorized(x_worker_key)
    if body.mode not in {"auto", "yue"}:
        raise HTTPException(400, "Unsupported language mode")
    # Reject special control tokens supplied in conversation text.
    text = body.text.replace("<|", "").replace("|>", "")
    with lock, torch.inference_mode():
        if body.mode == "yue":
            output = model.inference_instruct2(
                text, "You are a helpful assistant. 请用广东话表达。<|endofprompt|>",
                "", zero_shot_spk_id="qiuqiu-yue", stream=False)
        else:
            output = model.inference_zero_shot(
                text, "", "", zero_shot_spk_id="qiuqiu-demo", stream=False)
        parts = [item["tts_speech"].float().cpu().numpy().reshape(-1) for item in output]
        if not parts:
            raise HTTPException(503, "No speech generated")
        audio = np.concatenate(parts)
        if not np.isfinite(audio).all():
            raise HTTPException(503, "Invalid audio generated")
        wav = io.BytesIO()
        sf.write(wav, audio, model.sample_rate, format="WAV", subtype="PCM_16")
    return Response(wav.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9881, access_log=False)
