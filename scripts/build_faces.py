"""Turn an open-source character atlas into RLE data the ESP32 keeps in flash.

Run:  .\\.venv\\Scripts\\python.exe scripts\\build_faces.py

Default artwork is the **DeepSeek girl desktop-pet atlas** from
`f0909172434/deepseek-girl-codex-pet` (MIT). It is an 8x11 grid of 192x208
cells: columns 0-5 are the six animation frames, and the rows are poses —
the upstream plugin uses row 0 for idle, row 6 for "waiting for you", row 7 for
"working", and rows 9/10 for the sixteen look-at-the-pointer directions.
Rows 1-5 and 8 are drawn but unwired upstream, so they are unused here too.

Every cell is fitted into FACE_PIXELS, composited on the screen background,
converted to RGB565 and run-length encoded. RLE keeps all eight stills near
100 KB, which fits easily beside the firmware in the 3.19 MB app partition, and
the faces survive a power cut because they are `const` data in flash.

The generated header is checked in, so a normal firmware build needs no network.
Re-run this only when the mapping or the artwork changes.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - the pipeline is a developer tool
    sys.exit("Pillow is required: python -m pip install pillow")

ATLAS_URL = ("https://raw.githubusercontent.com/f0909172434/deepseek-girl-codex-pet/"
             "2572709632b0e81401b9e92994f2c3786c186397/pet/spritesheet.webp")
ATLAS_SHA256 = "234f24a97c18195a00c6093da0090773e675993c169e92e7e13a24c37b323fa2"
ATLAS_BYTES = 2836976
ATTRIBUTION = ("DeepSeek girl desktop-pet atlas by f0909172434 "
               "(github.com/f0909172434/deepseek-girl-codex-pet), MIT")

CELL = (192, 208)
GRID = (8, 11)
FACE_PIXELS = 240
BACKGROUND = (0x00, 0x00, 0x00)
# How the screen is mounted. 90 turns the artwork a quarter turn
# counter-clockwise (the character's head ends up on the left); 0 leaves her
# upright; 270 is a quarter turn clockwise.
ROTATE_CCW = 90

# Atlas rows, per the upstream README ("9 種標準狀態動畫" = rows 0-8):
# row 0 is the idle animation (columns 0-5) plus a neutral gaze baseline in
# column 6; rows 9-10 carry the sixteen look directions.
ROW_NAMES = {
    0: "待機 idle",
    1: "向右移動",
    2: "向左移動",
    3: "揮手 wave",
    4: "跳躍 jump",
    5: "失敗 failure",
    6: "等待使用者 waiting",
    7: "工作中 working",
    8: "審查中 reviewing",
    9: "觀看方向 0-7 look",
    10: "觀看方向 8-15 look",
}

# (identifier, row, column, when the robot shows it)
FACES: tuple[tuple[str, int, int, str], ...] = (
    ("BOOT", 3, 0, "上电就绪，正在等 Bridge 握手（揮手 · wave）"),
    ("READY", 0, 0, "已连接、空闲待命（待機 · idle）"),
    ("SLEEP", 6, 0, "等不到心跳，进入等待（等待使用者 · waiting）"),
    ("LISTEN", 9, 0, "正在收音，抬头听（look up）"),
    ("THINK", 7, 0, "识别 / Hermes 处理中（工作中 · working）"),
    ("SPEAK", 0, 5, "正在朗读回复（待機动画帧）"),
    ("APPROVE", 8, 0, "Hermes 请求工具审批（審查中 · reviewing）"),
    ("ERROR", 5, 0, "音频驱动 / Hermes / 链路出错（失敗 · failure）"),
)


def default_cache() -> Path:
    import os
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "DesktopAiRobot" / "faces" / "spritesheet.webp"


def load_atlas(path: Path, allow_download: bool = True) -> Image.Image:
    if not path.is_file():
        if not allow_download:
            raise SystemExit(f"atlas missing: {path} (run without --offline once)")
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {ATLAS_URL}")
        try:
            with urllib.request.urlopen(ATLAS_URL, timeout=180) as response:
                payload = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SystemExit(f"download failed: {exc}") from None
        if len(payload) != ATLAS_BYTES:
            raise SystemExit(f"atlas truncated: {len(payload)} bytes, expected {ATLAS_BYTES}")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != ATLAS_SHA256:
            raise SystemExit(f"atlas checksum mismatch: {digest}")
        path.write_bytes(payload)
    else:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != ATLAS_SHA256:
            raise SystemExit(f"cached atlas checksum mismatch: {digest}\nDelete {path} and retry.")
    print(f"atlas ok ({ATLAS_SHA256[:16]}…) {path}")
    return Image.open(path).convert("RGBA")


def cell_frame(atlas: Image.Image, row: int, column: int) -> Image.Image:
    columns, rows = GRID
    if not 0 <= row < rows or not 0 <= column < columns:
        raise SystemExit(f"cell {row},{column} is outside the {columns}x{rows} grid")
    width, height = CELL
    box = (column * width, row * height, (column + 1) * width, (row + 1) * height)
    return atlas.crop(box)


def compose(frame: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    width, height = frame.size
    scale = min(FACE_PIXELS / width, FACE_PIXELS / height)
    fitted = frame.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                          Image.LANCZOS)
    canvas = Image.new("RGBA", (FACE_PIXELS, FACE_PIXELS), background + (255,))
    canvas.alpha_composite(fitted, ((FACE_PIXELS - fitted.width) // 2,
                                    (FACE_PIXELS - fitted.height) // 2))
    flat = canvas.convert("RGB")
    if ROTATE_CCW:
        # Exact transposes rather than rotate(): a 90-degree turn of a square
        # is lossless, while rotate() would resample and soften the artwork.
        # Turning the image counter-clockwise sends the character's head to the
        # LEFT of the screen.
        flat = flat.transpose(Image.Transpose.ROTATE_90 if ROTATE_CCW == 90
                              else Image.Transpose.ROTATE_270)
    return flat


def to_rgb565(image: Image.Image) -> list[int]:
    raw = image.tobytes()
    return [((raw[i] & 0xF8) << 8) | ((raw[i + 1] & 0xFC) << 3) | (raw[i + 2] >> 3)
            for i in range(0, len(raw), 3)]


def run_length_encode(pixels: list[int]) -> list[int]:
    """Flat (count, colour) pairs, terminated by (0, 0)."""
    runs: list[int] = []
    previous = pixels[0]
    count = 0
    for value in pixels:
        if value == previous:
            count += 1
        else:
            runs.extend((count, previous))
            previous, count = value, 1
    runs.extend((count, previous))
    runs.extend((0, 0))
    return runs


def format_array(name: str, values: list[int], per_line: int = 8) -> str:
    lines = []
    for start in range(0, len(values), per_line):
        chunk = ", ".join(f"0x{value:04X}" for value in values[start:start + per_line])
        lines.append(f"  {chunk},")
    return f"static const uint16_t FACE_{name}[] = {{\n" + "\n".join(lines) + "\n};\n"


def build(atlas: Image.Image, background: tuple[int, int, int]):
    arrays: list[str] = []
    summary: list[tuple[str, int, int, int, int]] = []
    for name, row, column, _purpose in FACES:
        pixels = to_rgb565(compose(cell_frame(atlas, row, column), background))
        values = run_length_encode(pixels)
        arrays.append(format_array(name, values))
        summary.append((name, row, column, len(values) // 2, len(values) * 2))

    enum = "\n".join(f"  FACE_ID_{name} = {index},"
                     for index, (name, _r, _c, _p) in enumerate(FACES))
    table = "\n".join(f'  {{"{name}", "r{row}c{column}", "{purpose}", FACE_{name}}},'
                      for name, row, column, purpose in FACES)
    legend = "\n".join(f"//   {index:>2}  {name}" for index, name in sorted(ROW_NAMES.items()))
    header = f"""// Generated by scripts/build_faces.py — do not edit by hand.
