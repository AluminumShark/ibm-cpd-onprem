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
verified by direct calls against a real cluster, not taken from generic docs.

Three control planes, each a thin client that calls the cluster over HTTPS REST
(the models, agents and data all live server-side):

1. **REST API** + a CPD bearer token — covers everything (auth, chat, inventory).
2. **`orchestrate` ADK CLI** — manages watsonx Orchestrate (agents, tools, models, knowledge bases).
3. **`ibm_watsonx_ai` Python SDK** — manages watsonx.ai + Watson Machine Learning.

## Where commands run: `$S`

The shell usually sits in the user's own project, not in this skill, so every
command here addresses the skill through `S`, its base directory — Claude Code
prints it as "Base directory for this skill" when the skill loads. Set it with
single quotes (Windows paths keep their backslashes), in the same command that
uses it: shell state does not carry over between Bash calls.

```bash
S='<this skill base directory>'
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1      # see the first gotcha below
python "$S/scripts/cpd_config.py" show
```

A bare `scripts/...` path resolves against the user's project and fails. The
references follow the same convention.

## Prerequisites: check the path you need, install on demand

Only Python 3.8+ and `curl` are always required — `cpd_config.py`,
`cpd_token.sh` and `wx_chat.sh` are standard-library only and never need a pip
install. The other two control planes each need one package:

| Path | Check first | If the check fails |
|---|---|---|
| REST (token, chat, inventory) | `python --version` | nothing to install |
| watsonx.ai SDK (`wx_connect.py`) | `python -c "import ibm_watsonx_ai"` | `pip install ibm-watsonx-ai` |
| Orchestrate ADK (`orchestrate ...`) | `uv run --project "$S" --group wxo python "$S/scripts/wxo_adk_check.py"` | `uv sync --project "$S" --group wxo`; without uv, `pip install "ibm-watsonx-orchestrate==2.7.2"` |

Run the check before the first command of a path, not after a failure —
`orchestrate: command not found` and a `ModuleNotFoundError` traceback both read
as "the cluster is broken" to a user who does not know a package is missing.
When a check fails, say plainly what is missing, give the one-line install
command, and ask before running it — installing into the user's Python
environment is their call. If they would rather not install anything, the REST
path in [references/rest-api.md](references/rest-api.md) covers auth, chat and
inventory with nothing but `curl`.

On macOS and most Linux the interpreter is `python3` and `pip` is
`python3 -m pip` — use those wherever this skill writes `python` / `pip`.
`cpd_token.sh` and `wx_chat.sh` pick a working `python3` or `python` on their
own; `CPD_PYTHON` overrides the choice.

### The ADK: pinned, in the skill's own `.venv`

