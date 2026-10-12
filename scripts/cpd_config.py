#!/usr/bin/env python
"""Resolve connection settings for an on-prem IBM Cloud Pak for Data cluster.

Single source of truth for every script in this skill. Pure standard library —
no third-party dependency — so it runs anywhere Python 3.8+ is installed.

Resolution order for every setting (first hit wins):
    1. explicit CLI arg (callers pass it)      — highest
    2. environment variable  (CPD_*)
    3. config file — first of these that exists:
         a. $CPD_CONFIG                     (explicit path)
         b. ./config.json                   (beside config.example.json)
         c. ~/.config/cpd-onprem/config.json  (written by cpd_init.py)
    4. built-in default (only for verify_ssl)  — lowest

Secrets are never committed. Every config.json is git-ignored wherever it sits;
storing the api_key in one is opt-in (default: use CPD_API_KEY). A checkout-local
config.json keeps a clone self-contained, at the cost of putting credentials
inside a work tree — `show` always names the file actually in use.

CLI:
    python cpd_config.py show                 # resolved settings (api_key masked)
    python cpd_config.py get <key>            # print one resolved value
    python cpd_config.py token                # print a bearer token (~12h)
    python cpd_config.py path                 # print the config file path
    python cpd_config.py resolve-deployment   # print a usable chat deployment id
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import urllib.request
import urllib.error
from pathlib import Path

CONFIG_NAME = "config.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_CONFIG = REPO_ROOT / CONFIG_NAME                       # beside config.example.json
USER_CONFIG = Path.home() / ".config" / "cpd-onprem" / CONFIG_NAME
CONFIG_PATH = USER_CONFIG                                   # default write target

# setting name -> environment variable
ENV = {
    "url": "CPD_URL",
    "username": "CPD_USERNAME",
    "api_key": "CPD_API_KEY",
    "space_id": "CPD_SPACE_ID",
    "project_id": "CPD_PROJECT_ID",
    "deployment_id": "CPD_DEPLOYMENT_ID",
    "wxo_instance_url": "CPD_WXO_INSTANCE_URL",
    "ca_bundle": "CPD_CA_BUNDLE",
}

_warned = set()


def config_candidates():
    """Config files in precedence order; the first one that exists wins."""
    out = []
    override = os.environ.get("CPD_CONFIG")
    if override:
        out.append(Path(override).expanduser())
    out.append(REPO_CONFIG)
    out.append(USER_CONFIG)
    return out


def active_config():
    """The config file actually in effect, or None when running on env vars."""
    for p in config_candidates():
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def _gitignore_shields_config() -> bool:
    """Stdlib check that .gitignore still covers a checkout-local config.json."""
    try:
        lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return any(ln.strip().lstrip("/") == CONFIG_NAME for ln in lines)


def _warn_once(key: str, msg: str) -> None:
    if key not in _warned:
        _warned.add(key)
        sys.stderr.write(msg)


def load_file(path=None) -> dict:
    if path is None:
        path = active_config()
        if path is None:
            return {}
        if path == REPO_CONFIG and not _gitignore_shields_config():
            _warn_once("unshielded", (
                "[warn] %s holds credentials but .gitignore no longer excludes "
                "%s — restore that rule before committing.\n" % (path, CONFIG_NAME)))
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:  # malformed file shouldn't be fatal for env-only use
        sys.stderr.write("[warn] ignoring unreadable config %s: %s\n" % (path, e))
        return {}


def get(key: str, cfg: dict | None = None, default=None):
    """Resolve one setting: env var > config file > default."""
    if cfg is None:
        cfg = load_file()
    if key == "verify_ssl":
        # Checked ahead of the file on purpose: cpd_init.py always writes this
        # key, so consulting the file first made CPD_VERIFY_SSL permanently dead
        # for anyone who had run the wizard.
        ev = os.environ.get("CPD_VERIFY_SSL")
        if ev is not None:
            return ev not in ("0", "false", "False", "")
        return bool(cfg.get("verify_ssl", False))
    env_name = ENV.get(key)
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    if key in cfg and cfg[key] not in (None, ""):
        return cfg[key]
    return default


def _ctx(verify, cfg: dict | None = None) -> ssl.SSLContext:
    """TLS context. Verification stays off by default because on-prem CPD is
    almost always self-signed, but say so out loud, and honour a CA bundle when
    one is configured so a properly-certified cluster can be verified."""
    if not verify:
        _warn_once("tls", "[warn] TLS verification is OFF (self-signed default). "
                          "Set CPD_VERIFY_SSL=1, with CPD_CA_BUNDLE if the "
                          "cluster uses a private CA.\n")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    bundle = get("ca_bundle", cfg)
    if not bundle:
        return ssl.create_default_context()
    if not os.path.isfile(bundle):
        sys.exit("CPD_CA_BUNDLE points at %s, which is not a file." % bundle)
    try:
        return ssl.create_default_context(cafile=bundle)
    except ssl.SSLError as e:
        sys.exit("cannot load the CA bundle %s: %s" % (bundle, e))


def http(method: str, path_or_url: str, token: str | None = None, body=None,
         cfg: dict | None = None):
    """Minimal JSON HTTP helper against the cluster. path_or_url may be an
    absolute URL or a path (joined onto the configured base url)."""
    if cfg is None:
        cfg = load_file()
    if path_or_url.startswith("http"):
        url = path_or_url
    else:
        base = get("url", cfg)
        if not base:
            sys.exit("no cluster URL — run cpd_init.py or set CPD_URL")
        url = base.rstrip("/") + path_or_url
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    verify = get("verify_ssl", cfg)
    try:
        with urllib.request.urlopen(req, context=_ctx(verify, cfg), timeout=180) as r:
            raw = r.read().decode("utf-8")
            status = getattr(r, "status", None) or r.getcode()
    except urllib.error.HTTPError as e:  # must precede URLError, it subclasses it
        raw = e.read().decode("utf-8", "ignore")
        return e.code, _maybe_json(raw)
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        sys.exit("cannot reach %s: %s\n"
                 "  check the cluster URL, your network or VPN, and whether the "
                 "cluster is up." % (url, getattr(e, "reason", e) or e))
    return status, _maybe_json(raw)


def _maybe_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        return s


def get_token(cfg: dict | None = None) -> str:
    """Exchange username + api_key for a bearer token (valid ~12h)."""
    if cfg is None:
        cfg = load_file()
    url = get("url", cfg)
    user = get("username", cfg)
    key = get("api_key", cfg)
    missing = [n for n, v in (("CPD_URL", url), ("CPD_USERNAME", user),
                              ("CPD_API_KEY", key)) if not v]
    if missing:
        sys.exit("missing " + ", ".join(missing) + " — run cpd_init.py or set the env vars")
    code, resp = http("POST", "/icp4d-api/v1/authorize",
                      body={"username": user, "api_key": key}, cfg=cfg)
    if code != 200 or not isinstance(resp, dict) or "token" not in resp:
        sys.exit(f"authorize failed (HTTP {code}): {str(resp)[:300]}")
    return resp["token"]


def resolve_deployment(cfg: dict | None = None, token: str | None = None) -> str:
    """Return the configured deployment id, or discover a ready one in the space."""
    if cfg is None:
        cfg = load_file()
    dep = get("deployment_id", cfg)
    if dep:
        return dep
    space = get("space_id", cfg)
    if not space:
        sys.exit("no deployment_id and no space_id to discover from — run cpd_init.py")
    if token is None:
        token = get_token(cfg)
    code, resp = http("GET",
                      f"/ml/v4/deployments?space_id={space}&version=2024-05-01",
                      token=token, cfg=cfg)
    res = resp.get("resources", []) if isinstance(resp, dict) else []
    for r in res:
        if r.get("entity", {}).get("status", {}).get("state") == "ready":
            did = r["metadata"]["id"]
            sys.stderr.write(f"[info] no deployment_id set; using discovered '{did}'\n")
            return did
    sys.exit("no ready deployment found in the space — run cpd_init.py")


def _mask(v):
    if not v:
        return ""
    return v[:4] + "…" + v[-2:] if len(v) > 8 else "***"


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    cfg = load_file()
    if cmd == "path":
        print(active_config() or CONFIG_PATH)
    elif cmd == "show":
        out = {k: (get(k, cfg) or "") for k in ENV}   # unset reads as "", not null
        out["api_key"] = _mask(out.get("api_key"))
        out["verify_ssl"] = get("verify_ssl", cfg)
        active = active_config()
        out["_config_file"] = str(active) if active else "(none — env vars only)"
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif cmd == "get":
        if len(argv) < 2:
            sys.exit("usage: cpd_config.py get <key> [--reveal]")
        key = argv[1]
        if key == "api_key" and "--reveal" not in argv[2:]:
            sys.stderr.write(
                "refusing to print the API key: `get` is meant for $(...) in "
                "shell scripts, where the value lands in history, logs and agent "
                "transcripts.\n"
                "  pass --reveal if you really mean it; scripts should read "
                "$CPD_API_KEY or call get_token() instead.\n")
            return 2
        v = get(key, cfg)
        print(v if v is not None else "")
    elif cmd == "token":
        print(get_token(cfg))
    elif cmd == "resolve-deployment":
        print(resolve_deployment(cfg))
    else:
        sys.exit(f"unknown command: {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
