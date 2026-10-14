# watsonx Orchestrate ADK CLI path

CLI: `orchestrate` (pip package `ibm-watsonx-orchestrate`). Verified first-hand
through a full import→verify→remove cycle on a live CPD instance. Command surface
and flags below are from ADK 2.7.2 (the same loop also passed on 1.12.0, 2.3.4
and 2.6.1); check `--help` if your version differs.

## Install & verify the CLI first
With uv (recommended) the ADK lives in this checkout's `.venv`, pinned by the
`wxo` dependency group in `pyproject.toml` (Python 3.11–3.13, the ADK's own
range), so it never collides with packages in the system Python:
```bash
uv sync --group wxo                                  # once
uv run --group wxo python scripts/wxo_adk_check.py   # installed AND compatible?
uv run --group wxo orchestrate agents list           # prefix every ADK command
```
`uv run --group wxo` puts `.venv`'s `orchestrate` first on `PATH`, for the CLI
and for the `wxo_*` scripts that call it. The commands below are written bare —
add the prefix, or activate `.venv`. Pinning a different ADK means editing the
`wxo` group and re-running `uv sync --group wxo`.

These run from the checkout. From any other directory — which is the normal
case when Claude uses this as a skill — add `--project <checkout or skill dir>`
(`uv run --project "$S" --group wxo …`, with script paths under `$S` too).
Without it uv finds no project, ignores `--group wxo` with only a warning, and
runs whatever `orchestrate` is on `PATH`; `wxo_adk_check.py` run the same way
will flag it if that one is too new.

Without uv:
```bash
python scripts/wxo_adk_check.py
pip install "ibm-watsonx-orchestrate==2.7.2"   # only if the check says so
```
`orchestrate: command not found` (PowerShell: `'orchestrate' is not recognized`)
means the package is absent, not that the cluster is down. After installing,
open a new shell so the console script lands on `PATH`. Nothing else in this
toolkit needs the ADK — only the Orchestrate path does.

