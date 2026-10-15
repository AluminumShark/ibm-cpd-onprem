#!/usr/bin/env python3
"""Point the ADK at this cluster's watsonx Orchestrate: `env add` + `env activate`.

Settings come from cpd_config (env CPD_* > config file), so this works whether
the CPD API key sits in CPD_API_KEY or in a config.json the wizard stored it
in. The bare one-liner `orchestrate env activate ... -a "$CPD_API_KEY"` covers
only the first, and an empty -a/-u makes the ADK fall back to getpass prompts
that hang a non-interactive shell — so a missing setting stops here instead.

Safe to re-run: `env add` on an existing name asks "update the environment?
(Y/n)" through input(), which dies with EOFError without a terminal; the
answer is supplied on stdin.

Secret note: `env activate` takes the key only on argv (`-a`); it has no file,
stdin or env-var input. The key is redacted in the echoed command and scrubbed
from captured output, but is briefly visible to a local `ps` while the child
runs — the same trade-off as wxo_add_provider.py.

Run it through the pinned ADK so the right `orchestrate` is on PATH:
    uv run --project "$S" --group wxo python "$S/scripts/wxo_env_activate.py"
    ... wxo_env_activate.py --name cpd-test      # default name: cpd-onprem
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpd_config as C            # noqa: E402
import wxo_adk_check as adk       # noqa: E402  (install hint only)

DEFAULT_NAME = "cpd-onprem"


def env_add_cmd(name, url, verify, ca_bundle, orchestrate="orchestrate"):
    cmd = [orchestrate, "env", "add", "-n", name, "-u", url, "-t", "cpd"]
    if not verify:
        cmd.append("--insecure")              # self-signed: the usual on-prem case
    elif ca_bundle:
        cmd += ["--verify", ca_bundle]        # private CA
    return cmd                                # verify against system trust: no flag


def _run(cmd, secret=None, stdin=None):
    """Run an orchestrate command; mask `secret` in the echo and the output."""
    def scrub(text):
        return text.replace(secret, "***") if secret and text else text
    shown = ["***" if secret and a == secret else a for a in cmd]
    sys.stdout.write("  $ " + " ".join(shown) + "\n")
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if proc.stdout:
        sys.stdout.write(scrub(proc.stdout))
    if proc.stderr:
        sys.stderr.write(scrub(proc.stderr))
    return proc


def activate(name=DEFAULT_NAME, orchestrate="orchestrate", cfg=None) -> int:
    """Add (or update) the CPD env and activate it. 0 on success."""
    if cfg is None:
        cfg = C.load_file()
    url = C.get("wxo_instance_url", cfg)
    user = C.get("username", cfg)
    key = C.get("api_key", cfg)
    missing = [var for var, v in (("CPD_WXO_INSTANCE_URL", url),
                                  ("CPD_USERNAME", user),
                                  ("CPD_API_KEY", key)) if not v]
    if missing:
        sys.stderr.write("[error] missing %s — the user runs cpd_init.py in their "
                         "own terminal, or sets the env var(s).\n" % ", ".join(missing))
        return 2

    add = env_add_cmd(name, url, C.get("verify_ssl", cfg), C.get("ca_bundle", cfg),
                      orchestrate)
    try:
        proc = _run(add, secret=key, stdin="y\n")
        if proc.returncode != 0:
            sys.stderr.write("[error] 'env add' failed for '%s'.\n" % name)
            return proc.returncode
        proc = _run([orchestrate, "env", "activate", name, "-u", user, "-a", key,
                     "--skip-version-check"], secret=key)
    except FileNotFoundError:
        sys.stderr.write("[error] the orchestrate CLI is not on PATH. Install the "
                         "pinned ADK:\n%s\n" % adk.INSTALL)
        return 1
    if proc.returncode != 0:
        sys.stderr.write("[error] 'env activate' failed for '%s'.\n" % name)
        return proc.returncode
    sys.stdout.write("[ok] ADK env '%s' is active -> %s\n" % (name, url))
    return 0


def main(argv) -> int:
    p = argparse.ArgumentParser(description="Add and activate an ADK env for this "
                                            "cluster's watsonx Orchestrate.")
    p.add_argument("--name", default=DEFAULT_NAME,
                   help="ADK env name (default %s)" % DEFAULT_NAME)
    return activate(name=p.parse_args(argv).name)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
