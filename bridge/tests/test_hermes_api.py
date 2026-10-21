import urllib.error
from unittest.mock import Mock

import pytest

from bridge.app.hermes_api import HermesRunsClient


def client(tmp_path):
    key = tmp_path / 'key'
    key.write_text('test-only-key-long-enough')
    return HermesRunsClient(key)


def test_refused_connection_has_actionable_error(tmp_path):
    api = client(tmp_path)
    api._opener.open = Mock(side_effect=urllib.error.URLError(ConnectionRefusedError(10061, 'refused')))
    with pytest.raises(RuntimeError, match='未启动.*8642'):
        api.capabilities()


def test_health_caches_failure_then_recovers(tmp_path, monkeypatch):
    api = client(tmp_path)
    clock = [10.0]
    monkeypatch.setattr('bridge.app.hermes_api.time.monotonic', lambda: clock[0])
    api._request = Mock(side_effect=[RuntimeError('unavailable'), {'object': 'capabilities'}])
    assert api.health_snapshot() == {'available': False, 'error': 'unavailable'}
    assert not api.health_snapshot()['available']
    assert api._request.call_count == 1
    clock[0] += 6
    assert api.health_snapshot() == {'available': True, 'error': None}
    api._request.assert_called_with('GET', '/v1/capabilities', timeout=.8)


def test_timeout_is_distinct(tmp_path):
    api = client(tmp_path)
    api._opener.open = Mock(side_effect=TimeoutError())
    with pytest.raises(RuntimeError, match='响应超时'):
        api.capabilities()