## The ADK version must match the cluster — never `pip install --upgrade` blindly
The ADK tracks IBM's SaaS, and on-prem servers lag it. IBM publishes the ADK to
use for each Software Hub release in its
[on-prem compatibility matrix](https://developer.watson-orchestrate.ibm.com/environment/onprem_compatibility)
(5.3.0 → 1.14.x, 5.3.1 → 2.3.x, 5.3.1 Patch 2 → 2.7.x, Patch 5 → 2.10.x,
5.4.0 → 2.11.x, …).

The hard edge, verified on WXO 5.3.1: **ADK 2.8.0 and later break every
`agents` command** (`list`, `import`, `export`) with HTTP 500 — see
[gotchas #11](gotchas.md#11-adk-every-agents-command-fails-with-http-500).
Tools, models, connections, knowledge bases and toolkits still work, which makes
the failure look random. Pin `2.7.2` (the last release before workspaces) unless
the matrix names a newer ADK for your release.

`scripts/wxo_adk_check.py` tells the two cases apart without guessing from
version numbers: an ADK older than 2.8.0 passes straight away; a newer one is
probed against the server (`GET …/agents/external-chat?include=global`) and is
reported `incompatible` when the server answers 500. `wxo_setup_agent.py` runs
the same check before it creates anything.

### Installing with pip into a shared Python
None of this applies to the uv route above; it is what the project `.venv`
avoids.
- **LangChain 0.3 conflict.** ADK 2.x requires `langchain-core` 1.x (2.7.2 pins
  `~=1.4.0`). Installing it into a Python that also holds a LangChain 0.3 stack
  (`langchain`, `langchain-community`, `langchain-ibm`,
  `langchain-text-splitters` 0.3.x) leaves `pip check` reporting conflicts, and
  that stack may break. To keep both in one interpreter, either move that stack
  to LangChain 1.x or stay on ADK 1.x (1.12.0 also passes the loop here).
- **Skip the `[agentops]` extra.** On 2.7.2 it pins
  `ibm-watsonx-orchestrate-evaluation-framework==1.3.9`; installing it stopped on
  a dependency that needs Rust/Cargo to compile (seen on Windows, Python 3.13),
  so the whole install fails. Install plain `ibm-watsonx-orchestrate==2.7.2`; only
  `orchestrate evaluations` needs the extra.
- **Cloud and on-prem on one machine.** An IBM Cloud (SaaS) instance wants the
  newest ADK, this cluster wants ≤ 2.7.2. The uv route already separates them:
  the cluster's ADK sits in this checkout's `.venv` and wins on `PATH` inside
  `uv run --group wxo`, so a newer `orchestrate` elsewhere (e.g. from
  `uv tool install ibm-watsonx-orchestrate`) can serve the SaaS instance. With
  pip only, give one of them its own virtualenv. The env list in
  `~/.config/orchestrate` is shared, so `env activate` picks the target either
  way.

## ALWAYS export this first
```bash
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
```
The ADK prints model names containing emoji/CJK; without UTF-8 the command crashes
mid-output with `UnicodeEncodeError` on non-English Windows consoles. The
server-side action may still have happened — re-run a read-only `list` to check.

## Command surface (v2.7.2)
`env`, `agents`, `tools`, `toolkits`, `knowledge-bases`, `connections`,
`voice-configs`, `server`, `chat`, `models`, `channels`, `phone`, `evaluations`,
`settings`, `partners`, `observability`. (`copilot` existed in 1.x and is gone
in 2.x; `skills` and `workspaces` arrive in later 2.x releases and have no
server side on WXO 5.3.1.)

Agent attributes: style ∈ `default | react | planner`; kind ∈
`native | external | assistant`; tool permission ∈
`read_only | write_only | read_write | admin`.

## Connect to the cluster
```bash
WXO_URL=$(python scripts/cpd_config.py get wxo_instance_url)
USER=$(python scripts/cpd_config.py get username)

orchestrate env add -n cpd-onprem -u "$WXO_URL" -t cpd --insecure
orchestrate env activate cpd-onprem -u "$USER" -a "$CPD_API_KEY" --skip-version-check
```
- `-t cpd` selects CPD auth; `--insecure` accepts the self-signed cert.
- `env activate` takes a CPD **password OR api key**, not both.
- `--skip-version-check` avoids a pypi lookup that can hang or mismatch.
- `WXO_URL` looks like `{CPD_URL}/orchestrate/cpd-instance-operands/instances/{INSTANCE_ID}`.
  `cpd_init.py` discovers and stores it; or get the instance id from
  `zen-data/v3/service_instances` (addon_type `orchestrate`).
- CPD support prints an "early access preview" warning — expected.

> Do not `env activate` a *cloud* env non-interactively without its key — it drops
> into an interactive prompt and hangs on non-interactive stdin. Activating
> `local` needs the Developer Edition server running (`localhost:4321`).

## Read-only inventory
```bash
orchestrate models list      # LLM catalog (virtual + watsonx.ai-backed)
orchestrate agents list
orchestrate tools list
orchestrate connections list
orchestrate knowledge-bases list
```

## Build → import → verify → remove (the tested loop)
Tool (`example_ping.py`):
```python
from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission

@tool(permission=ToolPermission.READ_ONLY)
def example_ping(name: str) -> str:
    """Return a short test greeting.

    Args:
        name: who to greet
    """
    return f"ok: hello {name}"
```
Agent (`example_agent.yaml`) — set `llm` to a name from `orchestrate models list`:
```yaml
spec_version: v1
kind: native
name: example_agent
display_name: Example Assistant
description: Example agent.
llm: watsonx/openai/gpt-oss-120b
style: default
instructions: You are an assistant. Call the example_ping tool when needed.
tools:
  - example_ping
```
Commands:
```bash
orchestrate tools import  -k python -f example_ping.py     # -> "Tool '...' imported successfully"
orchestrate agents import -f example_agent.yaml            # -> "Agent '...' imported successfully"
orchestrate agents list | grep -i example                 # verify present
# remove the agent BEFORE the tool it depends on
orchestrate agents remove -n example_agent -k native
orchestrate tools  remove -n example_ping
orchestrate agents list | grep -ci example                 # expect 0
```
- `agents remove` needs `-k <kind>`. Remove dependents (agents) before their tools.

## Clean up the env entry
```bash
orchestrate env remove -n cpd-onprem     # prompts y/N; REFUSES if it's the ACTIVE env
```
It will not remove the active env without an interactive `y`. To script teardown,
switch active away first, or pipe `y`. Removing the env is local-only.

## Back a native agent with an external provider (AI Gateway)

Give a **native** agent an external LLM (Anthropic Claude, OpenAI, Gemini,
Mistral, Groq, Bedrock, Vertex AI, an OpenAI-compatible self-hosted model…)
through WXO's built-in AI Gateway (Portkey-based "virtual models"), with no
provider key ever landing in the chat transcript, a visible command, shell
history, or the repo.

- **Virtual models.** The model is named `virtual-model/<provider>/<model-id>`;
  the ADK adds the `virtual-model/` prefix and infers the provider from the 2nd
  path segment. The provider's secret lives in a **key_value connection** bound
  to the model via `--app-id`; non-secret settings live in the model spec's
  `provider_config`.
- **Native agents only.** Only `native` agents have an `llm:` field. `external`
  and `assistant` agents bring their own backend — this flow does not apply.
- **Tool-calling only.** Only a tool-calling-capable model works as an agent LLM
  with tools. The ADK auto-injects `config.max_tokens: 4096` for `anthropic`.

> **Egress requirement.** The gateway makes the outbound call to the provider
> *from the cluster*. An air-gapped cluster cannot reach `api.anthropic.com` &c.
> Fallbacks: point a provider at an in-network endpoint with
> `--provider-config custom_host=...`, use `ollama` against a self-hosted
> OpenAI-compatible server, or stay on watsonx.ai-hosted models (the ADK
> `watsonx/...` catalog). Verify egress once with a `zytest_` model before
> relying on it.

### Provider → credential fields

| Provider | secret fields (→ `providers.env`) | non-secret config (→ `--provider-config`) |
|---|---|---|
| openai, anthropic, google, mistral-ai, groq, cohere, together-ai, openrouter, x-ai, jina | `api_key` | — |
| ollama | (none) | `custom_host` |
| azure-openai | `api_key` | `custom_host`, or `azure_resource_name` / `azure_deployment_id` / `azure_api_version` |
| bedrock | `aws_access_key_id`, `aws_secret_access_key` | `aws_region` |
| vertex-ai | `vertex_service_account_json` | `vertex_project_id`, `vertex_region` |

Unknown providers default to requiring `api_key`; `orchestrate models import`
also names a provider's required fields in its output. Secrets are supplied via
`WXO_<PROVIDER_UPPER>_<FIELD_UPPER>` env vars or `providers.env` (see
`providers.env.example`) — never on the command line you type.

### One-shot helper (recommended)
```bash
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
# put WXO_<PROVIDER>_API_KEY in providers.env (chmod 600) or the environment first
python scripts/wxo_setup_agent.py --provider anthropic \
    --model claude-3-5-sonnet-20241022 --agent-name zytest_claude \
    --test "Reply with exactly: PONG"
```
It ensures the connection + credentials (`wxo_add_provider.py`, the only code that
touches the plaintext key), imports the model and a native agent, and — with
`--test` — invokes it. Self-hosted example:
```bash
python scripts/wxo_setup_agent.py --provider ollama --model llama3.1 \
    --agent-name zytest_ollama --provider-config custom_host=http://ollama:11434/v1
```

### Equivalent manual commands
```bash
# 1. credentials: a key_value connection (secret rides on argv — see note below)
orchestrate connections add -a wxo_anthropic
orchestrate connections configure -a wxo_anthropic --env draft -k key_value -t team
orchestrate connections set-credentials -a wxo_anthropic --env draft -e "api_key=$WXO_ANTHROPIC_API_KEY"

# 2. model spec -> import (name gets the virtual-model/ prefix; anthropic gets max_tokens=4096)
cat > model.json <<'JSON'
{ "spec_version": "v1", "name": "virtual-model/anthropic/claude-3-5-sonnet-20241022",
  "display_name": "Claude 3.5 Sonnet", "description": "Claude via the AI Gateway",
  "model_type": "chat" }
JSON
orchestrate models import -f model.json --app-id wxo_anthropic

# 3. native agent spec -> import
cat > agent.yaml <<'YAML'
spec_version: v1
kind: native
name: zytest_claude
description: Native agent backed by Claude.
llm: virtual-model/anthropic/claude-3-5-sonnet-20241022
style: default
instructions: You are a helpful assistant. Answer directly and concisely.
YAML
orchestrate agents import -f agent.yaml
```
`set-credentials` (ADK 1.12.0 through 2.18.1) has **no file/stdin option** — the secret is only
accepted on argv (`-e key=value`, `--api-key`, …), so it is briefly visible to a
local `ps` while the child runs. `wxo_add_provider.py` reads the value from
`providers.env`/env, never echoes it, and scrubs it from captured output; prefer
the helper over typing the key into a shell.

### Invoke the agent (runs API, not raw completions)
The gateway's raw OpenAI endpoint
`POST {wxo}/v1/orchestrate/v1/chat/completions` returns **HTTP 500** on this
cluster — use the **runs** path instead:
```bash
python scripts/wxo_run_agent.py --agent zytest_claude --message "Reply with: PONG"
```
Under the hood: resolve `GET {wxo}/v1/orchestrate/agents` (a JSON array, each with
`id`/`name`/`llm`) → `POST {wxo}/v1/orchestrate/runs` with
`{"agent_id","message":{"role":"user","content":"…"}}` → returns
`{thread_id,…}` → poll `GET {wxo}/v1/orchestrate/threads/{thread_id}/messages` and
take the last `role == "assistant"` message's text parts.

### Cleanup (reverse order)
```bash
python scripts/wxo_setup_agent.py --provider anthropic \
    --model claude-3-5-sonnet-20241022 --agent-name zytest_claude --cleanup
# equivalently, by hand — agent depends on the model, remove it first:
orchestrate agents remove -n zytest_claude -k native
orchestrate models remove -n virtual-model/anthropic/claude-3-5-sonnet-20241022
orchestrate connections remove -a wxo_anthropic
orchestrate agents list   # confirm nothing zytest_ remains
```
Name test objects with a clear `zytest_` prefix, and only remove objects this
session created — verify the delete by re-listing.

## Beyond the basics (pointers)
- **Knowledge bases**: `knowledge-bases import` builds RAG; embeddings can use a
  deployed retriever model (e.g. an `slate-*-rtrvr`).
- **Toolkits / MCP**: `toolkits import` integrates MCP servers.
- **Channels**: `channels` publishes an agent to embedded web chat.
- **Evaluations**: `evaluations` runs datasets against an agent.
- **Flows**: `ibm_watsonx_orchestrate.flow_builder` composes deterministic
  multi-tool/agent flows in Python.
