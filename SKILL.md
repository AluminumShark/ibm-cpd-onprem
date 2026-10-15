---
name: ibm-cpd-onprem
description: >-
  Use when working with an on-prem IBM Cloud Pak for Data / IBM Software Hub
  cluster ("on-prem", "CPD", "this cluster", "this box") — watsonx Orchestrate,
  watsonx.ai, Watson Machine Learning, Watson Studio: getting a CPD bearer
  token; chatting with a deployed model (gpt-oss, granite, llama); listing,
  importing, removing or invoking Orchestrate agents and tools with the
  `orchestrate` ADK; backing a native agent with Claude, OpenAI, Gemini or
  another external LLM through the AI Gateway; the ibm_watsonx_ai SDK;
  inventorying spaces, projects, deployments and prompt templates; first-time
  setup of the cluster URL and API key. Also use on errors such as
  UnicodeEncodeError cp950, "product version 5.3 is not supported",
  json_validation_error from /text/chat, HTTP 500 from `orchestrate agents
  list`, or a cpdctl locale panic.
---

# Operating an on-prem IBM Cloud Pak for Data cluster

A portable toolkit for driving any on-prem CPD / IBM Software Hub deployment.
Nothing is hard-coded to one cluster: URL, credentials and IDs come from a
per-machine config or `CPD_*` env vars. The endpoints, flags and gotchas were
verified against a real cluster. Three control planes, each a thin HTTPS
client of the cluster:

1. **REST API** + a CPD bearer token — covers everything (auth, chat, inventory).
2. **`orchestrate` ADK CLI** — watsonx Orchestrate (agents, tools, models, knowledge bases).
3. **`ibm_watsonx_ai` Python SDK** — watsonx.ai + Watson Machine Learning.

## Where commands run: `$S`

The shell usually sits in the user's own project, not in this skill, so every
command addresses the skill through `S`, its base directory — Claude Code
prints it as "Base directory for this skill" when the skill loads. Set it with
single quotes (Windows paths keep their backslashes), in the same command that
uses it: shell state does not carry over between Bash calls.

```bash
S='<this skill base directory>'
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1      # see "Two gotchas" below
python "$S/scripts/cpd_config.py" show
```

A bare `scripts/...` path resolves against the user's project and fails; the
references follow the same convention. On macOS and most Linux read `python` /
`pip` as `python3` / `python3 -m pip`; the `.sh` scripts find a working Python
themselves (`CPD_PYTHON` overrides).

## Prerequisites: check the path you need, install on demand

Python 3.8+ and `curl` cover the REST path — `cpd_config.py`, `cpd_token.sh`
and `wx_chat.sh` are standard-library only. The other two paths each need one
package:

| Path | Check first | If the check fails |
|---|---|---|
| watsonx.ai SDK (`wx_connect.py`) | `python -c "import ibm_watsonx_ai"` | `pip install ibm-watsonx-ai` |
| Orchestrate ADK | `uv run --project "$S" --group wxo python "$S/scripts/wxo_adk_check.py"` | no `uv`: `pip install "ibm-watsonx-orchestrate==2.7.2"`, then the check with plain `python` |

Run the check before the first command of a path — `orchestrate: command not
found` or a `ModuleNotFoundError` reads as "the cluster is broken" to a user
who doesn't know a package is missing. When it fails, name what is missing,
give the one-line install, and ask before running it: the user's Python
environment is theirs. The uv route never touches it, but any
`uv run --group wxo` — the check included — first syncs the pinned ADK into
the skill's own `.venv`, a sizeable one-time download; say so before the first
ADK command on a machine. Rather not install anything? The REST path in
[references/rest-api.md](references/rest-api.md) needs only `curl`.

### The ADK: pinned, in the skill's own `.venv`

