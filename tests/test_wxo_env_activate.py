"""Offline tests for wxo_env_activate — a fake `orchestrate`, no cluster.

It exists because the documented one-liner `env activate -a "$CPD_API_KEY"`
only works when the key is in the environment, and `env add` crashes on a
non-interactive re-run. The guiding assertion: the CPD key never reaches our
output.
"""
import subprocess

import pytest

import wxo_env_activate as act

KEY = "cpd-KEY-FROM-THE-CONFIG-FILE-42"
WXO = "https://cpd.example/orchestrate/cpd-instance-operands/instances/123"


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def calls(monkeypatch):
    """Record every subprocess.run as (argv, kwargs); answer success."""
    seen = []

    def fake(cmd, *a, **k):
        seen.append((list(cmd), k))
        return _FakeProc()
    monkeypatch.setattr(subprocess, "run", fake)
    return seen


@pytest.fixture
def stored_key(config_file):
    """The wizard's option A: the key lives in config.json, not the env."""
    return config_file(url="https://cpd.example", username="admin",
                       api_key=KEY, wxo_instance_url=WXO)


def _add(calls):
    return next((c, k) for c, k in calls if c[1:3] == ["env", "add"])


def _activate(calls):
    return next(c for c, _ in calls if c[1:3] == ["env", "activate"])


def test_a_key_stored_in_the_config_file_is_used(stored_key, calls):
    assert act.activate() == 0
    cmd = _activate(calls)
    assert cmd[cmd.index("-a") + 1] == KEY
    assert cmd[cmd.index("-u") + 1] == "admin"
    assert "--skip-version-check" in cmd


def test_the_env_var_still_overrides_the_file(stored_key, calls, monkeypatch):
    monkeypatch.setenv("CPD_API_KEY", "from-env")
    act.activate()
    cmd = _activate(calls)
    assert cmd[cmd.index("-a") + 1] == "from-env"


def test_env_add_targets_the_wxo_instance_as_cpd(stored_key, calls):
    act.activate(name="cpd-test")
    cmd, _ = _add(calls)
    assert cmd[cmd.index("-n") + 1] == "cpd-test"
    assert cmd[cmd.index("-u") + 1] == WXO
    assert cmd[cmd.index("-t") + 1] == "cpd"
    assert _activate(calls)[3] == "cpd-test"


def test_a_rerun_answers_the_update_prompt(stored_key, calls):
    """`env add` on an existing name calls input('... (Y/n)'); without an
    answer on stdin a non-interactive shell dies with EOFError."""
    act.activate()
    _, kwargs = _add(calls)
    assert kwargs.get("input") == "y\n"


@pytest.mark.parametrize("missing,var", [("api_key", "CPD_API_KEY"),
                                         ("username", "CPD_USERNAME"),
                                         ("wxo_instance_url", "CPD_WXO_INSTANCE_URL")])
def test_a_missing_setting_stops_before_the_adk_prompts(config_file, calls, capsys,
                                                       missing, var):
    """An empty -a/-u makes the ADK fall back to getpass, which hangs."""
    values = dict(url="https://cpd.example", username="admin", api_key=KEY,
                  wxo_instance_url=WXO)
    del values[missing]
    config_file(**values)
    assert act.activate() == 2
    assert calls == []
    assert var in capsys.readouterr().err


def test_the_key_never_reaches_our_output(stored_key, monkeypatch, capsys):
    def echoing(cmd, *a, **k):
        return _FakeProc(stdout="activated with %s\n" % KEY,
                         stderr="debug: -a %s\n" % KEY)
    monkeypatch.setattr(subprocess, "run", echoing)
    act.activate()
    out = capsys.readouterr()
    assert KEY not in out.out and KEY not in out.err
    assert "-a ***" in out.out


@pytest.mark.parametrize("verify,bundle,expect", [
    (False, None, ["--insecure"]),
    (True, "/etc/ca.pem", ["--verify", "/etc/ca.pem"]),
    (True, None, []),
])
def test_tls_flags_follow_the_config(config_file, calls, monkeypatch,
                                     verify, bundle, expect):
    config_file(url="https://cpd.example", username="admin", api_key=KEY,
                wxo_instance_url=WXO, verify_ssl=verify)
    if bundle:
        monkeypatch.setenv("CPD_CA_BUNDLE", bundle)
    act.activate()
    cmd, _ = _add(calls)
    tail = cmd[cmd.index("cpd") + 1:]
    assert tail == expect


def test_a_failed_env_add_skips_activation(stored_key, monkeypatch, capsys):
    seen = []

    def failing(cmd, *a, **k):
        seen.append(list(cmd))
        return _FakeProc(returncode=1, stderr="boom")
    monkeypatch.setattr(subprocess, "run", failing)
    assert act.activate() != 0
    assert len(seen) == 1


def test_a_missing_cli_names_the_install_command(stored_key, monkeypatch, capsys):
    def absent(cmd, *a, **k):
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(subprocess, "run", absent)
    assert act.activate() == 1
    assert "uv sync" in capsys.readouterr().err
