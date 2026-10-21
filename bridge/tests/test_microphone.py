import io
import json
import struct

import numpy as np

from bridge.app.device import DeviceLink
from bridge.app.microphone import DualMicrophone, SpeechActivity
from bridge.app.protocol import (Frame, FrameParser, HELLO, BUTTON, WAKE_CONFIG,
                                STEREO_UP, STEREO_WAKE)


def process(mic, channels, capture=False):
    pcm = np.clip(channels, -32768, 32767).astype('<i2')
    parts = [mic.process(pcm[i:i+128].tobytes(), capture=capture)
             for i in range(0, len(pcm), 128)]
    return np.frombuffer(b''.join(parts), dtype='<i2').astype(float)


def test_independent_background_is_reduced_without_changing_length():
    rng = np.random.default_rng(12)
    channels = rng.normal(0, 1000, (16000, 2))
    mic = DualMicrophone()
    result = process(mic, channels)
    assert len(result) == len(channels)
    reduction = 10*np.log10(np.mean(channels[2000:, 0]**2)/np.mean(result[2000:]**2))
    assert reduction > 3
    assert mic.stats['mode'] == 'dual'


def test_aligned_speech_is_preserved_and_one_missing_mic_falls_back():
    t = np.arange(16000)/16000
    speech = 2000*np.sin(2*np.pi*700*t) + 500*np.sin(2*np.pi*1400*t)
    both = process(DualMicrophone(), np.column_stack((speech, speech)))
    mic = DualMicrophone()
    one = process(mic, np.column_stack((speech, np.zeros_like(speech))))
    reference = speech[2000:-128]
    assert np.corrcoef(both[2128:], reference)[0, 1] > .99
    assert np.sqrt(np.mean(both[2000:]**2)/np.mean(reference**2)) > .9
    assert np.sqrt(np.mean(one[2000:]**2)/np.mean(reference**2)) > .9
    assert mic.stats['mode'] == 'single_fallback'


def test_delay_is_physical_bounded_and_frozen_during_capture():
    source = np.random.default_rng(4).normal(0, 1000, 16000)
    delayed = np.concatenate((np.zeros(2), source[:-2]))
    mic = DualMicrophone()
    process(mic, np.column_stack((source, delayed)))
    assert abs(mic.delay - 2) < .4
    previous = mic.delay
    process(mic, np.column_stack((delayed, source)), capture=True)
    assert mic.delay == previous
    assert abs(mic.delay) <= .05/343*16000


def test_stereo_negotiation_is_capability_gated_and_malformed_pcm_is_ignored():
    raw = []
    device = DeviceLink(on_mic_audio=lambda *args: raw.append(args))
    device._update(connected=True, wake_protocol=1)
    port = io.BytesIO()
    device.configure_wake(True, 0)
    device._send_pending_wake(port, 0)
    assert FrameParser().feed(port.getvalue())[0].payload == b'\x01\x00'
    hello = json.dumps({'protocol': 1, 'wake_protocol': 1, 'stereo_protocol': 1}).encode()
    device._handle(Frame(HELLO, 1, hello), io.BytesIO(), 0)
    port = io.BytesIO()
    device._send_pending_wake(port, 0)
    assert FrameParser().feed(port.getvalue())[0].payload == b'\x01\x03'
    device._handle(Frame(WAKE_CONFIG, 2, b'\x01\x03'), None, 0)
    device._handle(Frame(STEREO_WAKE, 3, b'bad'), None, 0)
    assert not raw
    payload = struct.pack('<256h', *([100, 200]*128))
    device._handle(Frame(STEREO_WAKE, 4, payload), None, 0)
    assert len(raw) == 1 and raw[0][1] is False
    device._handle(Frame(BUTTON, 5, b'\x01'), None, 0)
    device._handle(Frame(STEREO_UP, 6, payload), None, 0)
    assert raw[-1][1] is True
    assert device.snapshot()['audio_samples'] == 128
    device._connection_lost()
    device._handle(Frame(STEREO_WAKE, 7, payload), None, 0)
    assert len(raw) == 2


def test_streaming_local_vad_rejects_silence_and_preserves_partial_frames():
    vad = SpeechActivity()
    for _ in range(50):
        assert not vad.accept(bytes(256))
    assert len(vad.pending) == 512
    assert vad.probability < .5
    vad.reset()
    assert not vad.pending and vad.probability == 0
