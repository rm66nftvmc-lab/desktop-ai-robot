"""Download the offline Kokoro Chinese model from its official release."""

import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(os.environ["LOCALAPPDATA"]) / "DesktopAiRobot" / "models" / "tts"
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
FILES = {
    "kokoro-v1.1-zh.int8.onnx": 114120125,
    "voices-v1.1-zh.bin": 53815880,
}
CHUNK = 4 * 1024 * 1024


def download_piece(name: str, start: int, end: int) -> Path:
    path = ROOT / f".{name}.{start}.chunk"
    size = end - start + 1
    if path.exists() and path.stat().st_size == size:
        return path
    for attempt in range(6):
        have = path.stat().st_size if path.exists() else 0
        if have > size:
            path.unlink()
            have = 0
        try:
            request = urllib.request.Request(
                f"{BASE}/{name}", headers={"Range": f"bytes={start + have}-{end}"}
            )
            with urllib.request.urlopen(request, timeout=40) as response:
                expected_range = f"bytes {start + have}-{end}/"
                if response.status != 206 or not response.headers.get("Content-Range", "").startswith(expected_range):
                    raise RuntimeError(f"Server did not honor byte range for {name}")
                with path.open("ab") as output:
                    while block := response.read(256 * 1024):
                        output.write(block)
            if path.stat().st_size == size:
                return path
        except (OSError, RuntimeError) as exc:
            if attempt == 5:
                raise RuntimeError(f"Could not download {name} bytes {start}-{end}") from exc
            time.sleep(2 + attempt)
    raise AssertionError("unreachable")


def download_model(name: str, size: int) -> None:
    destination = ROOT / name
    if destination.exists() and destination.stat().st_size == size:
        print(f"Ready: {name}", flush=True)
        return
    ranges = [(start, min(start + CHUNK, size) - 1) for start in range(0, size, CHUNK)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        parts = list(pool.map(lambda pair: download_piece(name, *pair), ranges))
    temp = ROOT / f".{name}.assembling"
    with temp.open("wb") as output:
        for part in parts:
            with part.open("rb") as source:
                while block := source.read(1024 * 1024):
                    output.write(block)
    if temp.stat().st_size != size:
        raise RuntimeError(f"Wrong file size for {name}")
    temp.replace(destination)
    for part in parts:
        part.unlink()
    print(f"Ready: {name} ({size} bytes)", flush=True)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, size in FILES.items():
        download_model(name, size)
    config = ROOT / "config.json"
    if not config.exists():
        url = "https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/raw/main/config.json"
        with urllib.request.urlopen(url, timeout=40) as response:
            data = response.read()
        if not data.startswith(b"{"):
            raise RuntimeError("Invalid Kokoro config")
        temp = ROOT / ".config.json.downloading"
        temp.write_bytes(data)
        temp.replace(config)
    print(f"Voice files installed in {ROOT}", flush=True)


if __name__ == "__main__":
    main()
