"""Decode faces.h back into a PNG contact sheet.

This is the offline stand-in for looking at the robot: it parses the generated
header, runs the same run-length decode the firmware does, and writes a preview
plus an on-screen mock-up. Rebuilding the artwork is the only way to check the
expressions without flashing the board.

Run:  .\\.venv\\Scripts\\python.exe scripts\\render_faces_preview.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - developer tool
    sys.exit("Pillow is required: python -m pip install pillow")

ARRAY_RE = re.compile(r"const uint16_t (FACE_\w+)\[\] = \{(.*?)\n\};", re.S)
VALUE_RE = re.compile(r"0x([0-9A-Fa-f]{4})")
PURPOSE_RE = re.compile(r'\{"(\w+)", "(\w+)", "([^"]*)", FACE_\w+\}')
SCREEN = (240, 320)          # the firmware's LCD_WIDTH x LCD_HEIGHT
BACKGROUND = (0, 0, 0)


def rle_to_rgb565(values: list[int], pixels: int) -> list[int]:
    """Mirror lcdDrawFace(): flat (count, colour) pairs until count == 0."""
    decoded: list[int] = []
    for index in range(0, len(values), 2):
        count, colour = values[index], values[index + 1]
        if count == 0:
            break
        decoded.extend([colour] * count)
    if len(decoded) != pixels:
        raise ValueError(f"decoded {len(decoded)} pixels, expected {pixels}")
    return decoded


def to_rgb(colour: int) -> tuple[int, int, int]:
    return (((colour >> 11) & 0x1F) * 255 // 31,
            ((colour >> 5) & 0x3F) * 255 // 63,
            (colour & 0x1F) * 255 // 31)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--header", type=Path, default=root / "voice-device" / "src" / "faces.h")
    parser.add_argument("--output", type=Path, default=root / "faces-preview.png")
    parser.add_argument("--mock", type=Path, default=root / "faces-on-screen.png")
    arguments = parser.parse_args()

    text = arguments.header.read_text(encoding="utf-8")
    pixels = int(re.search(r"#define FACE_PIXELS (\d+)", text).group(1))  # type: ignore[union-attr]
    purposes = {name: purpose for name, _, purpose in PURPOSE_RE.findall(text)}

    decoded: list[tuple[str, Image.Image]] = []
    for match in ARRAY_RE.finditer(text):
        name = match.group(1)[5:]
        values = [int(value, 16) for value in VALUE_RE.findall(match.group(2))]
        image = Image.new("RGB", (pixels, pixels), BACKGROUND)
        image.putdata([to_rgb(c) for c in rle_to_rgb565(values, pixels * pixels)])
        decoded.append((name, image))
        print(f"  {name:<8} {len(values) // 2:>5} runs -> {pixels}x{pixels} OK")

    if not decoded:
        return int(bool(sys.stderr.write("no face arrays found in the header\n")))

    # Contact sheet: every face, labelled.
    columns = 4
    rows = (len(decoded) + columns - 1) // columns
    cell = pixels + 26
    sheet = Image.new("RGB", (cell * columns, cell * rows), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for index, (name, image) in enumerate(decoded):
        left = (index % columns) * cell + 13
        top = (index // columns) * cell + 8
        sheet.paste(image, (left, top))
        draw.text((left + 4, top + pixels + 6), f"{index} {name}", fill=(220, 220, 220))
    sheet.save(arguments.output)

    # What the panel actually shows: 240x240 centred in a 240x320 window.
    top = (SCREEN[1] - pixels) // 2
    strip = cell - 26
    mock = Image.new("RGB", (SCREEN[0] * len(decoded), SCREEN[1] + 22), (24, 24, 28))
    mock_draw = ImageDraw.Draw(mock)
    for index, (name, image) in enumerate(decoded):
        left = index * SCREEN[0]
        mock_draw.rectangle([left, 0, left + SCREEN[0] - 1, SCREEN[1] - 1], fill=BACKGROUND)
        mock.paste(image, (left, top))
        mock_draw.text((left + 6, SCREEN[1] + 4), f"{name}  ({purposes.get(name, '')[:26]})",
                       fill=(200, 200, 200))
    mock.save(arguments.mock)

    print(f"\ncontact sheet -> {arguments.output}")
    print(f"on-screen mock ({SCREEN[0]}x{SCREEN[1]}, face centred at y={top}) -> {arguments.mock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
