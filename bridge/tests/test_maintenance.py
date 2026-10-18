import logging
from logging.handlers import RotatingFileHandler
import sqlite3

import pytest
from fastapi.testclient import TestClient

from bridge.app.main import create_app
from bridge.app.maintenance import BRIDGE_VERSION, check_database, MaintenanceStatus, SCHEMA_VERSION
from bridge.app.storage import initialize, add_message
from bridge.run import logging_config, rotate_startup_logs


def test_readonly_check_and_migration_preserve_existing_messages(tmp_path):
    database = tmp_path / 'messages.sqlite3'
    assert check_database(database)['state'] == 'new'
    initialize(database)
    add_message(database, 'hermes', 'must stay', delivery='completed')
    original = database.read_bytes()
    assert check_database(database)['state'] == 'ok'
    assert database.read_bytes() == original
    initialize(database)
    with sqlite3.connect(database) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        assert db.execute('SELECT text FROM messages').fetchone()[0] == 'must stay'


def test_corrupt_store_stops_before_replacing_original(tmp_path):
    database = tmp_path / 'messages.sqlite3'
    database.write_bytes(b'not a sqlite database, preserve these bytes')
    original = database.read_bytes()
    with pytest.raises(RuntimeError, match='未自动重建'):
        create_app(tmp_path, token='test-access-token')
    assert database.read_bytes() == original
    assert not list(tmp_path.glob('*backup*'))


def test_future_database_is_never_downgraded(tmp_path):
    database = tmp_path / 'messages.sqlite3'
    initialize(database)
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA user_version=99')
    original = database.read_bytes()
    with pytest.raises(RuntimeError, match='新版本'):
        check_database(database)
    with pytest.raises(RuntimeError, match='停止写入'):
        initialize(database)
    assert database.read_bytes() == original


def test_busy_read_check_is_deferred_without_damaging_store(tmp_path):
    database = tmp_path / 'messages.sqlite3'
    initialize(database)
    with sqlite3.connect(database) as writer:
        writer.execute('BEGIN EXCLUSIVE')
        assert check_database(database, budget_seconds=.01)['state'] == 'deferred'
    assert check_database(database)['state'] == 'ok'


def test_runtime_logging_rotates_with_a_bounded_file_count(tmp_path):
    handler_config = logging_config(tmp_path, max_bytes=256, backups=2)['handlers']['runtime']
    handler = RotatingFileHandler(handler_config['filename'], maxBytes=handler_config['maxBytes'],
                                  backupCount=handler_config['backupCount'], encoding='utf-8')
    try:
        for index in range(100):
            handler.emit(logging.LogRecord('maintenance-test', logging.INFO, '', 0,
                                          f'entry-{index:03d} ' + 'x' * 60, (), None))
    finally:
        handler.close()
    files = list(tmp_path.glob('bridge.runtime.log*'))
    assert len(files) == 3
    assert all(path.stat().st_size < 256 for path in files)
    assert 'entry-099' in (tmp_path / 'bridge.runtime.log').read_text()
    assert not any('entry-000' in path.read_text() for path in files)


def test_bootstrap_rotation_only_changes_owned_logs(tmp_path):
    for index in range(5):
        (tmp_path / 'bridge.stderr.log').write_text(f'start {index}')
        rotate_startup_logs(tmp_path)
    assert (tmp_path / 'bridge.stderr.log.1').read_text() == 'start 4'
    assert (tmp_path / 'bridge.stderr.log.3').read_text() == 'start 2'
    assert not (tmp_path / 'bridge.stderr.log.4').exists()
    unrelated = tmp_path / 'harness-bridge.log'
    unrelated.write_text('untouched')
    rotate_startup_logs(tmp_path)
    assert unrelated.read_text() == 'untouched'


def test_maintenance_metrics_in_diagnostics_are_content_free(tmp_path, monkeypatch):
    app = create_app(tmp_path, token='test-access-token')
    for worker in (app.state.hermes, app.state.harness):
        monkeypatch.setattr(worker, 'snapshot', lambda: {'available': False})
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.get('/health').json()['version'] == BRIDGE_VERSION
    client.post('/api/login', json={'token': 'test-access-token'})
    result = client.get('/api/diagnostics').json()['maintenance']
    assert result['database']['state'] == 'ok'
    assert result['version'] == BRIDGE_VERSION
    assert result['disk_free_bytes'] > 0
    assert str(tmp_path) not in str(result)


def test_metrics_report_low_disk_space_without_deleting_anything(tmp_path, monkeypatch):
    from collections import namedtuple
    usage = namedtuple('usage', 'total used free')
    monkeypatch.setattr('bridge.app.maintenance.shutil.disk_usage', lambda _: usage(1000, 999, 1))
    status = MaintenanceStatus(tmp_path, {'state': 'ok'})
    assert status.snapshot()['low_disk_space'] is True
