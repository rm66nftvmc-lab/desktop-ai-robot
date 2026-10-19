"""Validate the only on-device texture and its RGB565 transport representation."""
from pathlib import Path
import re
import numpy as np


def test_emotion_ball_texture_fits_the_framebuffer_and_wire_byte_order():
    source = (Path(__file__).resolve().parents[2] / 'voice-device/src/qiuqiu_assets.h').read_text(encoding='utf-8')
    values = np.array([int(value, 16) for value in re.findall(r'0x([0-9a-fA-F]{4})', source)], dtype='>u2')
    assert values.size == 192 * 192
    assert len(values.tobytes()) == 192 * 192 * 2
    pixels = np.frombuffer(values.tobytes(), dtype='>u2').reshape(192, 192)
    assert pixels[0, 0] == pixels[-1, -1] == 0x0843
    # The light sphere remains distinct from its dark background.
    assert (int(pixels[96, 96]) >> 11) > (int(pixels[0, 0]) >> 11) + 15
