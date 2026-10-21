import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bridge.app.main import create_app
from bridge.app.security import Sessions
from bridge.app.message_access import MessageAccess
from bridge.app.hermes import HermesWorker
from bridge.app.harness import HarnessWorker
from bridge.app.storage import initialize, add_message, list_messages
from bridge.app.wake_ack import CONNECTION_NOTICE, WakeAcknowledgement


class Client:
    def __init__(self):
        self.probes = 0
        self.available = True
    def health_snapshot(self):
        self.probes += 1
        return {'available': self.available}


class Worker:
    executable = 'test-agent'
    hermes_home = Path('missing-test-home')
    def __init__(self):
        self.client = self.api_client = Client()
        self.jobs = []
        self.cancelled = []
    def snapshot(self):
        return {'available': True, 'running': False, 'pending': 0}
    def enqueue(self, message_id, text, **kwargs):
        self.jobs.append((message_id, text))
        return True
    def cancel(self, message_id):
        self.cancelled.append(message_id)
    def pending_approval(self):
        return None
    def _check_api_target(self, session):
        pass


def app_client(tmp_path):
    hermes, harness = Worker(), Worker()
    app = create_app(tmp_path, token='test-access-token', hermes_worker=hermes, harness_worker=harness)
    return app, TestClient(app, base_url='http://127.0.0.1'), hermes, harness


def pair(client, source):
    client.post('/api/login', json={'token': 'test-access-token'})
    sid = client.post('/api/sessions', json={'source': source}).json()['item']['id']
    assert client.post('/api/voice/target', json={'source': source, 'session_id': sid}).status_code == 200
    return sid


@pytest.mark.parametrize('source', ['hermes', 'deepseek_harness'])
def test_no_key_blocks_web_and_hardware_and_login_alone_does_not_pair(tmp_path, source):
    app, client, hermes, harness = app_client(tmp_path)
    assert client.post('/api/messages', json={'source': source, 'text': 'blocked'}).status_code == 401
    assert client.post('/api/hermes/approval', json={'request_id': 'x', 'choice': 'once'}).status_code == 401
    voice = app.state.voice
    voice.set_target(source, 'old-saved-session')
    voice.on_listen_start(1)
    voice.on_transcript('unauthorized microphone', 1)
    assert not hermes.jobs and not harness.jobs
    client.post('/api/login', json={'token': 'test-access-token'})
    assert not voice.snapshot()['authorized']  # Status/diagnostic clients cannot arm hardware.
    pair(client, source)
    assert voice.snapshot()['authorized']
    voice.on_listen_start(2)
    voice.on_transcript('authorized microphone', 2)
    worker = hermes if source == 'hermes' else harness
    mid = worker.jobs[-1][0]
    assert app.state.message_access.allowed(mid)
    client.post('/api/logout')
    assert not voice.snapshot()['authorized']
    assert not app.state.message_access.allowed(mid)
    assert mid in worker.cancelled
    voice.on_transcript('late transcript', 2)
    assert len(worker.jobs) == 1


@pytest.mark.parametrize('source', ['hermes', 'deepseek_harness'])
def test_wake_notice_is_local_no_capture_no_agent_probe_without_key(tmp_path, source, monkeypatch):
    app, client, hermes, harness = app_client(tmp_path)
    gate = app.state.wake.acknowledge
    calls = []
    gate.failure = lambda cancelled: calls.append('failure') or True
    gate.normal = lambda cancelled: calls.append('normal') or True
    captures = []
    monkeypatch.setattr(app.state.device, 'request_capture', lambda *args: captures.append(args))
    wake = app.state.wake
    wake._enabled, wake._state = True, 'acknowledging'
    wake._acknowledge_wake()
    assert calls == ['failure'] and not captures
    assert hermes.client.probes == harness.client.probes == 0
    pair(client, source)
    worker = hermes if source == 'hermes' else harness
    worker.client.available = False
    wake._state = 'acknowledging'
    wake._acknowledge_wake()
    assert calls == ['failure', 'failure'] and not captures
    worker.client.available = True
    wake._state = 'acknowledging'
    wake._acknowledge_wake()
    assert calls[-1] == 'normal' and captures == [(1,)]
    assert not hermes.jobs and not harness.jobs


