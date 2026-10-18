import sqlite3
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bridge.app.conversations import Conversations, bind_draft, message_route
from bridge.app.main import create_app
from bridge.app.hermes import HermesWorker
from bridge.app.storage import add_message, initialize


def setup_catalog(tmp_path):
    database = tmp_path / 'bridge.db'
    initialize(database)
    state = tmp_path / 'state.db'
    with sqlite3.connect(state) as db:
        db.execute('CREATE TABLE sessions(id TEXT,title TEXT,last_activity_at REAL,archived INTEGER,hidden INTEGER,parent_session_id TEXT)')
        db.executemany('INSERT INTO sessions VALUES(?,?,?,0,0,?)', [
            ('one', '第一会话', 1, None), ('two', '第二会话', 2, None), ('child', '子任务', 3, 'one')])
        db.execute('CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,active INTEGER)')
        db.executemany('INSERT INTO messages VALUES(?,?,?,?,1,1)', [
            (1, 'one', 'user', '第一条'), (2, 'one', 'assistant', '第一个回答'),
            (3, 'two', 'assistant', '第二个回答'), (4, 'one', 'system', '不可显示的系统指令')])
    hermes = SimpleNamespace(hermes_home=tmp_path)
    return database, Conversations(database, hermes, None)


def test_native_catalog_and_history_are_scoped_and_exclude_internal_messages(tmp_path):
    database, catalog = setup_catalog(tmp_path)
    assert [s['id'] for s in catalog.catalog('hermes')['items']] == ['two', 'one']
    assert [m['text'] for m in catalog.history('hermes', 'one')] == ['第一条', '第一个回答']
    assert [m['text'] for m in catalog.history('hermes', 'two')] == ['第二个回答']
    with pytest.raises(ValueError):
        catalog.history('hermes', 'child')
    with pytest.raises(ValueError):
        catalog.create('doubao_web')


def test_new_draft_is_empty_then_binds_without_switching_conversation(tmp_path):
    database, catalog = setup_catalog(tmp_path)
    draft = catalog.create('hermes')
    assert catalog.history('hermes', draft['id']) == []
    item = add_message(database, 'hermes', '新问题', conversation_id=draft['id'], delivery='queued')
    assert message_route(database, item['id'], 'two') == (None, draft['id'])
    bind_draft(database, draft['id'], 'one')
    assert message_route(database, item['id'], 'two') == ('one', draft['id'])
    assert catalog.resolve('hermes', draft['id']) == 'one'
    items = catalog.catalog('hermes')['items']
    assert sum(s['id'] in {'one', draft['id']} for s in items) == 1
    with pytest.raises(ValueError):
        catalog.resolve('deepseek_harness', draft['id'])


def test_explicit_session_routing_overrides_latest_desktop_session(tmp_path):
    database, catalog = setup_catalog(tmp_path)
    item = add_message(database, 'hermes', '继续第一会话', conversation_id='one')
    assert message_route(database, item['id'], 'two') == ('one', 'one')


def test_queued_messages_in_new_conversation_create_only_one_native_session(tmp_path):
    database, catalog = setup_catalog(tmp_path)
    draft = catalog.create('hermes')
    worker = HermesWorker(database, hermes_home=tmp_path)
    worker.executable = 'fake-hermes'
    worker._preferred_session_info = lambda: {'id': 'two'}
    calls = []
    def ask(text, session):
        calls.append(session)
        worker._last_run_session = session or 'generated'
        return '回答'
    worker._ask = ask
    for text in ['第一条', '第二条']:
        item = add_message(database, 'hermes', text, delivery='queued', conversation_id=draft['id'])
        assert worker.enqueue(item['id'], text)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with sqlite3.connect(database) as db:
                if db.execute("SELECT COUNT(*) FROM messages WHERE role='assistant'").fetchone()[0] == 2:
                    break
            time.sleep(.01)
        assert calls == [None, 'generated']
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT DISTINCT conversation_id FROM messages").fetchall() == [(draft['id'],)]
    finally:
        worker.stop()


def test_session_api_auth_origin_drafts_and_cross_target_rejection(tmp_path):
    app = create_app(tmp_path, token='test-access-token-for-bridge')
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.get('/api/sessions?source=hermes').status_code == 401
    assert client.post('/api/sessions', json={'source': 'hermes'}).status_code == 401
    client.post('/api/login', json={'token': 'test-access-token-for-bridge'})
    assert client.post('/api/sessions', json={'source': 'hermes'}, headers={'origin': 'https://example.com'}).status_code == 403
    assert client.post('/api/sessions', json={'source': 'doubao_web'}).status_code == 400
    draft = client.post('/api/sessions', json={'source': 'hermes'}).json()['item']
    assert client.get('/api/messages', params={'source': 'hermes', 'session_id': draft['id']}).json() == {'items': []}
    assert client.get('/api/messages', params={'source': 'deepseek_harness', 'session_id': draft['id']}).status_code == 404
    assert client.post('/api/messages', json={'source': 'deepseek_harness', 'session_id': draft['id'], 'text': '不能串到另一个AI'}).status_code == 400


def test_batch_delete_removes_all_selected_drafts_and_reports_missing_items(tmp_path):
    app = create_app(tmp_path, token='test-access-token-for-bridge')
    client = TestClient(app, base_url='http://127.0.0.1')
    client.post('/api/login', json={'token': 'test-access-token-for-bridge'})
    first = client.post('/api/sessions', json={'source': 'hermes'}).json()['item']
    second = client.post('/api/sessions', json={'source': 'hermes'}).json()['item']

    result = client.request('DELETE', '/api/sessions/batch', json={
        'source': 'hermes', 'session_ids': [first['id'], second['id'], 'missing-session'],
    })
    assert result.status_code == 200
    payload = result.json()
    assert {item['session_id'] for item in payload['deleted']} == {first['id'], second['id']}
    assert [item['session_id'] for item in payload['failed']] == ['missing-session']
    remaining_ids = {item['id'] for item in client.get(
        '/api/sessions', params={'source': 'hermes'}).json()['items']}
    assert first['id'] not in remaining_ids
    assert second['id'] not in remaining_ids


def test_purged_harness_session_never_reappears_from_stale_native_catalog(tmp_path):
    database, catalog = setup_catalog(tmp_path)
    class CachedHost:
        def rpc(self, method):
            return {'items': [{'sessionId': 'disposable-native', 'updatedAt': 1}]}
        def delete_session_permanently(self, session_id):
            assert session_id == 'disposable-native'
    from types import SimpleNamespace
    catalog.harness = SimpleNamespace(client=CachedHost(), snapshot=lambda: {'running': False, 'pending': 0})
    assert catalog.catalog('deepseek_harness')['items']
    assert catalog.delete('deepseek_harness', 'disposable-native')['native_session_deleted']
    assert catalog.catalog('deepseek_harness')['items'] == []
    with pytest.raises(ValueError):
        catalog.resolve('deepseek_harness', 'disposable-native')
    # Filtering is durable, not just a transient browser optimization.
    restored = type(catalog)(database, catalog.hermes, catalog.harness)
    assert restored.catalog('deepseek_harness')['items'] == []
    from bridge.app.harness import HarnessWorker
    host = CachedHost()
    host.installed = False
    host.exe = tmp_path / 'not-installed.exe'
    worker = HarnessWorker(database, tmp_path, client=host)
    assert worker._preferred_session_info() is None
