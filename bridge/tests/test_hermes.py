import io
import sqlite3
import urllib.error

import pytest

from bridge.app.hermes import HermesWorker, latest_desktop_session, parse_result
from bridge.app.hermes_api import HermesRunsClient
from bridge.app.storage import add_message, initialize, list_messages, set_delivery, set_setting


def test_last_visible_desktop_session_and_result_parsing(tmp_path):
    state = tmp_path / "state.db"
    with sqlite3.connect(state) as db:
        db.execute("CREATE TABLE sessions (id TEXT, source TEXT, title TEXT, archived INTEGER, "
                   "hidden INTEGER, last_activity_at REAL)")
        db.executemany("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)", [
            ("old", "desktop", "Old", 0, 0, 1),
            ("latest", "desktop", "Latest", 0, 0, 3),
            ("hidden", "desktop", "Hidden", 0, 1, 9),
            ("bridge", "bridge", "Bridge", 0, 0, 10),
        ])
    assert latest_desktop_session(state) == "latest"
    output = ('{"type":"text","text":"你好"}\n'
              '{"type":"result","session_id":"latest","exit_code":0,"text":"你好！"}\n')
    assert parse_result(output) == ("你好！", "latest")


def test_existing_message_table_is_migrated(tmp_path):
    path = tmp_path / "messages.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, source TEXT, text TEXT, "
                   "created_at TEXT)")
        db.execute("INSERT INTO messages (source, text, created_at) VALUES "
                   "('hermes', '旧消息', '2026-01-01T00:00:00Z')")
    initialize(path)
    item = add_message(path, "hermes", "新消息", delivery="queued")
    set_delivery(path, item["id"], "completed")
    assert [(row["text"], row["delivery"]) for row in list_messages(path, "hermes")] == [
        ("旧消息", "not_configured"), ("新消息", "completed")]


def test_api_session_is_reused_and_desktop_never_becomes_the_default(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    state = tmp_path / "state.db"
    with sqlite3.connect(state) as db:
        db.execute("CREATE TABLE sessions (id TEXT, source TEXT, title TEXT, archived INTEGER, "
                   "hidden INTEGER, last_activity_at REAL)")
        db.executemany("INSERT INTO sessions VALUES (?, ?, ?, 0, 0, ?)", [
            ("desktop-old", "desktop", "Old", 1),
            ("bridge-new", "api_server", "New", 2),
        ])
    set_setting(database, "hermes_session_id", "bridge-new")
    worker = HermesWorker(database, hermes_home=tmp_path)
    worker.executable = "fake-hermes"
    assert worker.enqueue(1, "继续")
    assert worker._jobs.get_nowait()[2] == "bridge-new"
    assert worker.enqueue(2, "另开", new_session=True)
    assert worker._jobs.get_nowait()[2] is None
    with sqlite3.connect(state) as db:
        db.execute("UPDATE sessions SET last_activity_at = 3 WHERE id = 'desktop-old'")
    # Hermes 0.22 refuses API writes into desktop sessions, so a newer desktop
    # turn must not pull the Bridge off its API-created session.
    assert worker.enqueue(3, "桌面更新了也不切")
    assert worker._jobs.get_nowait()[2] == "bridge-new"


def test_only_desktop_sessions_means_create_a_new_api_session(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    state = tmp_path / "state.db"
    with sqlite3.connect(state) as db:
        db.execute("CREATE TABLE sessions (id TEXT, source TEXT, title TEXT, archived INTEGER, "
                   "hidden INTEGER, last_activity_at REAL)")
        db.execute("INSERT INTO sessions VALUES ('desktop-1', 'desktop', 'Desktop', 0, 0, 9)")
    worker = HermesWorker(database, hermes_home=tmp_path)
    assert worker._preferred_session_info() is None


def test_api_refuses_a_desktop_target_before_sending(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    state = tmp_path / "state.db"
    with sqlite3.connect(state) as db:
        db.execute("CREATE TABLE sessions (id TEXT, source TEXT, title TEXT, archived INTEGER, "
                   "hidden INTEGER, last_activity_at REAL)")
        db.execute("INSERT INTO sessions VALUES ('desktop-1', 'desktop', '桌面会话', 0, 0, 9)")
        db.execute("INSERT INTO sessions VALUES ('api-1', 'api_server', 'API 会话', 0, 0, 8)")
    worker = HermesWorker(database, hermes_home=tmp_path, api_client=object())
    with pytest.raises(RuntimeError, match=r'不允许写入非 API 会话.*\+ 新建'):
        worker._check_api_target('desktop-1')
    worker._check_api_target('api-1')
    worker._check_api_target(None)



class _ErrorOpener:
    def __init__(self, body: bytes, status: int = 409):
        self.body, self.status = body, status

    def open(self, request, timeout):
        raise urllib.error.HTTPError(request.full_url, self.status, 'conflict', {},
                                      io.BytesIO(self.body))


def _key(tmp_path):
    path = tmp_path / 'hermes-api-key.txt'
    path.write_text('k' * 32, encoding='utf-8')
    return path


def test_hermes_http_error_surfaces_gateway_code_and_message(tmp_path):
    client = HermesRunsClient(_key(tmp_path))
    client._opener = _ErrorOpener(
        b'{"error": {"code": "session_busy", "message": "session has an active turn"}}')

    with pytest.raises(RuntimeError, match=r'HTTP 409 \(session_busy: session has an active turn\)'):
        client.start_run('hello', 'session-1')


def test_hermes_http_error_without_json_stays_readable(tmp_path):
    client = HermesRunsClient(_key(tmp_path))
    client._opener = _ErrorOpener(b'<html>conflict</html>', status=503)

    with pytest.raises(RuntimeError, match=r'^Hermes API returned HTTP 503$'):
        client.capabilities()