@pytest.mark.parametrize('factory', [HermesWorker, HarnessWorker])
def test_revoked_queued_job_never_reaches_model(tmp_path, monkeypatch, factory):
    db = tmp_path/'messages.sqlite3'
    initialize(db)
    worker = factory(db, tmp_path)
    worker.executable = 'test-agent'
    monkeypatch.setattr(worker, '_preferred_session_info', lambda: None)
    sent = []
    monkeypatch.setattr(worker, '_ask', lambda *args: sent.append(args) or 'not allowed')
    sessions = Sessions('test-key')
    cookie = sessions.login('test-key')
    access = MessageAccess(sessions)
    worker.authorize_job, worker.release_authorization = access.allowed, access.release
    mid = add_message(db, worker.source, 'queued', delivery='queued')['id']
    access.browser(mid, cookie)
    assert worker.enqueue(mid, 'queued')
    sessions.logout(cookie)
    worker.start()
    try:
        deadline = time.monotonic()+2
        while time.monotonic() < deadline and list_messages(db, worker.source)[0]['delivery'] != 'failed':
            time.sleep(.01)
        assert not sent
        assert list_messages(db, worker.source)[0]['delivery'] == 'failed'
    finally:
        worker.stop()


def test_voice_grant_expiry_does_not_revive_old_work_after_new_login(monkeypatch):
    sessions = Sessions('test-key')
    cookie = sessions.login('test-key')
    assert sessions.voice_grant() is None
    assert sessions.authorize_voice(cookie)
    old = sessions.voice_grant()
    access = MessageAccess(sessions)
    access.voice(1, old)
    assert access.allowed(1)
    sessions._expires[cookie] = 0
    assert not access.allowed(1)
    other = sessions.login('test-key')
    sessions.authorize_voice(other)
    assert sessions.voice_grant() != old and not access.allowed(1)


def test_notice_keeps_exact_text_and_does_not_retry_long_phrase(tmp_path, monkeypatch):
    from bridge.tests.test_wake_ack import cue
    calls = []
    monkeypatch.setattr('bridge.app.wake_ack.selected_voice', lambda _: 'paimon')
    monkeypatch.setattr('bridge.app.wake_ack.synthesize_chunks',
                        lambda text, *args, **kwargs: calls.append(text) or [cue()])
    notice = WakeAcknowledgement(tmp_path, None, None, text=CONNECTION_NOTICE)
    assert notice.prepare()
    assert calls == ['连接不上，没有大白饭吃，工作不了哟。']


def test_cli_authorization_loss_kills_process_without_resending_input(tmp_path, monkeypatch):
    import subprocess
    db = tmp_path/'messages.sqlite3'
    initialize(db)
    worker = HermesWorker(db, tmp_path)
    worker.executable = 'test-agent'
    worker._current_message_id = 1
    allowed = [True]
    worker.authorize_job = lambda message_id: allowed[0]
    calls = []
    class Process:
        returncode = 0
        def communicate(self, input=None, timeout=None):
            calls.append((input, timeout))
            if timeout:
                allowed[0] = False
                raise subprocess.TimeoutExpired('test-agent', timeout)
            return '', ''
        def kill(self):
            calls.append('killed')
    monkeypatch.setattr('bridge.app.hermes.subprocess.Popen', lambda *a, **k: Process())
    monkeypatch.setattr('bridge.app.hermes.command_invocation', lambda *a: (['test-agent'], {}))
    with pytest.raises(RuntimeError, match='访问授权已失效'):
        worker._ask('private input', None)
    assert calls == [('private input', .5), 'killed', (None, None)]
