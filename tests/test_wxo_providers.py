"""Offline tests for the external-provider helpers — no cluster, no network.

A fake `orchestrate` (a recording stand-in for subprocess.run) keeps the
credential step offline; cpd_config.http is monkeypatched for the runs API.
The guiding assertion throughout: a provider secret never reaches our output.
"""
import pytest

import cpd_config as C
import wxo_add_provider as prov
import wxo_run_agent as runner

SECRET = "sk-SUPER-SECRET-VALUE-123"


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _recorder(calls, result=_FakeProc()):
    """Replacement for subprocess.run that records argv and answers canned."""
    def fake(cmd, *a, **k):
        calls.append(list(cmd))
        return result
    return fake


def _providers_file(tmp_path, text):
    p = tmp_path / "providers.env"
    p.write_text(text, encoding="utf-8")
    return str(p)


@pytest.fixture(autouse=True)
def _reset_secrets():
    prov._SECRETS.clear()
    yield
    prov._SECRETS.clear()


# --- field map -------------------------------------------------------------

def test_known_provider_secret_fields():
    fields, known = prov.provider_fields("anthropic")
    assert known is True
    assert fields["secret"] == ["api_key"]

    fields, _ = prov.provider_fields("bedrock")
    assert fields["secret"] == ["aws_access_key_id", "aws_secret_access_key"]
    assert fields["config"] == ["aws_region"]


def test_unknown_provider_defaults_to_api_key():
    fields, known = prov.provider_fields("some-new-provider")
    assert known is False
    assert fields["secret"] == ["api_key"]


def test_env_var_name_convention():
    assert prov.field_env_var("anthropic", "api_key") == "WXO_ANTHROPIC_API_KEY"
    assert prov.field_env_var("mistral-ai", "api_key") == "WXO_MISTRAL_AI_API_KEY"
    assert (prov.field_env_var("bedrock", "aws_secret_access_key")
            == "WXO_BEDROCK_AWS_SECRET_ACCESS_KEY")


# --- providers.env parsing + resolution ------------------------------------

def test_providers_file_ignores_comments_and_blanks(tmp_path):
    path = _providers_file(
        tmp_path,
        "# a comment\n\n   \nWXO_ANTHROPIC_API_KEY=" + SECRET + "\n# trailing\n")
    values = prov.load_providers_file(path)
    assert values == {"WXO_ANTHROPIC_API_KEY": SECRET}


def test_real_env_var_overrides_the_file(tmp_path, monkeypatch):
    path = _providers_file(tmp_path, "WXO_ANTHROPIC_API_KEY=from-file")
    monkeypatch.setenv("WXO_ANTHROPIC_API_KEY", "from-env")
    creds, missing = prov.collect_credentials("anthropic", providers_file=path)
    assert missing == []
    assert creds == {"api_key": "from-env"}


# --- missing credential names the env var, never a value -------------------

def test_missing_credential_names_env_var_not_value(tmp_path, capsys):
    path = _providers_file(tmp_path, "# empty\n")
    rc = prov.add_provider("anthropic", providers_file=path)
    err = capsys.readouterr().err
    assert rc != 0
    assert "WXO_ANTHROPIC_API_KEY" in err
    assert SECRET not in err                      # no secret ever in the message


# --- add_provider issues the expected orchestrate calls --------------------

def test_add_provider_builds_expected_calls(tmp_path, monkeypatch, capsys):
    path = _providers_file(tmp_path, "WXO_ANTHROPIC_API_KEY=" + SECRET)
    calls = []
    monkeypatch.setattr(prov.subprocess, "run", _recorder(calls))

    rc = prov.add_provider("anthropic", connection="wxo_anthropic",
                           env="draft", scope="team", providers_file=path)
    assert rc == 0

    assert ["connections", "add", "-a"] == calls[0][1:4]
    assert calls[1][1:3] == ["connections", "configure"]
    assert "key_value" in calls[1] and "team" in calls[1]
    setcred = calls[2]
    assert setcred[1:3] == ["connections", "set-credentials"]
    # the secret rides on argv (set-credentials has no file/stdin) — expected,
    # documented residual exposure
    assert ("api_key=" + SECRET) in setcred

    out = capsys.readouterr()
    assert SECRET not in out.out                   # but never in OUR output
    assert SECRET not in out.err
    assert "api_key=***" in out.out                # the echo is redacted


def test_bedrock_sets_both_secret_entries(tmp_path, monkeypatch):
    path = _providers_file(
        tmp_path,
        "WXO_BEDROCK_AWS_ACCESS_KEY_ID=AKIA-TEST\n"
        "WXO_BEDROCK_AWS_SECRET_ACCESS_KEY=" + SECRET + "\n")
    calls = []
    monkeypatch.setattr(prov.subprocess, "run", _recorder(calls))
    rc = prov.add_provider("bedrock", connection="wxo_bedrock", providers_file=path)
    assert rc == 0
    setcred = calls[2]
    assert "aws_access_key_id=AKIA-TEST" in setcred
    assert ("aws_secret_access_key=" + SECRET) in setcred


# --- wxo_run_agent parses an assistant reply -------------------------------

def _wire_runs(monkeypatch, messages):
    base = "https://wxo.example"
    monkeypatch.setattr(C, "get_token", lambda cfg=None: "fake-token")
    monkeypatch.setattr(C, "load_file", lambda path=None: {})
    monkeypatch.setattr(
        C, "get",
        lambda key, cfg=None, default=None: base if key == "wxo_instance_url" else default)

    def fake_http(method, url, token=None, body=None, cfg=None):
        if method == "GET" and url.endswith("/v1/orchestrate/agents"):
            return 200, [{"id": "agent-123", "name": "zytest_claude",
                          "llm": "virtual-model/anthropic/claude"}]
        if method == "POST" and url.endswith("/v1/orchestrate/runs"):
            assert body["agent_id"] == "agent-123"
            assert body["message"] == {"role": "user", "content": "ping"}
            return 200, {"thread_id": "thread-9", "run_id": "r", "message_id": "m"}
        if method == "GET" and url.endswith("/threads/thread-9/messages"):
            return 200, messages
        raise AssertionError("unexpected call %s %s" % (method, url))

    monkeypatch.setattr(C, "http", fake_http)


def test_run_agent_returns_assistant_text(monkeypatch, capsys):
    messages = [
        {"role": "user", "content": "ping"},
        {"role": "assistant",
         "content": [{"response_type": "text", "text": "PONG"}]},
    ]
    _wire_runs(monkeypatch, messages)
    text = runner.run_agent("zytest_claude", "ping", timeout=5)
    assert text == "PONG"
    assert capsys.readouterr().out.strip() == "PONG"


def test_run_agent_resolves_agent_by_id(monkeypatch):
    messages = [{"role": "assistant",
                 "content": [{"response_type": "text", "text": "hi"}]}]
    _wire_runs(monkeypatch, messages)
    assert runner.run_agent("agent-123", "ping", timeout=5) == "hi"


def test_content_text_handles_parts_and_plain_string():
    assert runner._content_text("just text") == "just text"
    assert runner._content_text(
        [{"response_type": "text", "text": "a"},
         {"response_type": "text", "text": "b"}]) == "a\nb"
    assert runner._content_text([]) is None