//
// Artwork: {ATTRIBUTION}
// Faces are {FACE_PIXELS}x{FACE_PIXELS} RGB565, run-length encoded as flat
// (count, colour) pairs terminated by (0, 0). They live in flash, so the robot
// keeps its expressions across reboots and without any network.
//
// Atlas rows (taken from the upstream README, not guessed):
{legend}
#pragma once

#include <stdint.h>

#define FACE_PIXELS {FACE_PIXELS}
#define FACE_COUNT {len(FACES)}

// Face indices shared with bridge/app/faces.py. Keep both in the same order.
enum {{
{enum}
}};

{chr(10).join(arrays)}
struct FaceEntry {{
  const char *name;
  const char *source;   // row/column in the upstream atlas
  const char *purpose;
  const uint16_t *runs;
}};

static const FaceEntry FACES[FACE_COUNT] = {{
{table}
}};
"""
    return header, summary


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "voice-device" / "src" / "faces.h")
    parser.add_argument("--atlas", type=Path, default=default_cache())
    parser.add_argument("--offline", action="store_true", help="never download the atlas")
    parser.add_argument("--background", default="000000",
                        help="screen background behind each face, as RRGGBB")
    arguments = parser.parse_args()

    try:
        background = tuple(int(arguments.background[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return int(bool(sys.stderr.write("--background must be six hex digits, e.g. 000000\n")))

    atlas = load_atlas(arguments.atlas, allow_download=not arguments.offline)
    if atlas.size != (CELL[0] * GRID[0], CELL[1] * GRID[1]):
        raise SystemExit(f"atlas is {atlas.size}, expected "
                         f"{CELL[0] * GRID[0]}x{CELL[1] * GRID[1]}")

    header, summary = build(atlas, background)  # type: ignore[arg-type]
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(header, encoding="utf-8", newline="\n")

    total = sum(row[4] for row in summary)
    for name, row, column, runs, size in summary:
        print(f"  {name:<8} r{row}c{column}  {runs:>5} runs  {size / 1024:>6.1f} KB")
    print(f"\n{len(summary)} faces, {total / 1024:.1f} KB of RLE -> {arguments.output}")
    print(f"Artwork: {ATTRIBUTION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
