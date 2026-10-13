#!/usr/bin/env python3
"""Invoke a watsonx Orchestrate agent and print its reply, over the runs API.

The gateway's raw OpenAI-compatible endpoint (/v1/orchestrate/v1/chat/completions)
returns HTTP 500 on this cluster — use the runs path, not raw completions:
  1. GET  {wxo}/v1/orchestrate/agents                      -> resolve name -> id
  2. POST {wxo}/v1/orchestrate/runs {agent_id, message}    -> {thread_id, ...}
  3. GET  {wxo}/v1/orchestrate/threads/{thread_id}/messages -> last assistant text

Settings/token come from cpd_config (env CPD_* > config file). Read-mostly: the
only write is creating a run, which is inherent to invoking an agent.

CLI:
    python wxo_run_agent.py --agent zytest_claude --message "Reply with: PONG"
    python wxo_run_agent.py --agent <id> --message "hi" --timeout 90 --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpd_config as C  # noqa: E402


def _base(cfg) -> str:
    base = C.get("wxo_instance_url", cfg)
    if not base:
        sys.exit("no wxo_instance_url — run cpd_init.py or set CPD_WXO_INSTANCE_URL")
    return base.rstrip("/")


def _as_list(resp):
    """Agents/messages come back as a JSON array, or wrapped in a dict."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for key in ("agents", "messages", "data", "items", "resources"):
            if isinstance(resp.get(key), list):
                return resp[key]
    return []


def resolve_agent_id(agent, token, cfg, base) -> str:
    """Return the agent id for a given id-or-name."""
    code, resp = C.http("GET", base + "/v1/orchestrate/agents", token=token, cfg=cfg)
    if code != 200:
        sys.exit("cannot list agents (HTTP %s): %s" % (code, str(resp)[:300]))
    agents = _as_list(resp)
    for a in agents:                                   # exact id first
        if a.get("id") == agent:
            return agent
    for a in agents:                                   # then by name
        if a.get("name") == agent:
            return a.get("id")
    names = ", ".join(sorted(a.get("name", "?") for a in agents)) or "(none)"
    sys.exit("no agent named or id'd '%s'. Available: %s" % (agent, names))


def _content_text(content):
    """Pull the text out of an assistant message's content (a list of
    {response_type:text, text:...} parts), or a plain string."""
    if content is None:
        return None
    if isinstance(content, str):
        return content or None
    parts = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
    return "\n".join(p for p in parts if p) or None


def last_assistant(resp):
    """Return (text, raw_content) for the last assistant message with text, or
    (None, None) if the reply is not ready yet."""
    msgs = _as_list(resp)
    for m in reversed(msgs):
        if m.get("role") == "assistant":
            content = m.get("content")
            text = _content_text(content)
            if text:
                return text, content
            return None, None            # assistant turn exists but still empty
    return None, None


def run_agent(agent, message, timeout=60, as_json=False, cfg=None) -> str:
    """Create a run, poll for the assistant reply, print and return its text."""
    if cfg is None:
        cfg = C.load_file()
    token = C.get_token(cfg)
    base = _base(cfg)

    agent_id = resolve_agent_id(agent, token, cfg, base)
    code, resp = C.http("POST", base + "/v1/orchestrate/runs", token=token,
                        body={"agent_id": agent_id,
                              "message": {"role": "user", "content": message}},
                        cfg=cfg)
    if code not in (200, 201, 202) or not isinstance(resp, dict):
        sys.exit("run create failed (HTTP %s): %s" % (code, str(resp)[:300]))
    thread_id = resp.get("thread_id")
    if not thread_id:
        sys.exit("run response had no thread_id: %s" % (str(resp)[:300]))

    deadline = time.time() + timeout
    while True:
        code, msgs = C.http("GET",
                            base + "/v1/orchestrate/threads/%s/messages" % thread_id,
                            token=token, cfg=cfg)
        if code == 200:
            text, content = last_assistant(msgs)
            if text is not None:
                sys.stdout.write((json.dumps(content, ensure_ascii=False)
                                  if as_json else text) + "\n")
                return text
        if time.time() >= deadline:
            sys.exit("timed out after %ss waiting for a reply on thread %s"
                     % (timeout, thread_id))
        time.sleep(2)


def main(argv) -> int:
    p = argparse.ArgumentParser(description="Invoke a watsonx Orchestrate agent "
                                            "and print its reply.")
    p.add_argument("--agent", required=True, help="agent name or id")
    p.add_argument("--message", required=True, help="the user message to send")
    p.add_argument("--timeout", type=int, default=60, help="seconds to wait (default 60)")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="print the raw assistant content as JSON")
    args = p.parse_args(argv)
    run_agent(args.agent, args.message, timeout=args.timeout, as_json=args.as_json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
