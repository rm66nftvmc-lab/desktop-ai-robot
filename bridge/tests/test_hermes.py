import sqlite3

from bridge.app.hermes import HermesWorker, latest_desktop_session, parse_result
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


def test_new_hermes_session_is_reused_until_a_newer_desktop_window_appears(tmp_path):
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
    assert worker.enqueue(3, "现在继续桌面")
    assert worker._jobs.get_nowait()[2] == "desktop-old"
