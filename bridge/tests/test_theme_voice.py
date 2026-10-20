from fastapi.testclient import TestClient

from bridge.app.main import create_app
from bridge.app.storage import get_setting
from bridge.app.tts import remember_voice, selected_voice


def client_for(app):
    client = TestClient(app, base_url="http://127.0.0.1")
    client.post("/api/login", json={"token": "theme-test-key"})
    return client


def test_theme_switch_binds_voice_and_restart_repairs_stale_selection(tmp_path, monkeypatch):
    calls = []

    def choose(directory, voice):
        calls.append(voice)
        remember_voice(directory, voice)

    monkeypatch.setattr("bridge.app.main.set_selected_voice", choose)
    app = create_app(tmp_path, token="theme-test-key")
    client = client_for(app)
    assert selected_voice(tmp_path) == "paimon"
    result = client.post("/api/device/theme", json={"theme": "qiuqiu"})
    assert result.status_code == 200
    assert result.json()["voice"] == "cosyvoice"
    assert selected_voice(tmp_path) == "cosyvoice"
    assert app.state.device.snapshot()["desired_theme"] == 1
    assert client.post("/api/tts/voice", json={"voice": "paimon"}).status_code == 400
    remember_voice(tmp_path, "paimon")  # An old/manual choice cannot detach the binding.
    restarted = create_app(tmp_path, token="theme-test-key")
    assert selected_voice(tmp_path) == "cosyvoice"
    assert restarted.state.device.snapshot()["desired_theme"] == 1
    assert client_for(restarted).post("/api/device/theme", json={"theme": "dsh_pet"}).status_code == 200
    assert selected_voice(tmp_path) == "paimon"
    assert calls == ["cosyvoice", "paimon"]


def test_missing_bound_model_keeps_the_previous_theme_and_voice(tmp_path, monkeypatch):
    app = create_app(tmp_path, token="theme-test-key")

    def unavailable(*_):
        raise RuntimeError("voice unavailable")

    monkeypatch.setattr("bridge.app.main.set_selected_voice", unavailable)
    response = client_for(app).post("/api/device/theme", json={"theme": "qiuqiu"})
    assert response.status_code == 503
    assert selected_voice(tmp_path) == "paimon"
    assert get_setting(tmp_path / "messages.sqlite3", "display_theme") == "dsh_pet"
    assert app.state.device.snapshot()["desired_theme"] == 2


def test_animation_panel_owns_all_audition_controls():
    from pathlib import Path
    from html.parser import HTMLParser

    class PanelParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.panel = False
            self.controls = set()

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "section":
                self.panel = attrs.get("id") == "display-panel"
            if self.panel and attrs.get("id"):
                self.controls.add(attrs["id"])

        def handle_endtag(self, tag):
            if tag == "section":
                self.panel = False

    html = (Path(__file__).resolve().parents[2] / "web-client/index.html").read_text(encoding="utf-8")
    parser = PanelParser()
    parser.feed(html)
    assert {"bound-voice", "tts-form", "speak-text", "voice-test-language", "tts-error"} <= parser.controls
    assert "voice-tools-toggle" not in html
    assert 'value="yue"' not in html
