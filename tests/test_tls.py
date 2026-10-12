"""TLS stays permissive by default, but says so and can be tightened."""
import ssl

import pytest

import cpd_config as C


@pytest.fixture(autouse=True)
def reset_warning_state():
    C._warned.clear()
    yield
    C._warned.clear()


def test_verification_off_is_announced_once(config_file, capsys):
    config_file(url="https://x")
    C._ctx(False)
    C._ctx(False)
    err = capsys.readouterr().err
    assert "TLS verification is OFF" in err
    assert err.count("TLS verification is OFF") == 1, "must not nag per request"


def test_verification_off_disables_checks(config_file):
    config_file(url="https://x")
    ctx = C._ctx(False)
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_verification_on_keeps_checks_and_stays_quiet(config_file, capsys):
    config_file(url="https://x")
    ctx = C._ctx(True)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert "TLS verification is OFF" not in capsys.readouterr().err


def test_ca_bundle_is_loaded_when_verifying(config_file, monkeypatch, tmp_path):
    """A real PEM is needed, so borrow the one certifi-less Python ships with."""
    bundle = tmp_path / "ca.pem"
    bundle.write_text(ssl.get_default_verify_paths().cafile and
                      open(ssl.get_default_verify_paths().cafile).read() or "",
                      encoding="utf-8")
    if not bundle.read_text(encoding="utf-8").strip():
        pytest.skip("no system CA file to copy on this machine")
    config_file(url="https://x")
    monkeypatch.setenv("CPD_CA_BUNDLE", str(bundle))
    ctx = C._ctx(True)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.cert_store_stats()["x509_ca"] > 0


def test_a_missing_ca_bundle_fails_clearly(config_file, monkeypatch, tmp_path):
    config_file(url="https://x")
    monkeypatch.setenv("CPD_CA_BUNDLE", str(tmp_path / "nope.pem"))
    with pytest.raises(SystemExit) as e:
        C._ctx(True)
    assert "nope.pem" in str(e.value)


def test_ca_bundle_is_ignored_when_verification_is_off(config_file, monkeypatch, tmp_path):
    config_file(url="https://x")
    monkeypatch.setenv("CPD_CA_BUNDLE", str(tmp_path / "nope.pem"))
    ctx = C._ctx(False)          # must not blow up on the missing file
    assert ctx.verify_mode == ssl.CERT_NONE
