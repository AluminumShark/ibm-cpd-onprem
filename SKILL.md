---
name: ibm-cpd-onprem
description: >-
  Operate ANY on-prem IBM Cloud Pak for Data / IBM Software Hub cluster (watsonx
  Orchestrate, watsonx.ai, Watson Machine Learning, Watson Studio) from the
  command line. Use WHENEVER the user wants to: get a CPD bearer token; chat with
  a deployed foundation model (gpt-oss, granite, llama…); list/import/remove
  watsonx Orchestrate agents or tools via the ADK CLI; query or register models;
  connect with the ibm_watsonx_ai Python SDK; or inventory spaces, projects,
  deployments, prompt templates and assets. Trigger even when the user only says
  "on-prem / CPD / this cluster / this box". Cluster URL, credentials and IDs
  are NOT hard-coded — they come from a per-machine config (cpd_init.py) or CPD_*
  env vars, so it works against any cluster. Carries verified endpoints, exact
  flags, and the gotchas (cp950 console crash, SDK version rejection, chat version
  stamp, self-signed TLS, cpdctl locale panic) that make calls work first try.
  Default language: English.
---

# Operating an on-prem IBM Cloud Pak for Data cluster

A portable toolkit for driving any on-prem CPD / IBM Software Hub deployment.
Everything here was verified by direct calls against a real cluster — the
endpoints, flags and gotchas are field-tested, not generic docs.

Three control planes, each a thin client that calls the cluster over HTTPS REST
(the models, agents and data all live server-side):

1. **REST API** + a CPD bearer token — covers everything (auth, chat, inventory).
2. **`orchestrate` ADK CLI** — manages watsonx Orchestrate (agents, tools, models, knowledge bases).
3. **`ibm_watsonx_ai` Python SDK** — manages watsonx.ai + Watson Machine Learning.

## Prerequisites: check the path you need, install on demand

Only Python 3.8+ and `curl` are always required — `cpd_config.py`,
`cpd_token.sh` and `wx_chat.sh` are standard-library only and never need a pip
install. The other two control planes each need one package:

| Path | Check first | If the check fails |
|---|---|---|
| REST (token, chat, inventory) | `python --version` | nothing to install |
| watsonx.ai SDK (`wx_connect.py`) | `python -c "import ibm_watsonx_ai"` | `pip install ibm-watsonx-ai` |
| Orchestrate ADK (`orchestrate ...`) | `orchestrate --version` | `pip install ibm-watsonx-orchestrate` |

On macOS and most Linux the interpreter is `python3` and `pip` is
`python3 -m pip` — use those wherever this skill writes `python` / `pip`.
`cpd_token.sh` and `wx_chat.sh` pick a working `python3` or `python` on their
own; `CPD_PYTHON` overrides the choice.

Run the check before the first command of a path, not after a failure —
`orchestrate: command not found` and a `ModuleNotFoundError` traceback both read
as "the cluster is broken" to a user who does not know a package is missing.

When a check fails, say plainly what is missing, give the one-line install
command, and ask before running it — installing into the user's Python
environment is their call. If they would rather not install anything, the REST
path in [references/rest-api.md](references/rest-api.md) covers auth, chat and
inventory with nothing but `curl`.

## First run on any machine: `cpd_init.py`

Nothing is hard-coded to a specific cluster. Before the first operation, make
sure the user has run the setup wizard — it verifies the credentials and
discovers the cluster's own space / deployment / project IDs so no one has to
know them by hand:

```bash
python scripts/cpd_init.py
```

It writes `~/.config/cpd-onprem/config.json` (git-ignored, chmod 600). If that
file is absent and no `CPD_*` env vars are set, stop and ask the user to run it
(or to provide URL + username + API key for this session).

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

Which config file? The first of `$CPD_CONFIG`, `./config.json` in the checkout,
then `~/.config/cpd-onprem/config.json`. `show` names the one actually read, so
when a value looks stale, check that line before assuming the cluster is wrong.

Quick checks: `python scripts/cpd_config.py show` (resolved settings, key masked),
`python scripts/cpd_config.py token` (a bearer token). `get api_key` is refused without `--reveal`, so it cannot land in a transcript by accident.

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
| Inventory/manage **watsonx.ai / WML** | `ibm_watsonx_ai` SDK | [references/watsonx-sdk.md](references/watsonx-sdk.md) |
| Diagnose a weird error | — | [references/gotchas.md](references/gotchas.md) |

When the user is vague ("check the on-prem cluster", "what's on the cluster"),
the fastest full picture is: `python scripts/wx_connect.py` (SDK inventory) plus
`orchestrate agents list` (WXO), plus a REST `addOn/query` for installed services.

## Quick starts (the 80% cases)

### Chat with a deployed model (one call)
```bash
bash scripts/wx_chat.sh "Introduce yourself in one sentence."
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
python scripts/wx_connect.py
```
The script handles the **product-version pitfall**: if the backend is newer than
the installed SDK (e.g. 5.3 backend, SDK that tops out at 5.2) the SDK rejects
`version="5.3"`, so it falls back to the SDK's highest supported value (identical
API behaviour). It also sets the default space before any catalog call — those
raise "You must set the space/project id" otherwise.

### Point the ADK at this cluster
```bash
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
orchestrate --version || pip install ibm-watsonx-orchestrate   # check first
orchestrate env add -n cpd-onprem -u "$(python scripts/cpd_config.py get wxo_instance_url)" -t cpd --insecure
orchestrate env activate cpd-onprem -u "$(python scripts/cpd_config.py get username)" -a "$CPD_API_KEY" --skip-version-check
orchestrate models list
```
See the ADK reference for the full agent/tool build-import-remove loop and its
sharp edges.

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

## Known limitations (see gotchas.md for fixes)

- **`cpdctl`** (project export/import, job scheduling) panics on launch on
  non-English Windows regional locales (it maps the locale to a translation file
  it doesn't bundle and ignores `LANG`). Use it under WSL, or temporarily switch
  the Windows region to English.
- **`cpd-cli`** (platform admin) has no native Windows build — WSL only.
- **`oc`/`kubectl`** need a kubeconfig bound to the cluster (cluster-admin).
- The models visible in the ADK `models list` virtual catalog are not all
  deployed on watsonx.ai — only actually-deployed models can serve inference.
