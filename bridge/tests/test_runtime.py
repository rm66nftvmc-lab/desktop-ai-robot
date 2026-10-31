import threading
import types
import sys

from fastapi.testclient import TestClient

from bridge.app.main import create_app
from bridge.app.runtime import RuntimeStatus
from bridge.app.device import DeviceLink
from bridge.app.protocol import HELLO, Frame
from bridge.app.speech import SpeechWorker
from bridge.app.storage import initialize
from bridge.app.voice import VoiceConversation


def test_task_follows_capture_and_finishes_only_after_device_drains():
    runtime = RuntimeStatus()
    voice = {"state": "listening", "capture_generation": 4}
    speech = {"state": "transcribing", "capture_generation": 4}
    def state(**device):
        return runtime.snapshot(device, speech, voice, [])['state']
    assert state(listening=True) == 'listening'
    assert state() == 'transcribing'
    voice['state'] = 'waiting_for_agent'
    speech['state'] = 'idle'
    assert state() == 'waiting_reply'
    voice['state'] = 'sent_to_device'
    assert state(playing=True) == 'playing'
    assert state(playing=False) == 'completed'
    # Obsolete STT must not replace the current task.
    speech.update(state='transcribing', capture_generation=3)
    assert state() == 'completed'


def test_disconnect_drops_buffers_stale_transcript_and_late_voice_reply(tmp_path):
    database = tmp_path / 'messages.sqlite3'
    initialize(database)
    device = DeviceLink()
    voice = VoiceConversation(database, tmp_path, device, object())
    device._on_disconnect = voice.on_device_disconnect
    device._update(connected=True, listening=True, playing=True)
    device._capture.extend(b'private recording')
    device._playback = b'old speech'
    voice.on_listen_start(1)
    voice._message_id = 42
    generation = device._playback_generation
    device._connection_lost()
    assert not device._capture and device._playback is None
    assert not device.is_current_generation(generation)
    voice.on_transcript('stale transcript', 1)
    voice.on_reply(42, 'late answer')
    voice.on_speech_error('stale failure', 1)
    assert voice.snapshot()['state'] == 'interrupted'
    assert voice._jobs.empty()
    import io
    device._handle(Frame(HELLO, 1, b'{"protocol":1,"firmware":"test"}'), io.BytesIO(), 0)
    assert device.snapshot()['connected']
    assert device._playback is None
    assert voice.snapshot()['state'] == 'interrupted'
    voice.on_listen_start(8)
    assert voice.snapshot()['state'] == 'listening'


def test_short_capture_and_full_stt_queue_report_terminal_errors(tmp_path):
    errors = []
    worker = SpeechWorker(tmp_path, on_error=lambda *args: errors.append(args))
    worker.enqueue(None, 1)
    worker.enqueue(bytes(16044), 2)
    worker.enqueue(bytes(16044), 3)
    worker.enqueue(bytes(16044), 4)
    assert [entry[1] for entry in errors] == [1, 4]
    assert '半秒' in errors[0][0] and '队列已满' in errors[1][0]


def test_failed_speaker_ack_invalidates_producer_and_reports_failure():
    device = DeviceLink()
    device._update(connected=True)
    generation = device.stop_playback()
    device._playback = b'queued audio'
    device._fail_playback('扬声器回执超时')
    assert not device.is_current_generation(generation)
    assert device._playback is None
    runtime = RuntimeStatus()
    assert runtime.snapshot(device.snapshot(), {}, {'state': 'sent_to_device'}, [])['state'] == 'error'
    assert device.stop_playback() is not None
    assert device.snapshot()['last_error'] is None


def test_stt_model_error_notifies_voice_instead_of_leaving_it_waiting(tmp_path, monkeypatch):
    done = threading.Event()
    errors = []
    def unavailable(*args, **kwargs):
        raise FileNotFoundError('private path and model details')
    monkeypatch.setitem(sys.modules, 'faster_whisper', types.SimpleNamespace(WhisperModel=unavailable))
    def on_error(error, generation):
        errors.append((error, generation))
        done.set()
    worker = SpeechWorker(tmp_path, on_error=on_error)
    worker.start()
    try:
        worker.enqueue(bytes(16044), 7)
        assert done.wait(2)
        assert errors[0][1] == 7
        assert 'private path' not in errors[0][0]
        assert worker.snapshot()['state'] == 'error'
    finally:
        worker.stop()


def test_diagnostics_requires_auth_and_omits_content_paths_secrets(tmp_path, monkeypatch):
    app = create_app(tmp_path, token='test-access-key-sensitive')
    for worker in (app.state.hermes, app.state.harness):
        monkeypatch.setattr(worker, 'snapshot', lambda: {
            'available': True, 'running': False, 'pending': 0,
            'last_error': 'sensitive-error', 'session': {'id': 'sensitive-session'}})
    app.state.speech._status['last_text'] = 'sensitive-transcript'
    app.state.speech._status['last_original_text'] = 'sensitive-raw-transcript'
    app.state.voice._last_error = 'sensitive-voice-error'
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.get('/api/diagnostics').status_code == 401
    client.post('/api/login', json={'token': 'test-access-key-sensitive'})
    status = client.get('/api/status').json()
    assert 'task' in status
    response = client.get('/api/diagnostics')
    assert response.status_code == 200
    report = response.json()
    assert report['device']['connected'] is False
    assert report['events']
    for secret in ('sensitive-', str(tmp_path), 'last_text', 'last_error', 'session', 'token'):
        assert secret not in response.text
