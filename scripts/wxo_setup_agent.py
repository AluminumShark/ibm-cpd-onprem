#!/usr/bin/env python3
"""One-shot: back a native watsonx Orchestrate agent with an external provider.

Composes the two single-purpose helpers and the ADK CLI:
  1. wxo_add_provider.add_provider(...)  -> ensure the key_value connection + creds
                                            (the only place a secret is handled)
  2. orchestrate models import           -> a virtual-model/<provider>/<model> spec
  3. orchestrate agents import           -> a native agent with llm: that model
  4. (optional) wxo_run_agent.run_agent  -> send --test and print the reply

No secret ever passes through a spec file or this script's argv: credentials are
read from env/providers.env inside wxo_add_provider and handed straight to the
ADK. Non-secret config (custom_host, aws_region, vertex_*) goes in the model
spec's provider_config via --provider-config KEY=VALUE.

CLI:
    python wxo_setup_agent.py --provider google --model gemini-2.5-flash \\
        --agent-name zytest_gemini --test "Reply with exactly: PONG"
    python wxo_setup_agent.py --provider anthropic --model claude-3-5-sonnet-20241022 \\
        --agent-name zytest_claude
    python wxo_setup_agent.py --provider ollama --model llama3.1 \\
        --agent-name zytest_ollama --provider-config custom_host=http://ollama:11434/v1
    python wxo_setup_agent.py --provider google --model gemini-2.5-flash \\
        --agent-name zytest_gemini --cleanup
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wxo_adk_check as adk       # noqa: E402
import wxo_add_provider as prov   # noqa: E402  (secret handling lives here)
import wxo_run_agent as runner    # noqa: E402

DEFAULT_INSTRUCTIONS = ("You are a helpful assistant. Answer the user directly "
                        "and concisely.")


def _run(cmd, orchestrate="orchestrate"):
    """Run an orchestrate command (no secrets flow through here)."""
    full = [orchestrate] + cmd
    sys.stdout.write("  $ " + " ".join(full) + "\n")
    return subprocess.run(full)


def model_name(provider: str, model: str) -> str:
    """Stored name. ADK adds the virtual-model/ prefix; we keep it explicit so
    the same string works for `models remove -n`."""
    return "virtual-model/%s/%s" % (provider, model)


def parse_provider_config(pairs):
    """--provider-config KEY=VALUE ... -> dict (non-secret fields only)."""
    cfg = {}
    for item in pairs or []:
        if "=" not in item:
            sys.exit("--provider-config expects KEY=VALUE, got %r" % item)
        key, value = item.split("=", 1)
        cfg[key.strip()] = value.strip()
    return cfg


def build_model_spec(provider, model, display_name, model_type, provider_config):
    spec = {
        "spec_version": "v1",
        "name": model_name(provider, model),
        "display_name": display_name or model_name(provider, model),
        "description": "External %s model %s via the AI Gateway." % (provider, model),
        "model_type": model_type,
    }
    if provider_config:                 # non-secret config only
        spec["provider_config"] = provider_config
    return spec


def build_agent_spec(agent_name, display_name, provider, model, instructions, style):
    return {
        "spec_version": "v1",
        "kind": "native",
        "name": agent_name,
        "display_name": display_name or agent_name,
        "description": "Native agent backed by %s/%s." % (provider, model),
        "llm": model_name(provider, model),
        "style": style,
        "instructions": instructions or DEFAULT_INSTRUCTIONS,
    }


def _write_spec(tmpdir, name, spec, suffix):
    path = Path(tmpdir) / (name + suffix)
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def do_setup(args) -> int:
    connection = args.connection or prov.default_connection(args.provider)
    provider_config = parse_provider_config(args.provider_config)

    # 0. refuse an ADK this server can't serve before creating anything, or a
    #    failed `agents import` would leave the connection + model behind.
    status, msg = adk.check()
    if status in ("incompatible", "missing"):
        sys.stderr.write("[error] %s\n" % msg)
        return 1
    if status == "unknown":
        sys.stderr.write("[warn] %s\n" % msg)

    # 1. connection + credentials (reads env/providers.env; no secret here)
    rc = prov.add_provider(args.provider, connection=connection,
                           env=args.env, scope=args.scope)
    if rc != 0:
        return rc

    tmpdir = tempfile.mkdtemp(prefix="wxo_setup_")
    try:
        # 2. model spec -> import (bound to the key_value connection)
        mspec = build_model_spec(args.provider, args.model, args.display_name,
                                 args.model_type, provider_config)
        mfile = _write_spec(tmpdir, "model", mspec, ".json")
        if _run(["models", "import", "-f", mfile, "--app-id", connection]).returncode != 0:
            sys.stderr.write("[error] 'models import' failed.\n")
            return 1

        # 3. native agent spec -> import
        aspec = build_agent_spec(args.agent_name, args.display_name, args.provider,
                                 args.model, args.instructions, args.style)
        afile = _write_spec(tmpdir, "agent", aspec, ".json")
        if _run(["agents", "import", "-f", afile]).returncode != 0:
            sys.stderr.write("[error] 'agents import' failed.\n")
            return 1
    finally:
        _cleanup_tmp(tmpdir)

    sys.stdout.write("[ok] agent '%s' is backed by %s\n"
                     % (args.agent_name, model_name(args.provider, args.model)))

    # 4. optional smoke test over the runs API
    if args.test:
        sys.stdout.write("[test] sending prompt to '%s'...\n" % args.agent_name)
        runner.run_agent(args.agent_name, args.test, timeout=args.timeout)
    return 0


def do_cleanup(args) -> int:
    """Remove agent -> model -> connection (reverse of creation) and re-list."""
    connection = args.connection or prov.default_connection(args.provider)
    name = model_name(args.provider, args.model)
    rc = 0
    # agent depends on the model; remove it first.
    if _run(["agents", "remove", "-n", args.agent_name, "-k", "native"]).returncode != 0:
        sys.stderr.write("[warn] could not remove agent '%s'.\n" % args.agent_name)
        rc = 1
    if _run(["models", "remove", "-n", name]).returncode != 0:
        sys.stderr.write("[warn] could not remove model '%s'.\n" % name)
        rc = 1
    if _run(["connections", "remove", "-a", connection]).returncode != 0:
        sys.stderr.write("[warn] could not remove connection '%s'.\n" % connection)
        rc = 1
    sys.stdout.write("[verify] re-listing to confirm teardown:\n")
    _run(["agents", "list"])
    _run(["models", "list"])
    _run(["connections", "list"])
    return rc


def _cleanup_tmp(tmpdir):
    try:
        for f in Path(tmpdir).glob("*"):
            f.unlink()
        Path(tmpdir).rmdir()
    except OSError:
        pass


def main(argv) -> int:
    p = argparse.ArgumentParser(description="Back a native watsonx Orchestrate "
                                            "agent with an external provider.")
    p.add_argument("--provider", required=True,
                   help="provider id, e.g. anthropic, openai, google, bedrock, ollama")
    p.add_argument("--model", required=True,
                   help="provider model id, e.g. claude-3-5-sonnet-20241022")
    p.add_argument("--agent-name", required=True, help="name for the native agent")
    p.add_argument("--instructions", default=None, help="agent instructions")
    p.add_argument("--connection", default=None, help="connection id; default wxo_<provider>")
    p.add_argument("--display-name", default=None)
    p.add_argument("--model-type", default="chat",
                   choices=["chat", "chat_vision", "completion", "embedding"])
    p.add_argument("--provider-config", action="append", metavar="KEY=VALUE",
                   help="non-secret model config, repeatable (e.g. custom_host=...)")
    p.add_argument("--style", default="default", choices=["default", "react", "planner"])
    p.add_argument("--env", default="draft", choices=["draft", "live"])
    p.add_argument("--scope", default="team", choices=["team", "member"])
    p.add_argument("--test", default=None, metavar="PROMPT",
                   help="send this prompt to the agent and print the reply")
    p.add_argument("--timeout", type=int, default=60, help="--test wait seconds")
    p.add_argument("--cleanup", action="store_true",
                   help="remove agent -> model -> connection, then re-list")
    args = p.parse_args(argv)
    return do_cleanup(args) if args.cleanup else do_setup(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
