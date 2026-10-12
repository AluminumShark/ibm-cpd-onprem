# watsonx Orchestrate ADK CLI path

CLI: `orchestrate` (pip package `ibm-watsonx-orchestrate`). Verified first-hand
through a full import→verify→remove cycle on a live CPD instance. Command surface
and flags below are from ADK v1.12.0; check `--help` if your version differs.

## Install & verify the CLI first
```bash
orchestrate --version          # "ADK Version: 1.12.0" -> already installed
pip install ibm-watsonx-orchestrate
```
`orchestrate: command not found` (PowerShell: `'orchestrate' is not recognized`)
means the package is absent, not that the cluster is down. After installing,
open a new shell so the console script lands on `PATH`. Nothing else in this
toolkit needs the ADK — only the Orchestrate path does.

## ALWAYS export this first
```bash
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
```
The ADK prints model names containing emoji/CJK; without UTF-8 the command crashes
mid-output with `UnicodeEncodeError` on non-English Windows consoles. The
server-side action may still have happened — re-run a read-only `list` to check.

## Command surface (v1.12.0)
`env`, `agents`, `tools`, `toolkits`, `knowledge-bases`, `connections`,
`voice-configs`, `server`, `chat`, `models`, `channels`, `evaluations`,
`copilot`, `settings`, `partners`.

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

## Beyond the basics (pointers)
- **Knowledge bases**: `knowledge-bases import` builds RAG; embeddings can use a
  deployed retriever model (e.g. an `slate-*-rtrvr`).
- **Toolkits / MCP**: `toolkits import` integrates MCP servers.
- **Channels**: `channels` publishes an agent to embedded web chat.
- **Evaluations**: `evaluations` runs datasets against an agent.
- **Flows**: `ibm_watsonx_orchestrate.flow_builder` composes deterministic
  multi-tool/agent flows in Python.
