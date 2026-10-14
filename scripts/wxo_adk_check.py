#!/usr/bin/env python3
"""Check that the installed ADK can manage agents on this cluster's Orchestrate.

ADK 2.8.0+ adds `include=global` and `workspace_id` to every agent lookup. A WXO
server without workspace support (verified: 5.3.1 below Patch 5) answers HTTP 500
on /v1/orchestrate/agents/external-chat for those params, so `agents list`,
`agents import` and `agents export` all fail. No CLI flag turns the params off.

The check is a probe, not a version cap, so it stays right on newer clusters:
  ADK < 2.8.0                       -> ok (never sends the params; no network call)
  ADK >= 2.8.0, probe answers 200   -> ok (server knows workspaces)
  ADK >= 2.8.0, probe answers 500   -> incompatible: pin the ADK to <= 2.7.x
  anything else                     -> unknown (warn, don't block)

IBM's on-prem matrix lists the supported ADK per Software Hub release:
  https://developer.watson-orchestrate.ibm.com/environment/onprem_compatibility

CLI:
    python wxo_adk_check.py     # exit 0 ok/unknown, 1 incompatible/missing
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpd_config as C  # noqa: E402

WORKSPACE_ADK = (2, 8, 0)          # first ADK that sends include=global
LAST_PRE_WORKSPACE = "2.7.2"       # newest ADK verified against WXO 5.3.1
MATRIX_URL = ("https://developer.watson-orchestrate.ibm.com/environment/"
              "onprem_compatibility")
PROBE = "/v1/orchestrate/agents/external-chat?include=global"


def parse_adk_version(text: str):
    """'ADK Version: 2.18.1' -> (2, 18, 1); None if absent."""
    m = re.search(r"ADK Version:\s*(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def adk_version(orchestrate="orchestrate"):
    """Installed ADK version as a tuple, or None if the CLI is missing."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        proc = subprocess.run([orchestrate, "--version"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
    except FileNotFoundError:
        return None
    return parse_adk_version((proc.stdout or "") + (proc.stderr or ""))


def check(orchestrate="orchestrate", cfg=None):
    """Return (status, message); status is ok | incompatible | missing | unknown."""
    ver = adk_version(orchestrate)
    if ver is None:
        return "missing", ("the orchestrate CLI is not installed (or prints no ADK "
                           "version). Install it with: pip install "
                           '"ibm-watsonx-orchestrate==%s"' % LAST_PRE_WORKSPACE)
    shown = ".".join(map(str, ver))
    if ver < WORKSPACE_ADK:
        return "ok", "ADK %s predates workspaces; compatible." % shown

    if cfg is None:
        cfg = C.load_file()
    base = (C.get("wxo_instance_url", cfg) or "").rstrip("/")
    if not base:
        return "unknown", ("no wxo_instance_url — cannot verify ADK %s against "
                           "the server (run cpd_init.py)." % shown)
    code, _ = C.http("GET", base + PROBE, token=C.get_token(cfg), cfg=cfg)
    if code == 200:
        return "ok", "ADK %s; server supports workspaces." % shown
    if code == 500:
        return "incompatible", (
            "ADK %s sends include=global/workspace_id on agent lookups, and this "
            "Orchestrate server answers HTTP 500 to them — agents list/import/"
            "export will fail. Pin the ADK to the last release before workspaces:\n"
            '    pip install "ibm-watsonx-orchestrate==%s"\n'
            "or the version IBM lists for your Software Hub release: %s"
            % (shown, LAST_PRE_WORKSPACE, MATRIX_URL))
    return "unknown", ("ADK %s: compatibility probe returned HTTP %s; could not "
                       "verify. See %s" % (shown, code, MATRIX_URL))


def main(argv) -> int:
    status, msg = check()
    tag = {"ok": "ok", "unknown": "warn"}.get(status, "error")
    stream = sys.stdout if status == "ok" else sys.stderr
    stream.write("[%s] %s\n" % (tag, msg))
    return 0 if status in ("ok", "unknown") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
