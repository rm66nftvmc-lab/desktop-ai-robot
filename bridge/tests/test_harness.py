import urllib.error

import pytest

from bridge.app.harness import HarnessClient, HarnessWorker, backend_overlay, completed_reply
from bridge.app.storage import initialize


def test_health_probe_is_bounded_read_only_and_never_starts_host(tmp_path, monkeypatch):
    import io
    import json
    client = HarnessClient(tmp_path)
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append((request.full_url, timeout, json.loads(request.data)))
            return io.BytesIO(json.dumps({'result': {'ok': True, 'value': {'items': []}}}).encode())
    client._health_opener = Opener()
    monkeypatch.setattr(client, 'start', lambda: pytest.fail('Health must not start a Host'))
    assert client.health_snapshot()['available']
    assert client.health_snapshot()['available']
    assert len(calls) == 1
    assert calls[0][0].endswith('/api/session/list') and calls[0][1] == .4
    assert calls[0][2]['method'] == 'session/list'


def test_health_failure_is_sanitized_and_does_not_use_model_rpc(tmp_path, monkeypatch):
    client = HarnessClient(tmp_path)
    monkeypatch.setattr(client, 'rpc', lambda *a: pytest.fail('No model RPC allowed'))
    result = client.health_snapshot()
    assert not result['available']
    assert str(tmp_path) not in result['error']


def test_expired_harness_cookie_refreshes_once_without_retrying_ambiguous_writes(tmp_path, monkeypatch):
    client = HarnessClient(tmp_path)
    expired = _RouteOpener([urllib.error.HTTPError('http://local/api/test', 401, 'expired', {}, None)])
    fresh = _RouteOpener([{'result': {'ok': True, 'value': {'sessionId': 'fresh'}}}])
    client._opener = expired
    logins = []
    def login():
        logins.append(True)
        client._opener = fresh
    monkeypatch.setattr(client, '_login', login)
    monkeypatch.setattr(client, 'start', lambda: None)
    assert client.rpc('session/create') == {'sessionId': 'fresh'}
    assert logins == [True]
    client._opener = _RouteOpener([urllib.error.URLError('lost')])
    with pytest.raises(RuntimeError, match='不会自动重发'):
        client.rpc('session/prompt')
    assert logins == [True]


def record(seq, kind, data):
    return {'type': 'event', 'event': {'seq': seq, 'type': kind, 'data': data}}


def test_reply_requires_our_prompt_and_completed_turn_and_keeps_full_text():
    text = '完整回答' * 1000
    records = [record(5, 'user/message', {'source': {'rpcId': 'ours'}}),
               record(5.5, 'user/message', {'source': {'kind': 'skill-catalog'}}),
               record(6, 'assistant/message', {'message': {'content': [
                   {'type': 'reasoning', 'text': '隐藏思考'}, {'type': 'text', 'text': text}]}})]
    assert completed_reply(records, 'ours', 4) is None
    records.append(record(7, 'turn/end', {'reason': {'kind': 'completed'}}))
    assert completed_reply(records, 'ours', 4) == text
    assert completed_reply(records, 'other', 4) is None
    assert completed_reply(records, 'ours', 7) is None
    records[-1] = record(7, 'turn/end', {'reason': {'kind': 'error'}})
    with pytest.raises(RuntimeError):
        completed_reply(records, 'ours', 4)


def test_backend_overlay_preserves_off_key_and_excludes_desktop_ui(tmp_path):
    path = tmp_path / 'desktop.yml'
    path.write_text('''- id: llm-pi-ai
  config:
    efforts: {off: null, high: high}
- id: agent-default-model
  config: {provider: existing, model: existing-model}
- id: ui-theme
  config: {theme: dark}
''', encoding='utf-8')
    values = backend_overlay(path)
    assert len(values) == 2
    assert 'off' in values[0]['config']['efforts']
    assert False not in values[0]['config']['efforts']


def test_harness_resumes_latest_root_instead_of_subagent(tmp_path):
    db = tmp_path / 'messages.sqlite3'
    initialize(db)

    class Client:
        installed = True
        exe = tmp_path / 'harness.exe'
        def rpc(self, method):
            return {'items': [
                {'sessionId': 'child', 'updatedAt': 20, 'projections': {'values': {'subagent': {'parent': 'root'}}}},
                {'sessionId': 'root', 'updatedAt': 10},
                {'sessionId': 'empty', 'updatedAt': 30, 'blank': True}]}

    worker = HarnessWorker(db, tmp_path, client=Client())
    assert worker._preferred_session_info()['id'] == 'root'


class _JsonResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        import json
        return json.dumps(self.value).encode()


class _RouteOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.paths = []
        self.payloads = []

    def open(self, request, timeout):
        import json
        from urllib.parse import urlsplit
        self.paths.append(urlsplit(request.full_url).path)
        self.payloads.append(json.loads(request.data))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return _JsonResponse(response)


def test_harness_permanent_delete_moves_then_immediately_purges(tmp_path):
    session_id = 'session-123'
    opener = _RouteOpener([
        {'ok': True, 'value': {'sessionId': session_id}},
        {'ok': True, 'value': {'purged': [session_id]}},
    ])
    client = HarnessClient(tmp_path)
    client._opener = opener

    result = client.delete_session_permanently(session_id)

    assert result == {'session_id': session_id, 'permanently_deleted': True}
    assert opener.paths == ['/api/session.delete', '/api/session.purge']
    assert all(payload == {'sessionId': session_id} for payload in opener.payloads)


def test_harness_permanent_delete_restores_if_immediate_purge_fails(tmp_path):
    session_id = 'session-456'
    purge_error = urllib.error.HTTPError(
        'http://127.0.0.1:3081/api/session.purge', 500, 'failed', {}, None)
    opener = _RouteOpener([
        {'ok': True, 'value': {'sessionId': session_id}},
        purge_error,
        {'ok': True, 'value': {'sessionId': session_id}},
    ])
    client = HarnessClient(tmp_path)
    client._opener = opener

    with pytest.raises(RuntimeError, match='永久删除失败，已将会话恢复到列表'):
        client.delete_session_permanently(session_id)

    assert opener.paths == [
        '/api/session.delete', '/api/session.purge', '/api/session.restore']


def test_harness_permanent_delete_refuses_live_session_without_archiving(tmp_path):
    session_id = 'session-789'
    opener = _RouteOpener([
        {'ok': False, 'error': {'code': 'session-open', 'message': 'busy'}}])
    client = HarnessClient(tmp_path)
    client._opener = opener

    with pytest.raises(RuntimeError, match='仍被 Harness 占用.*无法安全删除'):
        client.delete_session_permanently(session_id)

    assert opener.paths == ['/api/session.delete']


def test_harness_permanent_delete_explains_missing_extension_without_archiving(tmp_path):
    missing_route = urllib.error.HTTPError(
        'http://127.0.0.1:3081/api/session.delete', 404, 'Not Found', {}, None)
    opener = _RouteOpener([missing_route])
    client = HarnessClient(tmp_path)
    client._opener = opener

    with pytest.raises(RuntimeError, match='永久删除扩展尚未加载.*未归档，会话未删除'):
        client.delete_session_permanently('session-123')
