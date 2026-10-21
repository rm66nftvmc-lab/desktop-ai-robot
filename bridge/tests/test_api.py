from fastapi.testclient import TestClient
import pytest

from bridge.app.main import create_app


class FakeHermes:
    executable = "hermes-test"

    def __init__(self):
        self.jobs = []
        self.approvals = []

    def start(self):
        pass

    def stop(self):
        pass

    def snapshot(self):
        return {"available": True, "pending": len(self.jobs), "running": False, "last_error": None}

    def enqueue(self, message_id, text, *, new_session=False):
        self.jobs.append((message_id, text, new_session))
        return True

    def approve(self, request_id, choice):
        self.approvals.append((request_id, choice))
        return request_id == "pending-1"


def test_audio_output_auth_limits_persistence_and_immediate_stop(tmp_path, monkeypatch):
    app = create_app(tmp_path, token="test-access-token-for-bridge")
    client = TestClient(app, base_url="http://127.0.0.1")
    path = "/api/audio/output"
    assert client.post(path, json={"muted": True}).status_code == 401
    client.post("/api/login", json={"token": "test-access-token-for-bridge"})
    assert client.post(path, json={"volume": 30}, headers={"origin": "https://example.com"}).status_code == 403
    for invalid in (-1, 101, True, "50"):
        assert client.post(path, json={"volume": invalid}).status_code == 422
    stops = []
    monkeypatch.setattr(app.state.device, "stop_playback", lambda: stops.append(True))
    monkeypatch.setattr("bridge.app.main.synthesize_chunks", lambda *a, **k: pytest.fail("Muted output must not synthesize"))
    assert client.post(path, json={"volume": 45}).json()["volume"] == 45
    assert client.post(path, json={"muted": True}).json()["enabled"] is False
    assert stops == [True]
    assert client.post("/api/tts/speak", json={"text": "你好"}).json() == {"queued": False, "muted": True}
    restored = create_app(tmp_path, token="test-access-token-for-bridge")
    assert restored.state.audio_output.snapshot() == {"volume": 45, "muted": True, "enabled": False}
    assert client.post(path, json={"muted": False}).json()["enabled"] is True


def test_auth_and_source_isolation(tmp_path):
    hermes = FakeHermes()
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge",
                                   hermes_worker=hermes), base_url="http://127.0.0.1")
    assert client.get("/api/status").status_code == 401
    assert client.post("/api/login", json={"token": "incorrect-token-12345"}).status_code == 401
    assert client.post("/api/login", json={"token": "test-access-token-for-bridge"}).status_code == 200

    result = client.post("/api/messages", json={"source": "hermes", "text": " 你好 "})
    assert result.status_code == 200
    assert result.json()["delivery"] == "queued"
    assert result.json()["item"]["text"] == "你好"
    assert hermes.jobs == [(result.json()["item"]["id"], "你好", False)]
    assert len(client.get("/api/messages?source=hermes").json()["items"]) == 1
    assert client.get("/api/messages?source=doubao_web").json()["items"] == []
    assert client.post("/api/messages", json={"source": "shell", "text": "test"}).status_code == 400
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/messages?source=hermes").status_code == 401


def test_six_digit_key_and_login_attempt_limit(tmp_path):
    client = TestClient(create_app(tmp_path, token="654321"), base_url="http://127.0.0.1")
    for _ in range(5):
        assert client.post("/api/login", json={"token": "000000"}).status_code == 401
    assert client.post("/api/login", json={"token": "654321"}).status_code == 401

    fresh_client = TestClient(create_app(tmp_path, token="654321"), base_url="http://127.0.0.1")
    assert fresh_client.post("/api/login", json={"token": "654321"}).status_code == 200


@pytest.mark.parametrize('source', ['hermes', 'deepseek_harness'])
def test_typed_reply_never_auto_plays_or_replaces_a_voice_turn(tmp_path, source):
    hermes, harness = FakeHermes(), FakeHermes()
    app = create_app(tmp_path, token='test-access-token-for-bridge',
                     hermes_worker=hermes, harness_worker=harness)
    client = TestClient(app, base_url='http://127.0.0.1', headers={
        'user-agent': 'Mozilla/5.0 (Linux; Android 14) Mobile'})
    client.post('/api/login', json={'token': 'test-access-token-for-bridge'})
    session = client.post('/api/sessions', json={'source': source}).json()['item']['id']
    voice = app.state.voice
    assert client.post('/api/voice/target', json={'source': source, 'session_id': session}).status_code == 200
    voice.on_listen_start(1)
    voice.on_transcript('语音提问', 1)
    spoken_id = voice.snapshot()['message_id']
    result = client.post('/api/messages', json={
        'source': source, 'session_id': session, 'text': '手机打字提问'}).json()
    assert result['item']['input_method'] == 'text'
    worker = hermes if source == 'hermes' else harness
    worker.on_reply(result['item']['id'], '打字问题的回答')
    assert voice._jobs.empty()
    assert voice.snapshot()['message_id'] == spoken_id
    worker.on_reply(spoken_id, '语音问题的回答')
    assert voice._jobs.get_nowait()[1:3] == ('语音问题的回答', 'reply')