The ADK version must match the cluster, not be the latest: ADK 2.8.0+ breaks
every `agents` command against WXO 5.3.1 (HTTP 500 — gotchas #11) while
everything else keeps working. `wxo_adk_check.py` probes the server and says
which case applies. Never suggest `pip install --upgrade ibm-watsonx-orchestrate`
for an on-prem cluster without running the check afterwards.

`pyproject.toml` pins the ADK in a `wxo` dependency group (Python 3.11–3.13),
and `uv sync --project "$S" --group wxo` installs it into the skill's own
`.venv` — the system Python, and whatever LangChain or SaaS ADK it holds, is
never touched. Run every ADK command, and every `wxo_*` script that calls it,
as `uv run --project "$S" --group wxo …`, which puts the pinned `orchestrate`
first on `PATH`. **Never drop `--project "$S"`**: outside this project uv
ignores `--group wxo` with only a warning and runs whatever `orchestrate` is on
`PATH` — often a newer, SaaS-oriented ADK that fails against WXO 5.3.1.

## First run on any machine: the user runs `cpd_init.py`

Nothing is hard-coded to a specific cluster. The setup wizard verifies the
credentials, discovers the cluster's own space / deployment / project / WXO
IDs, and writes `~/.config/cpd-onprem/config.json` (git-ignored, chmod 600).

The wizard is **interactive** (prompts, a hidden key prompt, pickers), so
Claude cannot run it — on a non-interactive shell it dies with `EOFError`.
When `python "$S/scripts/cpd_config.py" show` finds no config file and no
`CPD_*` values, stop and give the user the command to run in **their own
terminal**, with the real skill path filled in:

```bash
python "<skill base directory>/scripts/cpd_init.py"
```

Tell them that answering **y** at "Store the API key in the config file?" lets
this session use the key straight away. With N, the key must come from
`CPD_API_KEY` in the environment Claude Code was started from — set it
persistently and restart Claude Code; an `export` in another terminal never
reaches this session.

**Never ask the user to paste an API key or password into the chat**, and
never type one into a command. Keys reach the scripts only through the config
file or `CPD_API_KEY`.

**External-provider keys** (for backing a WXO native agent with Anthropic,
OpenAI, Gemini…) live separately in `providers.env` — default
`~/.config/cpd-onprem/providers.env` (chmod 600, git-ignored), override
`$WXO_PROVIDERS_ENV` — as `WXO_<PROVIDER>_<FIELD>` lines, or the same env vars.
See `providers.env.example`; never put a provider key in `config.json` or the
repo. A real env var overrides the file, same as `config.json`.

### How settings resolve (every script obeys this)
`scripts/cpd_config.py` is the single source of truth. For each setting it takes
the first available of: **explicit arg → `CPD_*` environment variable → config
file**. So env vars always override the file (handy for CI or a second cluster):

| Setting | Env var |
|---|---|
| cluster URL | `CPD_URL` |
| username | `CPD_USERNAME` |
| API key | `CPD_API_KEY` |
| default space | `CPD_SPACE_ID` |
| default project | `CPD_PROJECT_ID` |
| default deployment | `CPD_DEPLOYMENT_ID` |
| WXO instance URL | `CPD_WXO_INSTANCE_URL` |
| verify TLS | `CPD_VERIFY_SSL` (default off — self-signed) |
| CA bundle | `CPD_CA_BUNDLE` (PEM for a private CA; used while verifying) |

Which config file? `$CPD_CONFIG` when set — even before that file exists,
nothing else is read, and the wizard creates it there. Otherwise the first of
`config.json` in the skill folder, then `~/.config/cpd-onprem/config.json`.
`show` names the one actually read, so when a value looks stale, check that
line before assuming the cluster is wrong.

Quick checks: `python "$S/scripts/cpd_config.py" show` (resolved settings, key
masked), `python "$S/scripts/cpd_config.py" token` (a bearer token).
`get api_key` is refused without `--reveal`, so it cannot land in a transcript
by accident.

## Two gotchas that bite on EVERY path

1. **Windows console encoding.** On a non-English Windows box the console codepage
   (e.g. `cp950` on zh-TW) crashes with `UnicodeEncodeError` the moment a tool
   prints an emoji or CJK — and the ADK and model names do. **Always** export
   first:
   ```bash
   export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
   ```
   PowerShell: `$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"`. The bundled
   scripts already set this; set it yourself for ad-hoc `orchestrate`/`python`.
2. **Self-signed TLS.** On-prem clusters usually use a self-signed cert: `curl`
   needs `-k`, the ADK needs `--insecure`, the SDK needs `verify=False`
   (`verify_ssl: false` is the default here). Flip to verify once a real CA is in
   place.

## Choosing a path

| The user wants to… | Use | Reference |
|---|---|---|
| Token / raw inventory / one-off chat | REST + `curl` (or the bundled scripts) | [references/rest-api.md](references/rest-api.md) |
| Build/deploy/remove Orchestrate **agents & tools** | `orchestrate` ADK CLI | [references/orchestrate-adk.md](references/orchestrate-adk.md) |
| Back a native agent with an **external LLM** (Claude/OpenAI/Gemini…) | `wxo_setup_agent.py` + ADK | [orchestrate-adk.md › external provider](references/orchestrate-adk.md#back-a-native-agent-with-an-external-provider-ai-gateway) |
| Inventory/manage **watsonx.ai / WML** | `ibm_watsonx_ai` SDK | [references/watsonx-sdk.md](references/watsonx-sdk.md) |
| Diagnose a weird error | — | [references/gotchas.md](references/gotchas.md) |

When the user is vague ("check the on-prem cluster", "what's on the cluster"),
the fastest full picture is: `python "$S/scripts/wx_connect.py"` (SDK
inventory) plus `uv run --project "$S" --group wxo orchestrate agents list`
(WXO), plus a REST `addOn/query` for installed services.

## Quick starts (the 80% cases)

### Chat with a deployed model (one call)
```bash
bash "$S/scripts/wx_chat.sh" "Introduce yourself in one sentence."
```
Resolves URL + token + deployment from config (auto-discovers a ready deployment
if none is set). Under the hood:
`POST {url}/ml/v1/deployments/{id}/text/chat?version=2024-05-01` with body
`{"messages":[...]}` **only** — extra top-level fields like `max_tokens` return
HTTP 400 (`json_validation_error`); the allowed siblings are `context`, `tools`,
`tool_choice`, `tool_choice_option`. Responses carry
`choices[0].message.content` plus a separate `reasoning_content` (chain-of-thought
— strip it for end users).

### Connect the SDK (read or manage watsonx.ai/WML)
Needs `ibm-watsonx-ai`; `wx_connect.py` prints the install command if it is absent.
```bash
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
python "$S/scripts/wx_connect.py"
```
The script handles the **product-version pitfall**: if the backend is newer than
the installed SDK (e.g. 5.3 backend, SDK that tops out at 5.2) the SDK rejects
`version="5.3"`, so it falls back to the SDK's highest supported value (identical
API behaviour). It also sets the default space before any catalog call — those
raise "You must set the space/project id" otherwise.

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
`cpd_config.py`, so it works whether the key is in `CPD_API_KEY` or stored by
the wizard. It answers `env add`'s "update the environment? (Y/n)" on a re-run
and never prints the key. Do not hand-write
`orchestrate env activate … -a "$CPD_API_KEY"`: it covers only the env-var
case, and an empty `-a` drops the ADK into a getpass prompt that hangs.

Without uv, drop the `uv run --project "$S" --group wxo` prefix and use a
pip-installed, pinned `orchestrate` instead. See the ADK reference for the full
agent/tool build-import-remove loop and its sharp edges.

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
  chat. If a key is ever pasted somewhere shared, advise rotating it.
- **Never read, print, echo, or inline an external-provider API key** (Anthropic,
  OpenAI, Gemini, Bedrock…). Supply it only via `providers.env` / `WXO_*` env
  vars and let `scripts/wxo_add_provider.py` set it on the connection. If a
  provider key is pasted into chat, treat it as compromised and tell the user to
  rotate it.

## Known limitations (see gotchas.md for fixes)

- **`cpdctl`** (project export/import, job scheduling) panics on launch on
  non-English Windows regional locales (it maps the locale to a translation file
  it doesn't bundle and ignores `LANG`). Use it under WSL, or temporarily switch
  the Windows region to English.
- **`cpd-cli`** (platform admin) has no native Windows build — WSL only.
- **`oc`/`kubectl`** need a kubeconfig bound to the cluster (cluster-admin).
- The models visible in the ADK `models list` virtual catalog are not all
  deployed on watsonx.ai — only actually-deployed models can serve inference.
