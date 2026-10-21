import io
import struct
import time
import pytest

from bridge.app.device import DeviceLink
from bridge.app.protocol import Frame, FrameParser, BUTTON, WAKE_AUDIO, WAKE_CONFIG, AUDIO_UP, CAPTURE_CONTROL
from bridge.app.storage import initialize
from bridge.app.wake import WakeWorker


class FakeDevice:
    def __init__(self):
        self.state = {'connected': True, 'wake_protocol': 1, 'playing': False}
        self.requests = []
        self.configs = []

    def snapshot(self):
        return dict(self.state)

    def request_capture(self, action, generation=None):
        self.requests.append((action, generation))
        return True

    def configure_wake(self, *config):
        self.configs.append(config)


class Recognizer:
    def __init__(self):
        self.calls = self.resets = 0

    def accept(self, pcm):
        self.calls += 1
        return True

    def reset(self):
        self.resets += 1


def worker(tmp_path):
    db = tmp_path/'messages.sqlite3'
    initialize(db)
    device = FakeDevice()
    wake = WakeWorker(db, tmp_path, device)
    wake._enabled, wake._state, wake._engine = True, 'armed', Recognizer()
    return wake, device


def consume(wake, *, capture=False, generation=0, value=500, epoch=None):
    wake._consume((wake._epoch if epoch is None else epoch, struct.pack('<1600h', *([value]*1600)),
                   capture, generation, time.monotonic()))


def test_speaker_audio_and_pending_reply_cannot_wake(tmp_path):
    wake, device = worker(tmp_path)
    device.state['playing'] = True
    consume(wake)
    consume(wake)
    assert not device.requests and wake._engine.calls == 0
    assert wake._engine.resets == 1
    device.state['playing'] = False
    wake.voice_busy = lambda: True
    consume(wake)
    assert not device.requests
    wake.voice_busy = lambda: False
    consume(wake)
    assert device.requests == [(1, None)]


def test_wake_waits_for_acknowledgement_and_discards_its_mic_audio(tmp_path):
    wake, device = worker(tmp_path)
    def acknowledge(cancelled):
        assert not device.requests and not cancelled()
        wake.feed(bytes(3200), False, 0)
        assert wake._queue.empty()
        return True
    wake.acknowledge = acknowledge
    consume(wake)
    assert wake.snapshot()['state'] == 'acknowledging'
    assert not device.requests
    wake._acknowledge_wake()
    assert device.requests == [(1, None)]
    assert wake.snapshot()['state'] == 'waking'
    wake.capture_changed(True, 1)
    assert wake.snapshot()['state'] == 'recording'


@pytest.mark.parametrize('change', ['disconnect', 'manual', 'disable'])
def test_acknowledgement_cancellation_never_starts_late_capture(tmp_path, change):
    wake, device = worker(tmp_path)
    def acknowledge(cancelled):
        if change == 'disconnect':
            wake.disconnected()
        elif change == 'manual':
            wake.capture_changed(True, 4)
        else:
            wake.update(False, 'auto')
        assert cancelled()
        return True
    wake.acknowledge = acknowledge
    consume(wake)
    wake._acknowledge_wake()
    assert not device.requests


def test_failed_acknowledgement_returns_to_armed_without_open_mic(tmp_path):
    wake, device = worker(tmp_path)
    def fail(cancelled):
        raise RuntimeError('TTS unavailable')
    wake.acknowledge = fail
    consume(wake)
    wake._acknowledge_wake()
    assert not device.requests
    assert wake.snapshot()['state'] == 'armed'
    assert 'RuntimeError' in wake.snapshot()['last_error']


def test_loud_non_speech_no_longer_keeps_automatic_recording_alive(tmp_path):
    wake, device = worker(tmp_path)
    class Detector:
        probability = 0.
        def reset(self):
            pass
        def accept(self, pcm):
            return self.probability >= .5
    wake.speech_activity = Detector()
    wake._state = 'waking'
    wake.capture_changed(True, 9)
    wake.speech_activity.probability = .9
    for _ in range(3):
        consume(wake, capture=True, generation=9, value=500)
    wake.speech_activity.probability = .01
    for _ in range(16):
        consume(wake, capture=True, generation=9, value=5000)
    assert device.requests == [(0, 9)]


