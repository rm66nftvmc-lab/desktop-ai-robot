"""Fetch the pinned, Apache-2.0 local CosyVoice 3 inference assets."""
import os
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from download_paimon_models import _download, _files

ROOT = Path(os.environ["LOCALAPPDATA"]) / "DesktopAiRobot" / "tts-cosyvoice"
REPO = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
REVISION = "29e01c4e8d000f4bcd70751be16fa94bf3d85a18"
FILES = ["README.md", "cosyvoice3.yaml", "campplus.onnx", "flow.pt", "hift.pt",
         "llm.pt", "speech_tokenizer_v3.onnx", "CosyVoice-BlankEN/config.json",
         "CosyVoice-BlankEN/model.safetensors",
         "CosyVoice-BlankEN/generation_config.json", "CosyVoice-BlankEN/merges.txt",
         "CosyVoice-BlankEN/tokenizer_config.json", "CosyVoice-BlankEN/vocab.json"]


def fetch_model(name, size, sha):
    """Use the official domestic mirror; validate against pinned HF metadata."""
    target = ROOT / "models" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not sha:
        _download(REPO, REVISION, name, target, size, sha)
        return
    if target.is_file() and target.stat().st_size == size:
        with target.open("rb") as existing:
            if not sha or hashlib.file_digest(existing, "sha256").hexdigest() == sha:
                return
    url = f"https://modelscope.cn/models/{REPO}/resolve/master/{name}"
    block = 32 * 1024 * 1024
    chunks = []
    def part(index):
        start = index * block
        end = min(size - 1, start + block - 1)
        path = target.with_name(target.name + f".part{index}")
        if not path.is_file() or path.stat().st_size != end - start + 1:
            subprocess.run(["curl.exe", "-sS", "-L", "--fail", "--retry", "4",
                            "--retry-all-errors", "--retry-delay", "2",
                            "--max-time", "240", "-r", f"{start}-{end}",
                            "-o", str(path), url], check=True)
        if path.stat().st_size != end - start + 1:
            raise RuntimeError(f"Invalid range response: {name}, part {index}")
        return path
    with ThreadPoolExecutor(max_workers=8) as pool:
        chunks = list(pool.map(part, range((size + block - 1) // block)))
    temporary = target.with_name(target.name + ".verified-download")
    digest = hashlib.sha256()
    with temporary.open("wb") as out:
        for chunk in chunks:
            with chunk.open("rb") as source:
                for data in iter(lambda: source.read(1024 * 1024), b""):
                    out.write(data)
                    digest.update(data)
    if sha and digest.hexdigest() != sha:
        temporary.unlink()
        for chunk in chunks:
            chunk.unlink()
        raise RuntimeError(f"SHA-256 mismatch: {name}")
    temporary.replace(target)
    for chunk in chunks:
        chunk.unlink()
    print(f"Verified {name}: {size:,} bytes", flush=True)


def main():
    metadata = _files(REPO, REVISION, FILES)
    def fetch(name):
        size, sha = metadata[name]
        fetch_model(name, size, sha)
    for name in FILES:
        fetch(name)
    (ROOT / "MODELS_COMPLETE.txt").write_text(REVISION, encoding="utf-8")


if __name__ == "__main__":
    main()