The ADK must match the cluster, not be the latest: 2.8.0+ breaks every
`agents` command on WXO 5.3.1 (HTTP 500 — gotchas #11) while the rest keeps
working. `pyproject.toml` pins 2.7.2 in a `wxo` dependency group (Python
3.11–3.13); `uv sync --project "$S" --group wxo` installs it into the skill's
own `.venv`, leaving the system Python untouched. Run every ADK command, and
every `wxo_*` script that calls it, as `uv run --project "$S" --group wxo …`
(`wxo_run_agent.py` is plain REST and needs no prefix).
**Never drop `--project "$S"`**: outside this project uv ignores `--group wxo`
with only a warning and runs whatever `orchestrate` is on `PATH` — often a
newer, SaaS-oriented ADK. Never suggest
`pip install --upgrade ibm-watsonx-orchestrate` for this cluster without
re-running the check.

## First run on any machine: the user runs `cpd_init.py`

The setup wizard verifies the credentials, discovers the cluster's space /
deployment / project / WXO IDs, and writes the config file — `$CPD_CONFIG`
when set (a second cluster: run it with that variable set), else
`~/.config/cpd-onprem/config.json` — git-ignored, chmod 600. It is
**interactive**, so Claude cannot run it — on a non-interactive shell it dies
with `EOFError`. When `python "$S/scripts/cpd_config.py" show` comes back
without a `url`, `username` or `api_key`, stop and give the user this command
for **their own terminal**, with the real path filled in:

```bash
python "<skill base directory>/scripts/cpd_init.py"
```

Answering **y** at "Store the API key in the config file?" lets this session
use the key at once. With N, the key must come from `CPD_API_KEY` in the
environment Claude Code was started from — set it persistently (Windows:
`[Environment]::SetEnvironmentVariable('CPD_API_KEY', '<key>', 'User')` in
their own PowerShell) and restart Claude Code; an `export` in another terminal
never reaches this session. The same holds for `CPD_CONFIG`.

**Never ask the user to paste an API key or password into the chat**, and
never type one into a command. Keys reach the scripts only through the config
file or `CPD_API_KEY`. **External-provider keys** (Anthropic, OpenAI, Gemini…
backing a WXO agent) live apart in `~/.config/cpd-onprem/providers.env` (chmod
600; override `$WXO_PROVIDERS_ENV`) as `WXO_<PROVIDER>_<FIELD>` lines or env
vars — see `providers.env.example` — never in `config.json` or the repo.

### How settings resolve
`scripts/cpd_config.py` is the single source of truth: every script takes the
first of **explicit arg → `CPD_*` env var → config file**, over `CPD_URL`,
`CPD_USERNAME`, `CPD_API_KEY`, `CPD_SPACE_ID`, `CPD_PROJECT_ID`,
`CPD_DEPLOYMENT_ID`, `CPD_WXO_INSTANCE_URL`, `CPD_VERIFY_SSL` (default off —
self-signed), `CPD_CA_BUNDLE` (PEM for a private CA) and `CPD_VERSION` (the
product version the SDK sends). The config file is `$CPD_CONFIG` when set — the
only one read, even before it exists — else `config.json` in the skill folder,
else `~/.config/cpd-onprem/config.json`. `show` names the file actually read;
check it before blaming the cluster for a stale value. `token` prints a bearer
token; `get api_key` is refused without `--reveal`, so the key cannot land in
a transcript by accident.

## Two gotchas that bite on EVERY path

1. **Windows console encoding.** A non-English console codepage (e.g. `cp950`
   on zh-TW) crashes with `UnicodeEncodeError` when a tool prints emoji or CJK
   — and the ADK and model names do. Always
   `export PYTHONIOENCODING=utf-8 PYTHONUTF8=1` first (PowerShell:
   `$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"`). The bundled scripts
   set it themselves.
2. **Self-signed TLS.** `curl` needs `-k`, the ADK `--insecure`, the SDK
   `verify=False` (`verify_ssl: false` is the default here). Flip to verify
   once a real CA is in place.

## Choosing a path

| The user wants to… | Use | Reference |
|---|---|---|
| Token / raw inventory / one-off chat | REST + `curl` (or the bundled scripts) | [references/rest-api.md](references/rest-api.md) |
| Build/deploy/remove Orchestrate **agents & tools** | `orchestrate` ADK CLI | [references/orchestrate-adk.md](references/orchestrate-adk.md) |
| Back a native agent with an **external LLM** (Claude/OpenAI/Gemini…) | `wxo_setup_agent.py` + ADK | [orchestrate-adk.md › external provider](references/orchestrate-adk.md#back-a-native-agent-with-an-external-provider-ai-gateway) |
| Inventory/manage **watsonx.ai / WML** | `ibm_watsonx_ai` SDK | [references/watsonx-sdk.md](references/watsonx-sdk.md) |
| Diagnose a weird error | — | [references/gotchas.md](references/gotchas.md) |

For an external-LLM agent the provider and model are the user's choice: ask
when they haven't named a model — the ids in the references are examples, not
defaults.

When the user is vague ("check the on-prem cluster", "what's on the cluster"),
the fastest full picture is: `python "$S/scripts/wx_connect.py"` (SDK
inventory) plus `uv run --project "$S" --group wxo orchestrate agents list`
(WXO), plus a REST `addOn/query` for installed services.

## Quick starts (the 80% cases)

### Chat with a deployed model
```bash
bash "$S/scripts/wx_chat.sh" "Introduce yourself in one sentence."
```
Resolves URL, token and deployment and prints the answer. The deployment is
the configured one, else the first ready one in the space; to pick a model,
pass its deployment id as a second argument (`wx_connect.py` lists them). Calling `/text/chat` yourself: the body may hold only `messages`
(plus `context`, `tools`, `tool_choice`, `tool_choice_option`) — `max_tokens`
and the like return HTTP 400 — and strip `reasoning_content` before showing
users the reply ([rest-api.md](references/rest-api.md)).

### Connect the SDK
```bash
python "$S/scripts/wx_connect.py"
```
Prints a read-only inventory. It falls back to the SDK's highest supported
product version when the cluster is newer (gotchas #4) and sets the default
space before catalog calls (#5).

### Point the ADK at this cluster
```bash
S='<this skill base directory>'
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
uv sync --project "$S" --group wxo                                          # once: pinned ADK into the skill's .venv
uv run --project "$S" --group wxo python "$S/scripts/wxo_adk_check.py"      # installed AND compatible?
uv run --project "$S" --group wxo python "$S/scripts/wxo_env_activate.py"   # env add + activate
uv run --project "$S" --group wxo orchestrate models list
```
`wxo_env_activate.py` reads the WXO URL, username and API key through
`cpd_config.py` — key in `CPD_API_KEY` or stored by the wizard — answers
`env add`'s "update the environment? (Y/n)" on a re-run, and never prints the
key. Don't hand-write `orchestrate env activate … -a "$CPD_API_KEY"`: it covers
only the env-var case, and an empty `-a` drops the ADK into a getpass prompt
that hangs. Without uv, drop the prefix and use a pip-installed, pinned
`orchestrate`. The ADK reference has the full build-import-remove loop.

## Safety rails

- A cluster may host several WXO instances, some in production. Confirm which
  instance before writing; default to a non-production one when the user hasn't
  said. The configured `wxo_instance_url` is the chosen target.
- Creating then removing clearly-named test objects (prefix like `zytest_`) is
  fine, but **only remove objects this session created** — never pre-existing
  agents, tools, prompts or assets. Verify a delete by re-listing.
- Prefer read-only getters (`get_details`, `list`, `*_model_specs`) for
  inventory; reserve create/import/deploy/remove for explicit requests.
- Secrets flow through env vars / a chmod-600 config, never into the repo or
  chat. A CPD key or password pasted into chat, or anywhere shared, is
  compromised: don't use it, and advise rotating it in the CPD profile page.
- **Never read, print, echo, or inline an external-provider API key.** Let
  `wxo_add_provider.py` set it from `providers.env` / `WXO_*` env vars. A
  provider key pasted into chat is compromised — tell the user to rotate it.

## Known limitations

`cpdctl` panics on launch on non-English Windows locales (gotchas #7 — use
WSL); `cpd-cli` has no native Windows build (WSL only); `oc`/`kubectl` need a
cluster-admin kubeconfig; and the ADK `models list` catalog includes models
that are not deployed on watsonx.ai — only deployed ones can serve inference.
