"""Every documented CPD_* variable must actually override the config file."""
import pytest

import cpd_config as C


def test_env_var_overrides_config(config_file, monkeypatch):
    config_file(url="https://from-file.example")
    monkeypatch.setenv("CPD_URL", "https://from-env.example")
    assert C.get("url") == "https://from-env.example"


def test_config_used_when_env_absent(config_file):
    config_file(url="https://from-file.example")
    assert C.get("url") == "https://from-file.example"


def test_verify_ssl_defaults_to_false_for_self_signed(config_file):
    config_file(url="https://x")
    assert C.get("verify_ssl") is False


def test_verify_ssl_env_applies_when_config_is_silent(config_file, monkeypatch):
    config_file(url="https://x")
    monkeypatch.setenv("CPD_VERIFY_SSL", "1")
    assert C.get("verify_ssl") is True


@pytest.mark.parametrize("stored", [True, False])
def test_verify_ssl_env_overrides_a_stored_value(config_file, monkeypatch, stored):
    """cpd_init.py always writes verify_ssl, so the stored value must not win."""
    config_file(url="https://x", verify_ssl=stored)
    monkeypatch.setenv("CPD_VERIFY_SSL", "0")
    assert C.get("verify_ssl") is False
    monkeypatch.setenv("CPD_VERIFY_SSL", "1")
    assert C.get("verify_ssl") is True


def test_explicit_config_path_wins_over_the_user_file(config_file):
    p = config_file(url="https://explicit.example")
    assert C.active_config() == p
