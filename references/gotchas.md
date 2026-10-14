# Gotchas & fixes (field-tested)

The non-obvious things that make calls fail on this stack, with the fix for each.

## 1. `UnicodeEncodeError` on a non-English Windows console
**Symptom:** a command dies mid-output with
`UnicodeEncodeError: 'cp950' codec can't encode character '✨'...` (or similar
codepage). Happens with the ADK (model names carry ✨/CJK) and with SDK model
specs. It can also hit third-party tools that print emoji (even skill-packaging
scripts).
**Why:** the default console codepage on non-English Windows (cp950 on zh-TW, cp936
on zh-CN, cp932 on ja-JP) can't encode the characters Python is printing.
**Fix:** force UTF-8 before running —
```bash
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
```
PowerShell: `$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"`. The bundled
scripts set this themselves.

## 2. Self-signed TLS
**Symptom:** certificate-verify errors.
**Fix:** `curl -k`, ADK `--insecure`, SDK `verify=False`. The config default is
`verify_ssl: false`. Set it true (and trust the CA) once the cluster has a real
cert.

## 3. Chat request rejected: `json_validation_error`
**Symptom:** `POST .../text/chat` returns HTTP 400 saying the body "can only
contain 'messages' and optionally 'context', 'tools', 'tool_choice',
'tool_choice_option'".
**Why:** deployment chat endpoints don't accept generation params in the body
(no `max_tokens`, `temperature`, …). Those are set on the deployment.
**Fix:** send only `{"messages":[...]}` (+ the allowed siblings). Also use
`version=2024-05-01` in the query string.

## 4. SDK: "The product version 5.3 is not supported"
**Symptom:** `WMLClientError` when constructing `Credentials(..., version="5.3")`.
**Why:** the installed SDK validates `version` against a built-in list that may be
older than the cluster. The REST APIs are identical across 5.x.
**Fix:** pass the SDK's highest supported version instead of the literal backend
version. `wx_connect.py` auto-detects this via
`CPDVersion.supported_version_list`. (Or upgrade the SDK.)

## 5. SDK: "You must set the space/project id"
**Symptom:** `foundation_models.*` / `software_specifications.*` /
`hardware_specifications.*` raise this.
**Fix:** call `client.set.default_space(SPACE_ID)` (or `default_project`) right
after connecting, before any catalog call.

## 6. ADK `env remove` refuses / hangs
- It **refuses to remove the active env** without an interactive `y`. Switch the
  active env away first, or pipe `y`.
- `env activate` for a **cloud** env with no key drops into an interactive prompt
  and **hangs** on non-interactive stdin. Supply the key, or activate
  interactively.
- `env activate local` needs the Developer Edition server running on
  `localhost:4321`, else connection refused.

## 7. `cpdctl` panics on launch (non-English Windows)
**Symptom:** `panic: open resources/all.zh_Hant.json: file does not exist` (or
your locale's tag) immediately on any `cpdctl` command.
**Why:** `cpdctl` maps the Windows **regional format** (Get-Culture, e.g. zh-TW) to
a translation file it does not bundle, reads it from its embedded resources, and
**ignores `LANG`/`LC_ALL`/`LC_MESSAGES`/`LANGUAGE`**.
**Fixes (pick one):**
- Run `cpdctl` under **WSL** (Linux build; locale honours `LANG`, so `C`/en works).
- Temporarily switch the Windows region to English:
  `Set-Culture en-US` → run `cpdctl` in a **new** shell → `Set-Culture zh-TW` to
  revert. (This is a user regional-settings change; do it knowingly.)
The native-Windows `cpdctl` download is also ~140 MB vs ~37 MB for Linux.

## 8. API key returns 401 at `/authorize`
A watsonx.ai-scoped key is not necessarily a platform key, and a key created by
another user won't authenticate your username. Use the **CPD platform API key**
that matches `CPD_USERNAME` (generate it in the CPD profile page). The password
also works in place of the key for both the ADK and the SDK.

## 9. Can't sign in to the CPD web console
The console login page on an OpenShift-fronted cluster asks which identity
provider to use before it shows a username/password form — picking the wrong one
rejects otherwise-valid credentials.
**Fix:** choose **OpenShift authentication**, then **htpasswd**, then sign in with
the cluster username and password. The platform API key used by `CPD_API_KEY` is
generated from the profile page once you are inside.

## 10. `python: command not found` (macOS, most Linux)
**Symptom:** a command from these docs fails with `command not found: python`
(or `pip`).
**Why:** macOS 12.3+ and most Linux distributions ship only `python3`, with pip
as `pip3` / `python3 -m pip`.
**Fix:** type `python3` wherever the docs say `python`. `cpd_token.sh` and
`wx_chat.sh` already try `python3`, then `python`, and use the first that runs
Python 3.8+ — which also skips a Windows Store `python3` stub that does not.
Set `CPD_PYTHON=/path/to/python` to choose one explicitly.

## 11. ADK: every `agents` command fails with HTTP 500
**Symptom:** `orchestrate agents list` (or `import`, `export`) dies with
`500 Server Error … /v1/orchestrate/agents/external-chat?…&workspace_id=…&include=global`
and `{"detail":"An Unexpected Error Occurred."}`, while `tools`, `models`,
`connections`, `knowledge-bases` and `toolkits` keep working. `-k native` does
not help: listing native agents still resolves their collaborators through the
same endpoint.
**Why:** ADK 2.8.0 added workspaces. From then on every agent lookup carries
`include=global` (hard-coded default, no flag to turn it off) and the active
workspace id. A server without workspace support — verified on WXO 5.3.1 below
Patch 5 — ignores the params on `/agents` but answers 500 on
`/agents/external-chat` and `/assistants/watsonx`. Its `/workspaces` and
`/skills` routes don't exist either (the UI's HTML comes back, so the ADK reports
a JSON decode error).
**Fix:** pin the ADK to the last release before workspaces, or to the version
IBM's [on-prem compatibility matrix](https://developer.watson-orchestrate.ibm.com/environment/onprem_compatibility)
names for your Software Hub release. The `wxo` dependency group in
`pyproject.toml` already pins 2.7.2 into the project's `.venv`:
```bash
uv sync --group wxo
uv run --group wxo python scripts/wxo_adk_check.py   # -> [ok] ADK 2.7.2 predates workspaces
# without uv:
pip install "ibm-watsonx-orchestrate==2.7.2" && python scripts/wxo_adk_check.py
```
An upgrade can leave a cloud-oriented ADK on `PATH` without anyone noticing, so
run the check whenever the Orchestrate path misbehaves after a `pip install`.
If the same machine also drives an IBM Cloud (SaaS) instance that needs a newer
ADK, the uv route keeps the two apart; with pip, give one of them its own
virtualenv.
