# ibm-cpd-onprem

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
- **Encodes the gotchas** that otherwise cost an afternoon — console encoding,
  self-signed TLS, SDK version rejection, chat body validation, `cpdctl` locale
  panic (see [references/gotchas.md](references/gotchas.md)).

## Requirements

- Python 3.8+ (the auth/chat/config scripts are **standard-library only**).
- `curl` (for `wx_chat.sh`) and a POSIX shell, or use the PowerShell snippets in
  the references.
- Optional: `pip install ibm-watsonx-ai` for `wx_connect.py`;
  `pip install ibm-watsonx-orchestrate` for the ADK path.

## Quick start

```bash
# 1. one-time setup — verifies creds and discovers your cluster's IDs
python scripts/cpd_init.py

# 2. check what got resolved (API key is masked)
python scripts/cpd_config.py show

# 3. use it
bash scripts/wx_chat.sh "Introduce yourself in one sentence."
python scripts/wx_connect.py
```

The wizard writes `~/.config/cpd-onprem/config.json` (git-ignored, `chmod 600`).

## Configuration & credentials

Every setting resolves as **explicit arg → `CPD_*` env var → config file**, so env
vars always override the file (handy for CI or a second cluster):

| Setting | Env var | Notes |
|---|---|---|
| cluster URL | `CPD_URL` | e.g. `https://host` |
| username | `CPD_USERNAME` | |
| API key | `CPD_API_KEY` | the **platform** key, or your password |
| default space | `CPD_SPACE_ID` | discovered by the wizard |
| default project | `CPD_PROJECT_ID` | |
| default deployment | `CPD_DEPLOYMENT_ID` | auto-discovered if unset |
| WXO instance URL | `CPD_WXO_INSTANCE_URL` | for the ADK |
| verify TLS | `CPD_VERIFY_SSL` | default off (self-signed) |

**The API key is never stored by default** — the wizard asks, and the default is to
keep it in `CPD_API_KEY` instead of the file. Nothing secret is ever written to
this repo. If a key leaks, rotate it in the CPD profile page.

## Use as a Claude Code skill

Drop the folder into your skills directory and Claude will load it:

```bash
# personal (all projects)
cp -r ibm-cpd-onprem ~/.claude/skills/
# or project-scoped
cp -r ibm-cpd-onprem <project>/.claude/skills/
```

Then ask things like *"chat with gpt-oss on the on-prem cluster"*, *"list the
Orchestrate agents on my CPD"*, *"inventory watsonx.ai"* — the skill triggers and
runs the right path. `SKILL.md` is the entry point; `references/` holds the
detailed how-to.

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
    └── wx_connect.py     # SDK read-only inventory
```

## Contributing

Issues and PRs welcome. Please keep the standard-library-only promise for the
auth/chat/config scripts, and never commit real hostnames, IDs or credentials
(that's what `cpd_init.py` + the git-ignored config are for).

## License

[Apache-2.0](LICENSE).
