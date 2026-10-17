"""The store directory must be pinned and single, or the message database forks.

A scheduled task or service wrapper that resolves a different ``LOCALAPPDATA``
used to mint a second access token and a second empty database, which made the
user's own key stop working. These tests lock the guard in place.
"""

import pytest
from fastapi.testclient import TestClient

from bridge.app.main import create_app
from bridge.app.security import (ALLOW_INIT_ENV, ANCHOR_ENV, DATA_DIR_ENV, DataDirConflict,
                                 anchor_path, record_or_verify_data_dir, resolve_data_dir)


def test_resolve_data_dir_prefers_the_explicit_pin(tmp_path):
    path, source = resolve_data_dir({DATA_DIR_ENV: str(tmp_path / "store"),
                                     "LOCALAPPDATA": "C:/elsewhere"})
    assert path == tmp_path / "store"
    assert source == "env"


def test_resolve_data_dir_rejects_a_relative_pin():
    with pytest.raises(DataDirConflict):
        resolve_data_dir({DATA_DIR_ENV: "store"})


def test_resolve_data_dir_falls_back_without_localappdata():
    path, source = resolve_data_dir({"LOCALAPPDATA": "C:/Users/example/AppData/Local"})
    assert path.name == "DesktopAiRobot"
    assert source == "localappdata"
    assert resolve_data_dir({})[1] == "home"


def test_anchor_path_can_be_redirected_for_tests(tmp_path):
    assert anchor_path({ANCHOR_ENV: str(tmp_path / "a.txt")}) == tmp_path / "a.txt"
    assert anchor_path({"PROGRAMDATA": "C:/ProgramData"}).name == "data-dir.txt"


def test_first_run_writes_the_anchor_then_stays_consistent(tmp_path):
    store, anchor = tmp_path / "store", tmp_path / "anchor" / "data-dir.txt"
    first = record_or_verify_data_dir(store, "localappdata", anchor, environ={})
    assert first["anchored"] is True
    assert anchor.read_text(encoding="utf-8").strip() == str(store.resolve())

    again = record_or_verify_data_dir(store, "localappdata", anchor, environ={})
    assert again["consistent"] is True
    assert "adopted" not in again


def test_a_second_store_is_refused_instead_of_forking(tmp_path):
    anchor = tmp_path / "anchor" / "data-dir.txt"
    real, intruder = tmp_path / "real", tmp_path / "intruder"
    record_or_verify_data_dir(real, "localappdata", anchor, environ={})

    with pytest.raises(DataDirConflict) as excinfo:
        record_or_verify_data_dir(intruder, "localappdata", anchor, environ={})
    assert str(real.resolve()) in str(excinfo.value)
    assert str(intruder.resolve()) in str(excinfo.value)
    # The anchored store is untouched, and the intruder never became reachable.
    assert anchor.read_text(encoding="utf-8").strip() == str(real.resolve())


def test_explicit_opt_in_adopts_a_new_store(tmp_path):
    anchor = tmp_path / "anchor" / "data-dir.txt"
    old, new = tmp_path / "old", tmp_path / "new"
    record_or_verify_data_dir(old, "localappdata", anchor, environ={})

    adopted = record_or_verify_data_dir(new, "env", anchor, environ={ALLOW_INIT_ENV: "1"})
    assert adopted["adopted"] is True
    assert anchor.read_text(encoding="utf-8").strip() == str(new.resolve())


def test_unwritable_anchor_degrades_instead_of_blocking_startup(tmp_path):
    # A regular file cannot act as a parent directory, so anchoring must fail
    # softly rather than taking the whole Bridge down with it.
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    anchor = blocker / "data-dir.txt"

    record = record_or_verify_data_dir(tmp_path / "store", "env", anchor, environ={})
    assert record["anchored"] is False
    assert record["consistent"] is True


def test_create_app_with_an_explicit_dir_never_touches_the_anchor(tmp_path, monkeypatch):
    anchor = tmp_path / "anchor-not-used.txt"
    monkeypatch.setenv(ANCHOR_ENV, str(anchor))
    client = TestClient(create_app(tmp_path / "store", token="test-access-token-for-bridge"),
                        base_url="http://127.0.0.1")
    assert client.get("/health").json() == {"ok": True}
    assert not anchor.exists()


def test_status_reports_which_store_is_in_use(tmp_path):
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge"),
                        base_url="http://127.0.0.1")
    client.post("/api/login", json={"token": "test-access-token-for-bridge"})
    store = client.get("/api/status").json()["store"]
    assert store["source"] == "explicit"
    assert store["consistent"] is True
    assert store["path"] == str(tmp_path)