def test_cross_origin_submission_is_rejected(tmp_path):
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge"), base_url="http://127.0.0.1")
    result = client.post(
        "/api/login",
        json={"token": "test-access-token-for-bridge"},
        headers={"origin": "https://example.com"},
    )
    assert result.status_code == 403


def test_tts_requires_login_and_connected_device(tmp_path):
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge"), base_url="http://127.0.0.1")
    assert client.post("/api/tts/speak", json={"text": "你好"}).status_code == 401
    client.post("/api/login", json={"token": "test-access-token-for-bridge"})
    assert client.post("/api/tts/speak", json={"text": "你好"}).status_code == 503


def test_harness_target_routes_to_own_worker_and_keeps_messages_separate(tmp_path):
    hermes, harness = FakeHermes(), FakeHermes()
    app = create_app(tmp_path, token="test-access-token-for-bridge",
                     hermes_worker=hermes, harness_worker=harness)
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.post('/api/messages', json={'source': 'deepseek_harness', 'text': '你好'}).status_code == 401
    client.post('/api/login', json={'token': 'test-access-token-for-bridge'})
    response = client.post('/api/messages', json={
        'source': 'deepseek_harness', 'text': '你好', 'new_session': False})
    assert response.json()['delivery'] == 'queued'
    assert harness.jobs == [(response.json()['item']['id'], '你好', False)]
    assert hermes.jobs == []
    assert client.get('/api/messages?source=hermes').json()['items'] == []
    assert len(client.get('/api/messages?source=deepseek_harness').json()['items']) == 1


def test_voice_target_auth_origin_session_scope_and_harness_callback(tmp_path):
    hermes, harness = FakeHermes(), FakeHermes()
    app = create_app(tmp_path, token='test-access-token-for-bridge', hermes_worker=hermes, harness_worker=harness)
    client = TestClient(app, base_url='http://127.0.0.1')
    path = '/api/voice/target'
    assert client.post(path, json={'source': 'hermes'}).status_code == 401
    client.post('/api/login', json={'token': 'test-access-token-for-bridge'})
    draft = client.post('/api/sessions', json={'source': 'deepseek_harness'}).json()['item']
    target = {'source': 'deepseek_harness', 'session_id': draft['id']}
    assert client.post(path, json=target, headers={'origin': 'https://example.com'}).status_code == 403
    assert client.post(path, json=target).json() == target
    app.state.voice.on_listen_start(1)
    app.state.voice.on_transcript('语音路由测试', 1)
    message_id = harness.jobs[0][0]
    assert hermes.jobs == []
    harness.on_reply(message_id, 'Harness回答')
    assert app.state.voice.snapshot()['state'] == 'queued_to_speak'
    assert client.post(path, json={'source': 'hermes', 'session_id': draft['id']}).status_code == 400
    assert app.state.voice.snapshot()['target'] == {'source': 'hermes', 'session_id': None}


def test_voice_selection_is_local_authenticated_and_follows_theme(tmp_path, monkeypatch):
    monkeypatch.setattr("bridge.app.main.set_selected_voice", lambda _dir, voice: (
        (_ for _ in ()).throw(ValueError("Unknown voice")) if voice not in {"kokoro", "paimon"} else None))
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge"),
                        base_url="http://127.0.0.1")
    path = "/api/tts/voice"
    assert client.post(path, json={"voice": "kokoro"}).status_code == 401
    client.post("/api/login", json={"token": "test-access-token-for-bridge"})
    assert client.post(path, json={"voice": "untrusted"}).status_code == 400
    assert client.post(path, json={"voice": "kokoro"}).status_code == 400
    assert client.post(path, json={"voice": "paimon"}).status_code == 200


def test_approval_requires_login_same_origin_and_one_time_choice(tmp_path):
    hermes = FakeHermes()
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge",
                                   hermes_worker=hermes), base_url="http://127.0.0.1")
    path = "/api/hermes/approval"
    body = {"request_id": "pending-1", "choice": "once"}
    assert client.post(path, json=body).status_code == 401
    client.post("/api/login", json={"token": "test-access-token-for-bridge"})
    assert client.post(path, json=body, headers={"origin": "https://example.com"}).status_code == 403
    assert client.post(path, json={"request_id": "pending-1", "choice": "always"}).status_code == 400
    assert hermes.approvals == []
    assert client.post(path, json=body).json() == {"ok": True, "choice": "once"}
    assert hermes.approvals == [("pending-1", "once")]


def test_page_and_assets_do_not_use_stale_browser_cache(tmp_path):
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge"),
                        base_url="http://127.0.0.1")
    for path in ("/", "/assets/app.js", "/assets/style.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"


def test_only_explicit_tailnet_host_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOT_TAILNET_HOST", "robot.example.ts.net")
    app = create_app(tmp_path, token="test-access-token-for-bridge")
    client = TestClient(app, base_url="https://robot.example.ts.net")
    login = client.post("/api/login", json={"token": "test-access-token-for-bridge"})
    assert login.status_code == 200
    assert "secure" in login.headers["set-cookie"].lower()
    assert client.get("/api/status").status_code == 200
    outsider = TestClient(app, base_url="https://other.example.ts.net")
    assert outsider.get("/").status_code == 400
