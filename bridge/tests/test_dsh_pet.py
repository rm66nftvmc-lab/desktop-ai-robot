"""Validate the exact binary that PlatformIO embeds, including delta seeking."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

import numpy as np

ASSETS = Path(__file__).resolve().parents[2] / 'voice-device/assets/dsh_pet'


def test_embedded_clips_are_complete_seekable_and_fit_flash():
    data = (ASSETS/'animations.bin').read_bytes()
    manifest = json.loads((ASSETS/'manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(data).hexdigest() == manifest['sha256']
    magic, width, height, fps, clips, frames, co, fo, do = struct.unpack_from('<4sHHHHIIII', data)
    assert (magic, width, height, fps, clips) == (b'DSP1', 192, 192, 24, 13)
    assert len(data) + 600_000 < 0xef0000
    assert co == 28+512 and fo == co+clips*8 and do == fo+frames*8
    assert manifest['random_actions'] == list(range(5,13))
    assert manifest['idle_gap_ms'] == [8000,22000]
    assert len((ASSETS/'background.bin').read_bytes()) == 240*320*2
    background = np.frombuffer((ASSETS/'background.bin').read_bytes(), '>u2').reshape(320,240)
    logical_background = np.rot90(background[64:256,24:216], -1)
    palette = np.frombuffer(data[28:540], '<u2')
    seen = 0
    for i in range(clips):
        first, count = struct.unpack_from('<II', data, co+i*8)
        assert first == seen
        assert count >= 240  # No trimming the original ten-second actions.
        previous = np.zeros(width*height, np.uint8)
        unique = set()
        for local in range(count):
            offset, size = struct.unpack_from('<II', data, fo+(first+local)*8)
            key = bool(size & 0x80000000)
            assert key == (local % 24 == 0)
            length = size & 0x7fffffff
            assert do+offset+length <= len(data)
            decoded = np.frombuffer(zlib.decompress(data[do+offset:do+offset+length]), np.uint8)
            assert len(decoded) == width*height
            previous = decoded.copy() if key else previous ^ decoded
            assert previous.max() < 64
            assert np.count_nonzero(palette[previous.reshape(height,width)] != logical_background) > 1000
            unique.add(hashlib.sha256(previous.tobytes()).digest())
        assert len(unique) > count*.9
        assert manifest['clips'][i]['frames'] == count
        seen += count
    assert seen == frames


def test_dsh_theme_survives_restart_and_usb_reconnect(tmp_path):
    import io
    from fastapi.testclient import TestClient
    from bridge.app.main import create_app
    from bridge.app.protocol import Frame, FrameParser, HELLO, THEME
    app = create_app(tmp_path, token='test-access-token')
    client = TestClient(app, base_url='http://127.0.0.1')
    client.post('/api/login',json={'token':'test-access-token'})
    assert client.post('/api/device/theme',json={'theme':'dsh_pet'}).status_code == 200
    device = create_app(tmp_path,token='test-access-token').state.device
    assert device.snapshot()['desired_theme'] == 2
    for sequence in (1,7):
        port = io.BytesIO()
        device._handle(Frame(HELLO,0,b'{"protocol":1}'),port,sequence)
        device._send_pending_theme(port,sequence+1)
        assert FrameParser().feed(port.getvalue())[-1] == Frame(THEME,sequence+1,b'\x02')


def test_dsh_speaking_keeps_animation_and_ball_retains_quiet_policy():
    import io
    from bridge.app.device import DeviceLink
    from bridge.app.protocol import FrameParser
    device = DeviceLink()
    device.set_quiet_playback(True)
    device.set_theme(2)
    device._update(connected=True,playing=True,device_playing=True)
    port=io.BytesIO()
    device._send_pending_animation(port,0)
    assert FrameParser().feed(port.getvalue())[-1].payload == b'\x01'
    device.set_theme(1)
    port=io.BytesIO()
    device._send_pending_animation(port,1)
    assert FrameParser().feed(port.getvalue())[-1].payload == b'\x00'
