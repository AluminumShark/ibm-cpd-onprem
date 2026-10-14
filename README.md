# ibm-cpd-onprem

[![tests](https://github.com/AluminumShark/ibm-cpd-onprem/actions/workflows/tests.yml/badge.svg)](https://github.com/AluminumShark/ibm-cpd-onprem/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](#verified-against)
[![Cloud Pak for Data](https://img.shields.io/badge/Cloud%20Pak%20for%20Data-5.3-052FAD)](#verified-against)
[![license](https://img.shields.io/badge/license-Apache--2.0-D22128)](LICENSE)

A portable command-line toolkit **and** a [Claude Code](https://docs.claude.com/en/docs/claude-code/skills)
skill for operating an **on-prem IBM Cloud Pak for Data / IBM Software Hub**
cluster — watsonx Orchestrate, watsonx.ai, Watson Machine Learning and Watson
Studio — without memorising endpoints, flags, or resource IDs.

Nothing is hard-coded to a specific cluster. A one-time wizard discovers your
cluster's own IDs and stores them per-machine, so the same tool works against any
CPD deployment.

> Independent community tool. Not affiliated with or endorsed by IBM. Product
> names are trademarks of IBM, used for identification only. See [NOTICE](NOTICE).

## What it does

- **Auth** — exchange a username + API key for a bearer token (`cpd_token.sh`).
- **Chat** — one-line inference against a deployed foundation model (`wx_chat.sh`),
  with the correct `version` stamp and request shape.
- **Inventory** — read-only listing of deployments, models, spaces, projects via
  the `ibm_watsonx_ai` SDK (`wx_connect.py`) or raw REST.
- **Orchestrate** — build / import / list / remove agents and tools with the
  `orchestrate` ADK CLI (see [references/orchestrate-adk.md](references/orchestrate-adk.md)).
- **External-provider agents** — back a native watsonx Orchestrate agent with an
  external LLM (Anthropic Claude, OpenAI, Google Gemini, Mistral, Groq, Azure,
  Bedrock, Vertex, Ollama…) through the AI Gateway, one command, with the API key
  kept out of the transcript, your shell history and git (`wxo_setup_agent.py`).
- **Encodes the gotchas** that otherwise cost an afternoon — console encoding,
  self-signed TLS, SDK version rejection, chat body validation, `cpdctl` locale
  panic (see [references/gotchas.md](references/gotchas.md)).

## Requirements

- Python 3.8+ (the auth/chat/config scripts are **standard-library only**). On
  macOS and most Linux distributions the command is `python3`, and `pip` is
  `python3 -m pip` — read the examples below that way. The `.sh` scripts find a
  working `python3` or `python` on their own; set `CPD_PYTHON` to pick one.
- `curl` (for `wx_chat.sh`) and bash — Git Bash or WSL on Windows; macOS's stock
  bash 3.2 is enough — or use the PowerShell snippets in the references.
- Optional, one package per extra path — neither is needed for auth or chat:
  - `pip install ibm-watsonx-ai` for `wx_connect.py` (SDK inventory).
  - `pip install "ibm-watsonx-orchestrate==2.7.2"` for the `orchestrate` ADK
    CLI. Pin it: the ADK must match the cluster's Orchestrate release, and 2.8.0+
    can't manage agents on WXO 5.3.1. `python scripts/wxo_adk_check.py` checks
    the installed one against the server.

  Both scripts tell you which package is missing and how to install it rather
  than failing with a traceback, and the skill checks before it picks a path.
  Homebrew's Python (and recent Debian/Ubuntu) refuses a system-wide `pip
  install`; install into a virtualenv (`python3 -m venv .venv`) instead.

## Quick start

```bash
# 1. one-time setup — verifies creds and discovers your cluster's IDs
#    (macOS / Linux: python3 wherever these examples say python)
python scripts/cpd_init.py

# 2. check what got resolved (API key is masked)
python scripts/cpd_config.py show

# 3. use it
bash scripts/wx_chat.sh "Introduce yourself in one sentence."
python scripts/wx_connect.py
```

The wizard writes `~/.config/cpd-onprem/config.json` (git-ignored, `chmod 600`).

## Back an agent with an external provider (Claude, OpenAI, Gemini…)

watsonx Orchestrate can run a **native** agent on an external LLM through its
built-in AI Gateway. Put the provider key in `providers.env` (never on the command
line), then wire up a connection, a model and the agent in one command:

```bash
# 1. keys live here — git-ignored, one line per provider secret
cp providers.env.example ~/.config/cpd-onprem/providers.env
#    then edit it:  WXO_GOOGLE_API_KEY=...   (or WXO_ANTHROPIC_API_KEY=..., etc.)

# 2. one-shot: connection + model + native agent, and a smoke test
python scripts/wxo_setup_agent.py --provider google --model gemini-2.5-flash \
  --agent-name my_agent --test "Reply with exactly: PONG"

# 3. tear it all down again
python scripts/wxo_setup_agent.py --provider google --model gemini-2.5-flash \
  --agent-name my_agent --cleanup
```

The key is read from `providers.env` (or a `WXO_*` env var) by `wxo_add_provider.py`
and handed to the connection once — it is never printed, echoed, or written to a
spec. The gateway must be able to reach the provider's API (`api.anthropic.com`,
etc.); air-gapped clusters can point `--provider-config custom_host=…` at a
self-hosted OpenAI-compatible endpoint instead. Full flow, the provider→fields
table, and the runs-API call to invoke an agent are in
[references/orchestrate-adk.md](references/orchestrate-adk.md).

## Configuration & credentials

Every setting resolves as **explicit arg → `CPD_*` env var → config file**, so env
vars always override any file (handy for CI or a second cluster). The config file
itself is the first of these that exists:

1. `$CPD_CONFIG` — an explicit path, for juggling several clusters.
2. **`./config.json`** — in the checkout, beside `config.example.json`. Copy the
   example, fill it in, and the clone is self-contained.
3. `~/.config/cpd-onprem/config.json` — what `cpd_init.py` writes by default,
   shared by every checkout and by the installed skill.

`python scripts/cpd_config.py show` always names the file it actually read, so
there is never a question of which one won.

Cluster credentials live here. **External-provider** API keys (Claude, OpenAI,
Gemini…) are kept separately in `providers.env` — see the section above — so a
provider secret never has to sit beside your cluster config.

| Setting | Env var | Notes |
|---|---|---|
| cluster URL | `CPD_URL` | e.g. `https://host` |
| username | `CPD_USERNAME` | |
| API key | `CPD_API_KEY` | the **platform** key, or your password |
| default space | `CPD_SPACE_ID` | discovered by the wizard |
| default project | `CPD_PROJECT_ID` | |
| default deployment | `CPD_DEPLOYMENT_ID` | auto-discovered if unset |
| WXO instance URL | `CPD_WXO_INSTANCE_URL` | for the ADK |
| verify TLS | `CPD_VERIFY_SSL` | default off (self-signed); a warning is printed while off |
| CA bundle | `CPD_CA_BUNDLE` | PEM to verify against, for a cluster with a private CA |

**Signing in to the web console** (where you generate the API key): on a cluster
fronted by OpenShift, the login page asks for an identity provider first. Pick
**OpenShift authentication**, then **htpasswd**, then enter your cluster username
and password. Once inside, generate the platform API key from the profile page
and feed it to `cpd_init.py` or `CPD_API_KEY`.

### Supplying the API key

`cpd_init.py` prompts for the key but **does not store it by default** — it
verifies the key, discovers your cluster IDs, then asks *"Store the API key in the
config file? (y/N)"*. Answer **N** and only non-secret settings are written; the
key has to come from the environment on each use. Pick whichever fits:

**Option A — let the wizard store it** (simplest; single-user workstation):

```bash
python scripts/cpd_init.py        # answer y at "Store the API key..."
```

It lands in `~/.config/cpd-onprem/config.json`, which is `chmod 600` and matched
by `.gitignore`. Every script then works with no extra setup.

**Option B — keep it in the environment** (recommended; nothing secret on disk):

```bash
export CPD_API_KEY="<your-platform-api-key>"        # bash / zsh / WSL
```
```powershell
$env:CPD_API_KEY = "<your-platform-api-key>"        # PowerShell, current shell
[Environment]::SetEnvironmentVariable('CPD_API_KEY','<key>','User')   # persist
```

Set it before running any script. `CPD_*` env vars override the config file, so
this also works for a second cluster or for CI.

**Option C — your password instead of a key.** The CPD login password works in
place of the platform key for the REST, SDK and ADK paths. Put it in
`CPD_API_KEY` the same way.

**Option D — a self-contained checkout** (no wizard, nothing in your home dir):

```bash
cp config.example.json config.json   # then edit url / username / api_key
python scripts/cpd_config.py show    # confirms it read ./config.json
```

`config.json` is git-ignored at any depth, so it is never committed — and
`cpd_config.py` warns on every run if that `.gitignore` rule ever disappears.
Keep in mind the file still sits inside a work tree, where `git clean -x`, a
zip of the folder, or an editor's "add everything" can carry it off. Prefer
option A or B on a machine you share.

Whichever you choose, check it resolved (the key is masked in the output):

```bash
python scripts/cpd_config.py show
```

Nothing secret is ever **committed**, whichever option you pick. If a key leaks,
rotate it in the CPD profile page.

## Use as a Claude Code skill

Claude Code loads any folder placed in a `skills/` directory, as long as that
folder has a `SKILL.md` at its root — which this repo does. There is nothing to
build or register.

**1. Put the folder where Claude Code looks.** Personal (available in every
project) or project-scoped (shared with whoever clones that project):

```bash
REPO=https://github.com/AluminumShark/ibm-cpd-onprem.git

# personal — available in all your projects
git clone $REPO ~/.claude/skills/ibm-cpd-onprem

# or project-scoped — commit it with the project
git clone $REPO <project>/.claude/skills/ibm-cpd-onprem
```

On Windows the personal path is `%USERPROFILE%\.claude\skills\ibm-cpd-onprem`
(PowerShell: `$env:USERPROFILE\.claude\skills\ibm-cpd-onprem`).

Already cloned somewhere? `cp -r ibm-cpd-onprem ~/.claude/skills/` does the same.
The folder name is free, but `SKILL.md` must sit directly inside it — not one
level deeper.

**2. Start a new Claude Code session.** Skills are read at startup, so an already
running session will not see it.

**3. Confirm it loaded.** Run `/skills`; `ibm-cpd-onprem` should be listed.

**4. Set up credentials once** — see
[Supplying the API key](#supplying-the-api-key) above. The skill reads the same
`~/.config/cpd-onprem/config.json` and `CPD_*` env vars as the CLI, so if
`python scripts/cpd_config.py show` works, the skill works.

Then ask things like *"chat with gpt-oss on the on-prem cluster"*, *"list the
Orchestrate agents on my CPD"*, *"inventory watsonx.ai"* — the skill triggers and
runs the right path. `SKILL.md` is the entry point; `references/` holds the
detailed how-to.

**Keeping it current.** A `git clone` updates with
`git -C ~/.claude/skills/ibm-cpd-onprem pull`. A `cp -r` copy never updates —
copy it again after pulling, or it keeps serving old instructions (an older
copy, for example, still tells Claude to install the latest, unpinned ADK, which
can't manage agents on WXO 5.3.1). Start a new session afterwards.

## Layout

```
ibm-cpd-onprem/
├── SKILL.md              # skill entry point (how-to + path selection)
├── README.md
├── LICENSE               # Apache-2.0
├── NOTICE
├── config.example.json   # schema of ~/.config/cpd-onprem/config.json
├── references/           # rest-api · orchestrate-adk · watsonx-sdk · gotchas
└── scripts/
    ├── cpd_init.py       # interactive setup + ID discovery
    ├── cpd_config.py     # settings resolver + token/HTTP helpers (stdlib only)
    ├── cpd_token.sh      # print a bearer token
    ├── wx_chat.sh        # one-shot chat
    ├── wx_connect.py     # SDK read-only inventory
    ├── wxo_adk_check.py  # is the installed ADK compatible with this server?
    ├── wxo_add_provider.py  # external-LLM credentials -> WXO connection
    ├── wxo_setup_agent.py   # native agent backed by an external LLM
    └── wxo_run_agent.py     # invoke an agent over the runs API
```

## Verified against

Everything here was exercised end to end against a live cluster, not inferred
from docs. Other versions probably work; these are the ones actually tested.

| Component | Tested |
|---|---|
| IBM Cloud Pak for Data backend | 5.3 |
| `ibm-watsonx-ai` SDK | 1.3.39 (sends `version=5.2`, see below) |
| `ibm-watsonx-orchestrate` ADK | 2.7.2 (also 1.12.0, 2.3.4, 2.6.1; 2.8.0+ fails, see gotchas #11) |
| Python | 3.8.20 and 3.13.7 (unit tests pass on both) |
| Chat deployment | `openai/gpt-oss-120b` |

The SDK validates the product version against a built-in list and rejects a
backend newer than itself, so `wx_connect.py` falls back to the highest version
the installed SDK accepts and says so on stderr. Its read-only calls are
unaffected by that gap; do not assume the same for other APIs.

## Tests

Offline unit tests — no cluster, no credentials, no network:

```bash
uv run --with pytest pytest
```

They cover the things that silently break a working setup: config precedence
(including `CPD_VERIFY_SSL` over a stored value), the wizard keeping an existing
API key, resource ids not surviving a cluster or space switch, unreachable-host
diagnostics, `get api_key` refusing to print the key without `--reveal`, and the
`.sh` scripts' Python discovery and curl TLS flags (real bash, stub `curl`).
`pytest` is a dev dependency only; the toolkit itself stays standard-library.

CI runs them on Ubuntu and macOS against Python 3.8, 3.11 and 3.13; on macOS the
shell-script tests use the stock `/bin/bash` 3.2. On Windows they use Git Bash,
and skip without it.

## Contributing

Issues and PRs welcome. Please keep the standard-library-only promise for the
auth/chat/config scripts, and never commit real hostnames, IDs or credentials
(that's what `cpd_init.py` + the git-ignored config are for).

## License

[Apache-2.0](LICENSE).
