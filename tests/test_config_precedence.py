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


class TestExplicitConfigNotYetCreated:
    """$CPD_CONFIG naming a file that does not exist yet — the second-cluster
    case. Falling through to another file would read cluster 1's settings and
    let the wizard save cluster 2's over them."""

    @pytest.fixture
    def cluster1(self, tmp_path, monkeypatch):
        user = tmp_path / "home" / "config.json"
        user.parent.mkdir()
        user.write_text('{"url": "https://cluster1.example", "api_key": "k1"}',
                        encoding="utf-8")
        monkeypatch.setattr(C, "USER_CONFIG", user)
        monkeypatch.setattr(C, "CONFIG_PATH", user)
        monkeypatch.setattr(C, "REPO_CONFIG", tmp_path / "repo" / "config.json")
        new = tmp_path / "cluster2.json"
        monkeypatch.setenv("CPD_CONFIG", str(new))
        return new

    def test_the_wizard_writes_the_explicit_path(self, cluster1):
        assert C.write_target() == cluster1

    def test_nothing_is_read_from_another_cluster(self, cluster1):
        assert C.active_config() is None
        assert C.get("url") is None
        assert C.get("api_key") is None

    def test_without_an_override_the_wizard_updates_the_file_in_effect(
            self, cluster1, monkeypatch):
        monkeypatch.delenv("CPD_CONFIG")
        assert C.write_target() == C.USER_CONFIG


def test_cpd_version_env_overrides_the_config(config_file, monkeypatch):
    """wx_connect.py read the file first, the reverse of every other setting."""
    config_file(url="https://x", cpd_version="5.2")
    assert C.get("cpd_version") == "5.2"
    monkeypatch.setenv("CPD_VERSION", "5.3")
    assert C.get("cpd_version") == "5.3"
