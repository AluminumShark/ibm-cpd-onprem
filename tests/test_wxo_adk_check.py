"""Offline tests for the ADK/server compatibility check — no cluster, no network.

ADK 2.8.0+ adds `include=global` + `workspace_id` to every agent lookup; a WXO
server without workspace support answers HTTP 500 on /agents/external-chat, so
`agents list/import/export` all fail. The check must catch that before any
write, and stay quiet on an ADK that predates workspaces.
"""
import subprocess

import pytest

import cpd_config as C
import wxo_adk_check as chk
import wxo_setup_agent as setup

VERSION_OUT = ("ADK Version: {v}\nLangflow Version: 1.11.2\n"
               "Developer Edition Image Tags (if not overridden in env file)\n")


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_adk(monkeypatch, version, calls=None):
    """Stand in for `orchestrate --version` (and record any other call)."""
    def fake(cmd, *a, **k):
        if calls is not None:
            calls.append(list(cmd))
        if version is None:
            raise FileNotFoundError(cmd[0])
        return _FakeProc(stdout=VERSION_OUT.format(v=version))
    monkeypatch.setattr(subprocess, "run", fake)


def _fake_server(monkeypatch, status, seen=None):
    monkeypatch.setattr(C, "load_file", lambda path=None: {
        "wxo_instance_url": "https://cpd.example/orchestrate/x/instances/1"})
    monkeypatch.setattr(C, "get_token", lambda cfg=None: "fake-token")

    def fake_http(method, url, token=None, body=None, cfg=None):
        if seen is not None:
            seen.append((method, url))
        return status, {"detail": "An Unexpected Error Occurred."}
    monkeypatch.setattr(C, "http", fake_http)


# --- version parsing -------------------------------------------------------

def test_parse_adk_version_from_cli_banner():
    assert chk.parse_adk_version(VERSION_OUT.format(v="2.18.1")) == (2, 18, 1)


def test_parse_adk_version_returns_none_without_banner():
    assert chk.parse_adk_version("something else entirely") is None


def test_adk_version_is_none_when_cli_missing(monkeypatch):
    _fake_adk(monkeypatch, None)
    assert chk.adk_version() is None


# --- check() ---------------------------------------------------------------

def test_pre_workspace_adk_is_ok_without_probing(monkeypatch):
    _fake_adk(monkeypatch, "2.7.2")
    seen = []
    _fake_server(monkeypatch, 500, seen)
    status, _ = chk.check()
    assert status == "ok"
    assert seen == []                  # no network call for an old-enough ADK


def test_workspace_adk_against_server_without_workspaces(monkeypatch):
    _fake_adk(monkeypatch, "2.18.1")
    seen = []
    _fake_server(monkeypatch, 500, seen)
    status, msg = chk.check()
    assert status == "incompatible"
    assert "2.18.1" in msg
    assert "uv sync --group wxo" in msg
    assert 'pip install "ibm-watsonx-orchestrate==2.7.2"' in msg
    assert seen and "/v1/orchestrate/agents/external-chat" in seen[0][1]
    assert "include=global" in seen[0][1]


def test_workspace_adk_against_server_with_workspaces(monkeypatch):
    _fake_adk(monkeypatch, "2.18.1")
    _fake_server(monkeypatch, 200)
    status, _ = chk.check()
    assert status == "ok"


def test_unexpected_probe_status_is_unknown_not_blocking(monkeypatch):
    _fake_adk(monkeypatch, "2.18.1")
    _fake_server(monkeypatch, 403)
    status, msg = chk.check()
    assert status == "unknown"
    assert "403" in msg


def test_missing_cli_names_the_install_command(monkeypatch):
    _fake_adk(monkeypatch, None)
    status, msg = chk.check()
    assert status == "missing"
    assert "uv sync --group wxo" in msg
    assert "pip install" in msg


@pytest.mark.parametrize("status,code", [("ok", 0), ("unknown", 0),
                                         ("incompatible", 1), ("missing", 1)])
def test_cli_exit_codes(monkeypatch, capsys, status, code):
    monkeypatch.setattr(chk, "check", lambda **k: (status, "msg"))
    assert chk.main([]) == code


# --- wxo_setup_agent stops before any write --------------------------------

def _setup_args(**over):
    base = dict(provider="google", model="gemini-2.5-flash", agent_name="zytest_x",
                connection=None, provider_config=None, env="draft", scope="team",
                display_name=None, model_type="chat", instructions=None,
                style="default", test=None, timeout=60, cleanup=False)
    base.update(over)
    return type("Args", (), base)()


def test_setup_refuses_before_any_write_when_incompatible(monkeypatch, capsys):
    monkeypatch.setattr(chk, "check",
                        lambda **k: ("incompatible", "ADK too new for this server"))
    calls = []
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, *a, **k: calls.append(cmd) or _FakeProc())
    assert setup.do_setup(_setup_args()) == 1
    assert calls == []                 # no connection, model or agent created
    assert "ADK too new for this server" in capsys.readouterr().err
