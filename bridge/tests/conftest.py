"""Keep module-level app creation away from the user's active Bridge store."""

import os
from pathlib import Path
import tempfile


def pytest_configure(config):
    config._bridge_test_directory = tempfile.TemporaryDirectory(prefix="bridge-tests-")
    directory = Path(config._bridge_test_directory.name)
    settings = {"ROBOT_DATA_DIR": str(directory / "store"),
                "ROBOT_DATA_ANCHOR": str(directory / "anchor.txt"),
                "ROBOT_HARNESS_EXE": str(directory / "not-installed.exe")}
    config._bridge_original_environment = {key: os.environ.get(key) for key in settings}
    os.environ.update(settings)


def pytest_unconfigure(config):
    for key, original in getattr(config, "_bridge_original_environment", {}).items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original
    if hasattr(config, "_bridge_test_directory"):
        config._bridge_test_directory.cleanup()
