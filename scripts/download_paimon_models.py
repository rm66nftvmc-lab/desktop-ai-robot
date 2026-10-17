"""Download and checksum the optional, local-only Paimon GPT-SoVITS assets."""

import hashlib
import json
import os
import subprocess
import shutil
import zipfile
from pathlib import Path

from huggingface_hub import HfApi


ROOT = Path(os.environ["LOCALAPPDATA"]) / "DesktopAiRobot" / "tts-paimon"
VOICE_REPO = "UnlimitedBurst/GPT-SoVITS"
VOICE_REVISION = "7e5d75b5b5b63386a024df6c2bdb119445c837d2"
BASE_REPO = "lj1995/GPT-SoVITS"
BASE_REVISION = "8f8857563c040d542de108a2c18b0425abd6c9c5"
G2PW_REPO = "XXXXRT/GPT-SoVITS-Pretrained"
G2PW_REVISION = "0c47645e02a7bc3688d7b263b0042c81e3cd82cd"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(repo: str, revision: str, name: str, destination: Path,
              size: int | None, sha256: str | None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and size is not None and destination.stat().st_size == size:
        if sha256 is None or _sha256(destination) == sha256:
            print(f"Verified existing: {name}", flush=True)
            return
    temporary = destination.with_name(destination.name + ".download")
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
    subprocess.run([
        "curl.exe", "-L", "--fail", "--retry", "5", "--retry-all-errors",
        "--retry-delay", "2", "-C", "-", "-o", str(temporary), url,
    ], check=True)
    if size is not None and temporary.stat().st_size != size:
        raise RuntimeError(f"Size mismatch for {name}: expected {size}, got {temporary.stat().st_size}")
    if sha256 is not None and _sha256(temporary) != sha256:
        raise RuntimeError(f"SHA-256 mismatch for {name}")
    temporary.replace(destination)
    print(f"Verified downloaded: {name} ({destination.stat().st_size:,} bytes)", flush=True)


def _files(repo: str, revision: str, names: list[str]) -> dict[str, tuple[int, str | None]]:
    info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    by_name = {item.rfilename: item for item in info.siblings}
    missing = [name for name in names if name not in by_name]
    if missing:
        raise RuntimeError(f"Pinned model revision is missing: {missing}")
    result = {}
    for name in names:
        item = by_name[name]
        sha = item.lfs.sha256 if item.lfs else None
        result[name] = (item.size, sha)
    return result


def main() -> None:
    voice_files = {
        "原神（已更新4.8）/派蒙/派蒙-e10.ckpt": "派蒙-e10.ckpt",
        "原神（已更新4.8）/派蒙/派蒙_e10_s19390.pth": "派蒙_e10_s19390.pth",
        "原神（已更新4.8）/派蒙/平静-好耶！《特尔克西的奇幻历险》出发咯！.wav":
            "平静-好耶！《特尔克西的奇幻历险》出发咯！.wav",
    }
    info = _files(VOICE_REPO, VOICE_REVISION, list(voice_files))
    for remote, local in voice_files.items():
        size, sha = info[remote]
        _download(VOICE_REPO, VOICE_REVISION, remote, ROOT / "models" / local, size, sha)

    base_files = [
        "chinese-hubert-base/config.json",
        "chinese-hubert-base/preprocessor_config.json",
        "chinese-hubert-base/pytorch_model.bin",
        "chinese-roberta-wwm-ext-large/config.json",
        "chinese-roberta-wwm-ext-large/pytorch_model.bin",
        "chinese-roberta-wwm-ext-large/tokenizer.json",
    ]
    base_info = _files(BASE_REPO, BASE_REVISION, base_files)
    pretrained = ROOT / "repo" / "GPT_SoVITS" / "pretrained_models"
    for name in base_files:
        size, sha = base_info[name]
        _download(BASE_REPO, BASE_REVISION, name, pretrained / name, size, sha)

    # The v2 Chinese frontend also needs its local polyphonic-pronunciation model.
    g2pw_info = _files(G2PW_REPO, G2PW_REVISION, ["G2PWModel.zip"])
    size, sha = g2pw_info["G2PWModel.zip"]
    archive = ROOT / "models" / "G2PWModel.zip"
    _download(G2PW_REPO, G2PW_REVISION, "G2PWModel.zip", archive, size, sha)
    model_dir = ROOT / "repo" / "GPT_SoVITS" / "text" / "G2PWModel"
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if entry.is_dir():
                continue
            relative = Path(entry.filename)
            if relative.parts[0] in {"G2PWModel", "G2PWModel_1.1"}:
                relative = Path(*relative.parts[1:])
            destination = (model_dir / relative).resolve()
            if not destination.is_relative_to(model_dir.resolve()):
                raise RuntimeError(f"Unsafe G2PW archive path: {entry.filename}")
            if destination.is_file() and destination.stat().st_size == entry.file_size:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)

    manifest = {
        "voice_repo": VOICE_REPO, "voice_revision": VOICE_REVISION,
        "base_repo": BASE_REPO, "base_revision": BASE_REVISION,
        "g2pw_repo": G2PW_REPO, "g2pw_revision": G2PW_REVISION,
        "files": {name: {"size": size, "sha256": sha} for name, (size, sha) in
                  {**{n: info[n] for n in info}, **base_info, **g2pw_info}.items()},
    }
    (ROOT / "model-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    (ROOT / "MODEL_NOTICE.txt").write_text(
        "派蒙 GPT-SoVITS 模型来源：UnlimitedBurst/GPT-SoVITS，固定提交 "
        f"{VOICE_REVISION}。分享者注明自己并非原作者，并提供侵权联系渠道；"
        "原作者的 GPT-SoVITS-STAR 仓库注明严禁商用。仅用于本机个人试听，"
        "不上传音频或文本，不用于商业用途或对外发布。PyTorch checkpoint 会经官方"
        "GPT-SoVITS 推理代码加载；仍应把非官方转存模型视为不可信来源。\n"
        f"推理底模：{BASE_REPO}@{BASE_REVISION}。\n",
        encoding="utf-8",
    )
    print(f"All Paimon and GPT-SoVITS assets verified under {ROOT}", flush=True)


if __name__ == "__main__":
    main()
