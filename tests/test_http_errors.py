"""A cluster that cannot be reached must produce a diagnosis, not a traceback."""
import socket
import urllib.error

import pytest

import cpd_config as C


class _Resp:
    """Stand-in for the object urlopen returns."""
    def __init__(self, status=200, body='{"ok": true}'):
        self.status = status
        self._body = body

    def read(self):
        return self._body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, result):
    def fake(req, context=None, timeout=None):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(C.urllib.request, "urlopen", fake)


def test_dns_failure_exits_with_a_readable_message(config_file, monkeypatch):
    config_file(url="https://no-such-host.invalid")
    _patch_urlopen(monkeypatch, urllib.error.URLError("[Errno 11001] getaddrinfo failed"))
    with pytest.raises(SystemExit) as e:
        C.http("GET", "/v2/spaces")
    msg = str(e.value)
    assert "no-such-host.invalid" in msg
    assert "getaddrinfo" in msg or "cannot reach" in msg.lower()


def test_timeout_exits_with_a_readable_message(config_file, monkeypatch):
    config_file(url="https://slow.example")
    _patch_urlopen(monkeypatch, socket.timeout("timed out"))
    with pytest.raises(SystemExit) as e:
        C.http("GET", "/v2/spaces")
    assert "timed out" in str(e.value).lower()


def test_http_error_keeps_the_real_status_code(config_file, monkeypatch):
    config_file(url="https://x")
    err = urllib.error.HTTPError("https://x/v2/spaces", 401, "Unauthorized", {}, None)
    err.read = lambda: b'{"message": "bad key"}'
    _patch_urlopen(monkeypatch, err)
    code, body = C.http("GET", "/v2/spaces")
    assert code == 401
    assert body == {"message": "bad key"}


def test_success_reports_the_real_status_not_a_hard_coded_200(config_file, monkeypatch):
    config_file(url="https://x")
    _patch_urlopen(monkeypatch, _Resp(status=201, body='{"created": true}'))
    code, body = C.http("POST", "/v2/spaces", body={})
    assert code == 201
    assert body == {"created": True}
