from concurrent.futures import ThreadPoolExecutor
import threading

from fastapi.testclient import TestClient

from bridge.app.device import DeviceLink
from bridge.app.main import create_app
from bridge.app.playback import PlaybackControl


def test_late_stop_cannot_cancel_new_audio_or_restart_retired_request():
    device = DeviceLink()
    device._update(connected=True)
    control = PlaybackControl(device)
    _, old_generation, _ = control.claim('old')
    _, new_generation, _ = control.claim('new')
    assert not device.is_current_generation(old_generation)
    assert control.stop('old') is False
    assert device.is_current_generation(new_generation)
    assert control.claim('old') == ('old', None, True)
    assert control.stop('new') is True
    assert not device.is_current_generation(new_generation)
    assert control.snapshot()['state'] == 'idle'


def test_old_manual_stop_does_not_cancel_a_new_button_recording_or_voice_reply():
    device = DeviceLink()
    device._update(connected=True)
    control = PlaybackControl(device)
    control.claim('manual')
    new_voice_generation = device.stop_playback()
    assert control.stop('manual') is False
    assert device.is_current_generation(new_voice_generation)


def test_stop_before_speak_arrives_retires_that_request(tmp_path, monkeypatch):
    app = create_app(tmp_path, token='test-access-token')
    app.state.device._update(connected=True)
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.post('/api/tts/stop', json={}).status_code == 401
    client.post('/api/login', json={'token': 'test-access-token'})
    assert client.post('/api/tts/stop', json={}, headers={'origin': 'https://other.example'}).status_code == 403
    assert client.post('/api/tts/stop', json={'playback_id': ''}).status_code == 422
    client.post('/api/tts/stop', json={'playback_id': 'late'})
    monkeypatch.setattr('bridge.app.main.synthesize_chunks', lambda *a, **k: (_ for _ in ()).throw(AssertionError('retired playback must not synthesize')))
    response = client.post('/api/tts/speak', json={'text': 'late speech', 'playback_id': 'late'})
    assert response.json() == {'queued': False, 'superseded': True}


def test_stop_during_synthesis_prevents_late_audio_from_being_queued(tmp_path, monkeypatch):
    app = create_app(tmp_path, token='test-access-token')
    app.state.device._update(connected=True)
    client = TestClient(app, base_url='http://127.0.0.1')
    client.post('/api/login', json={'token': 'test-access-token'})
    started, resume = threading.Event(), threading.Event()
    def slow_synthesis(*args, **kwargs):
        started.set()
        assert resume.wait(3)
        yield b'not needed: generation must be checked before parsing audio'
    monkeypatch.setattr('bridge.app.main.synthesize_chunks', slow_synthesis)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(client.post, '/api/tts/speak', json={'text': 'speech', 'playback_id': 'pending'})
        try:
            assert started.wait(2)
            assert client.post('/api/tts/stop', json={'playback_id': 'pending'}).json()['stopped'] is True
        finally:
            resume.set()
        assert pending.result(timeout=3).json() == {'queued': False, 'superseded': True}
    assert app.state.device._playback is None
    assert app.state.device.snapshot()['playing'] is False


def test_finished_request_stays_active_until_device_buffer_drains():
    device = DeviceLink()
    device._update(connected=True)
    control = PlaybackControl(device)
    control.claim('audio')
    device._update(playing=True)
    control.finished('audio')
    assert control.snapshot() == {'playback_id': 'audio', 'state': 'playing'}
    device._update(playing=False)
    assert control.snapshot()['state'] == 'idle'
