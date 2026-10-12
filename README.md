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

Whichever you choose, check it resolved (the key is masked in the output):

```bash
python scripts/cpd_config.py show
```

Nothing secret is ever written into this repo. If a key leaks, rotate it in the
CPD profile page.

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
