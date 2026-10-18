"""Exercise the actual local model, without sending anything to the speaker."""
import os
from pathlib import Path
import sys
import time

root = Path(os.environ["LOCALAPPDATA"]) / "DesktopAiRobot" / "tts-cosyvoice"
repo = root / "repo"
sys.path[:0] = [str(repo), str(repo / "third_party" / "Matcha-TTS")]
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", MODELSCOPE_OFFLINE="1")
import numpy as np
import soundfile as sf
import torch
from cosyvoice.cli.cosyvoice import AutoModel

if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(90, repeat=True)
    started = time.monotonic()
    print("Loading local CosyVoice 3 model...", flush=True)
    model = AutoModel(model_dir=str(root / "models"), fp16=True)
    torch.cuda.empty_cache()
    print("Weights loaded; preparing reference voice...", flush=True)
    prompt = str(repo / "asset" / "zero_shot_prompt.wav")
    model.add_zero_shot_spk("You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。",
                           prompt, "qiuqiu-demo")
    model.add_zero_shot_spk("You are a helpful assistant. 请用广东话表达。<|endofprompt|>",
                           prompt, "qiuqiu-yue")
    print(f"Model loaded in {time.monotonic() - started:.1f}s", flush=True)
    output_dir = root / "auditions"
    output_dir.mkdir(exist_ok=True)
    for mode, text in (
        ("zh", "你好，我是球球，很高兴见到你。"),
        ("en", "Hello, I am your robot. Nice to meet you."),
        ("mixed", "你好，我是球球。Hello, I am your robot. 很高兴见到你。"),
        ("yue", "你好呀，我係球球，好高興識到你。"),
    ):
        started = time.monotonic()
        with torch.inference_mode():
            if mode == "yue":
                result = model.inference_instruct2(text,
                    "You are a helpful assistant. 请用广东话表达。<|endofprompt|>",
                    "", zero_shot_spk_id="qiuqiu-yue", stream=False)
            else:
                result = model.inference_zero_shot(text, "", "", zero_shot_spk_id="qiuqiu-demo", stream=False)
            parts = [item["tts_speech"].float().cpu().numpy().reshape(-1) for item in result]
        samples = np.concatenate(parts)
        assert np.isfinite(samples).all() and samples.size >= model.sample_rate
        assert np.max(np.abs(samples)) > 0.001
        sf.write(output_dir / f"{mode}.wav", samples, model.sample_rate, subtype="PCM_16")
        print(f"{mode}: {len(samples)/model.sample_rate:.1f}s audio in {time.monotonic()-started:.1f}s", flush=True)
    (root / "INSTALL_COMPLETE.txt").write_text("Local synthesis verified", encoding="utf-8")
    faulthandler.cancel_dump_traceback_later()
