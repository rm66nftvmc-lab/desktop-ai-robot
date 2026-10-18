"""The Harness delete plugin must ship with the repo, not only on one machine.

Bridge's permanent conversation deletion calls two Host routes registered by
``dsh-plugin-session-delete``. That package used to be an external, GitHub-only
install, so a clean checkout silently lost the feature (HTTP 404). These tests
pin the vendored, offline-installable copy in ``plugins/``.
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dsh-plugin-session-delete"
MANIFEST = PLUGIN / "package.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_vendored_plugin_manifest_is_the_expected_release():
    manifest = _manifest()
    assert manifest["name"] == "dsh-plugin-session-delete"
    assert manifest["version"] == "0.3.4"
    assert manifest["license"] == "MIT"
    assert manifest["main"] == "lib/index.js"
    assert manifest["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert manifest["dsh"]["client"]["platform"] == "web"


def test_vendored_plugin_ships_prebuilt_node_and_browser_halves():
    # Requiring both halves catches a copy that forgot lib/client.js (the menu
    # row) or lib/index.js (the authenticated Host routes).
    for relative, needle in (
        ("lib/index.js", "/api/session.delete"),
        ("lib/index.js", "/api/session.purge"),
        ("lib/client.js", "sidebar.workspaces.session.menu.item"),
    ):
        path = PLUGIN / relative
        assert path.is_file(), f"missing built file: {relative}"
        assert path.stat().st_size > 1024, f"{relative} looks truncated"
        assert needle in path.read_text(encoding="utf-8", errors="replace")


def test_vendored_plugin_bundle_patch_inserts_the_row():
    patch = (PLUGIN / "cordis.patch.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s*-\s*insert:", patch, re.MULTILINE)
    assert "id: session-delete" in patch
    assert "name: 'dsh-plugin-session-delete'" in patch


def test_vendored_plugin_keeps_its_license():
    license_text = (PLUGIN / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Permission is hereby granted" in license_text


def test_offline_installer_points_at_the_vendored_copy():
    script = (REPO / "scripts" / "install_dsh_plugin.ps1").read_text(encoding="utf-8")
    assert "plugins\\dsh-plugin-session-delete" in script
    assert "dsh.profile.bundles" in script
    assert "file:" in script
    # The installer must not require a network install.
    assert "pnpm add" not in script
    assert "github:" not in script


def test_vendored_plugin_contains_no_machine_specific_absolute_paths():
    for path in PLUGIN.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".js", ".json", ".yml", ".md", ".ts"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "C:\\Users\\" not in text, f"absolute Windows user path leaked into {path}"
        assert "/Users/55243/" not in text, f"absolute user path leaked into {path}"
        assert "AppData\\Local" not in text, f"absolute app-data path leaked into {path}"


@pytest.mark.parametrize("name", ["README.md", "CHANGELOG.md", "README.zh.md"])
def test_vendored_plugin_keeps_its_documentation(name: str):
    assert (PLUGIN / name).stat().st_size > 512