def test_wake_speech_then_silence_ends_once_for_the_same_generation(tmp_path):
    wake, device = worker(tmp_path)
    wake._state = 'waking'
    wake.capture_changed(True, 7)
    for _ in range(3):
        consume(wake, capture=True, generation=7)
    for _ in range(16):
        consume(wake, capture=True, generation=7, value=0)
    assert device.requests == [(0, 7)]
    assert wake.snapshot()['wake_count'] == 1


def test_playback_without_mic_frames_clears_decoder_and_guards_the_tail(tmp_path):
    wake, device = worker(tmp_path)
    device.state['playing'] = True
    wake._tick()  # Firmware deliberately sends no mic frames during playback.
    assert wake._engine.resets == 1
    device.state['playing'] = False
    consume(wake)
    assert not device.requests
    wake._cooldown = 0
    consume(wake)
    assert device.requests == [(1, None)]


def test_manual_button_recording_never_auto_stops(tmp_path):
    wake, device = worker(tmp_path)
    wake.capture_changed(True, 2)
    for _ in range(30):
        consume(wake, capture=True, generation=2, value=0)
    wake._started -= 25
    wake._tick()
    assert not device.requests


def test_no_speech_cancels_and_old_audio_is_discarded(tmp_path):
    wake, device = worker(tmp_path)
    old_epoch = wake._epoch
    wake._state = 'waking'
    wake.capture_changed(True, 3)
    consume(wake, epoch=old_epoch)
    assert not device.requests
    wake._started -= 7
    wake._tick()
    assert device.requests == [(2, 3)]
    wake.disconnected()
    consume(wake, epoch=old_epoch)
    assert device.requests == [(2, 3)]


def test_cancelled_capture_and_idle_pcm_never_reach_transcription():
    captures, raw = [], []
    device = DeviceLink(lambda *args: captures.append(args), on_mic_audio=lambda *args: raw.append(args))
    device._handle(Frame(WAKE_AUDIO, 0, bytes(256)), None, 0)
    assert not raw  # Old buffered idle data cannot wake a disconnected/reopening link.
    device._update(connected=True, wake_device_enabled=True)
    device._handle(Frame(WAKE_AUDIO, 1, bytes(256)), None, 0)
    assert not captures and device.snapshot()['audio_samples'] == 0
    device._handle(Frame(BUTTON, 2, b'\x01'), None, 0)
    device._handle(Frame(AUDIO_UP, 3, bytes(16000)), None, 0)
    device._handle(Frame(BUTTON, 4, b'\x02'), None, 0)
    assert not captures and not device._last_capture
    assert raw[0][1] is False and raw[1][1] is True


def test_old_firmware_is_untouched_and_stale_stop_is_not_sent():
    device = DeviceLink()
    port = io.BytesIO()
    device._update(connected=True)
    device.configure_wake(True)
    assert device._send_pending_wake(port, 1) == 1
    assert not device.request_capture(1)
    assert not port.getvalue()
    device._update(wake_protocol=1)
    device.request_capture(2, generation=0)
    device._capture_generation = 1
    device._send_pending_wake(port, 1)
    assert [f.kind for f in FrameParser().feed(port.getvalue())] == [WAKE_CONFIG]


def test_wake_api_requires_auth_origin_supported_device_and_local_model(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from bridge.app.main import create_app
    app = create_app(tmp_path, token='test-wake-token')
    client = TestClient(app, base_url='http://127.0.0.1')
    path = '/api/voice/wake'
    assert client.post(path, json={'enabled': True}).status_code == 401
    client.post('/api/login', json={'token': 'test-wake-token'})
    assert client.post(path, json={'enabled': True}, headers={'origin':'https://other.test'}).status_code == 403
    assert client.post(path, json={'enabled': 'true'}).status_code == 422
    assert client.post(path, json={'enabled': True}).status_code == 503
    model = tmp_path/'models/vosk-model-small-cn-0.22/am/final.mdl'
    model.parent.mkdir(parents=True)
    model.touch()
    monkeypatch.setattr('bridge.app.wake.importlib.util.find_spec', lambda _: object())
    assert client.post(path, json={'enabled': True}).status_code == 503
    app.state.device._update(wake_protocol=1)
    assert client.post(path, json={'enabled': True, 'mic_channel':'right'}).json()['enabled'] is True
    restored = create_app(tmp_path, token='test-wake-token')
    assert restored.state.wake.snapshot()['enabled'] is True
    assert restored.state.device._wake_desired == (False, 2)  # Apply channel before enabling the decoder.
    assert client.post(path, json={'enabled':False}).json()['enabled'] is False
