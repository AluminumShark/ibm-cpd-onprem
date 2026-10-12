"""Offline test fixtures — nothing here touches a real cluster."""
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

ALL_CPD_VARS = (
    "CPD_CONFIG", "CPD_URL", "CPD_USERNAME", "CPD_API_KEY", "CPD_SPACE_ID",
    "CPD_PROJECT_ID", "CPD_DEPLOYMENT_ID", "CPD_WXO_INSTANCE_URL",
    "CPD_VERIFY_SSL",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No CPD_* leaks in from the developer's own shell."""
    for name in ALL_CPD_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Write a config and point $CPD_CONFIG at it."""
    def _write(**values):
        p = tmp_path / "config.json"
        p.write_text(json.dumps(values), encoding="utf-8")
        monkeypatch.setenv("CPD_CONFIG", str(p))
        return p
    return _write
