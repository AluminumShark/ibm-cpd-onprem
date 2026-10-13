# Design: External LLM providers as watsonx Orchestrate agent models

**Date:** 2026-10-13
**Status:** approved design, pending implementation
**Scope:** Add first-class support to the `ibm-cpd-onprem` skill for backing a
watsonx Orchestrate (WXO) *native* agent with an external LLM provider (Anthropic
Claude, OpenAI, Google Gemini, Mistral, Groq, Azure OpenAI, Bedrock, Vertex AI,
Ollama / OpenAI-compatible self-hosted, …) through WXO's built-in AI Gateway
("virtual models"), without any provider API key leaking into the chat
transcript, Claude's visible commands, shell history, or the repo.

This capability was verified end-to-end on the target cluster on 2026-10-13
(IBM Software Hub 5.3.x, WXO 5.3.1, ADK v1.12.0): a `zytest_` Gemini connection +
`virtual-model/google/gemini-2.5-flash` + native agent returned a live answer via
the runs API, then was cleaned up. The gateway's outbound egress works on this
cluster.

## Goals

- A documented, repeatable flow for registering an external provider model and
  attaching it to a native agent, plus invoking/testing it.
- Credentials supplied so their plaintext value never appears in the transcript,
  Claude's command text, shell history, or git.
- Cross-provider: a provider→required-fields map, not a hard-coded `api_key`.
- Three composable stdlib helpers + a docs section + offline tests, matching the
  project's existing style (stdlib-only scripts, reference docs, pytest with fake
  CLI stubs). No new runtime dependencies.

## Non-goals

- No support for `external`/`assistant` agent types (they bring their own backend;
  only `native` agents use the `llm:` field).
- No automatic provisioning of provider accounts or egress/network changes.
- No GUI; CLI + config files only.

## Background facts (verified)

- The WXO AI Gateway is Portkey-based. Models are named
  `virtual-model/<provider>/<model-id>`; the ADK auto-prepends `virtual-model/`
  and infers the provider from the 2nd path segment.
- Provider IDs (ADK `ModelProvider` enum): `openai, anthropic, azure-openai,
  azure-ai, bedrock, google, vertex-ai, mistral-ai, cohere, groq, ollama,
  openrouter, x-ai, together-ai, huggingface, a21, anyscale, cerebras, jina,
  stability-ai, watsonx`.
- A model's `--app-id` must reference a **key_value** connection.
- The ADK auto-injects `config.max_tokens: 4096` for `anthropic` models.
- Only tool-calling-capable models work as agent LLMs with tools.
- **Runtime invocation (not in IBM docs; discovered here):**
  - `POST {wxo_instance_url}/v1/orchestrate/runs` with body
    `{"agent_id": "<id>", "message": {"role": "user", "content": "<text>"}}`
    returns `{thread_id, run_id, task_id, message_id}` (async).
  - Read the reply with `GET {wxo_instance_url}/v1/orchestrate/threads/{thread_id}/messages`;
    take the last `role == "assistant"` message; its `content` is a list of
    `{"response_type":"text","text":...}` parts.
  - The agent list is `GET {wxo_instance_url}/v1/orchestrate/agents` (a JSON array;
    each item has `id`, `name`, `llm`, …).
  - The gateway's raw OpenAI-compatible endpoint
    `POST {wxo_instance_url}/v1/orchestrate/v1/chat/completions` returns HTTP 500;
    **use the runs path, not raw completions.**

## Architecture

Three single-purpose stdlib scripts under `scripts/`, composed by the one-shot
helper. All reuse `cpd_config.py` for settings/token and follow its resolution
order (env var > config file). All run under `PYTHONIOENCODING=utf-8 PYTHONUTF8=1`.

### 1. Credential store: `providers.env`

- Default path `~/.config/cpd-onprem/providers.env` (same dir as `config.json`),
  created chmod 600, git-ignored. Overridable with `$WXO_PROVIDERS_ENV`.
- Format: `NAME=VALUE` lines, `#` comments, blank lines ignored. No quoting games;
  value is the rest of the line, stripped.
- Resolution for any field value: real environment variable wins, else the file.
  (Mirrors `cpd_config.get`.)
- Naming convention: `WXO_<PROVIDER_UPPER>_<FIELD_UPPER>`, e.g.
  `WXO_ANTHROPIC_API_KEY`, `WXO_OPENAI_API_KEY`, `WXO_GOOGLE_API_KEY`,
  `WXO_BEDROCK_AWS_ACCESS_KEY_ID`, `WXO_BEDROCK_AWS_SECRET_ACCESS_KEY`.
- A committed `providers.env.example` documents the convention with commented
  placeholders per common provider. `.gitignore` gets a `providers.env` line; the
  existing stdlib `.gitignore`-shield warning pattern in `cpd_config.py` is the
  reference for tone (no new shield check required for providers.env, but mention
  it in the example header).

### 2. Provider field map

A static dict in `wxo_add_provider.py` (importable by the others). For each
provider: which credential fields are **secret** (→ providers.env) and which are
**non-secret config** (→ the model spec's `provider_config`, NOT the credential
file). Minimum coverage:

| Provider | secret credential fields | non-secret config fields |
|---|---|---|
| openai, anthropic, google, mistral-ai, groq, cohere, together-ai, openrouter, x-ai, jina | `api_key` | — |
| ollama | (none required) | `custom_host` |
| azure-openai | `api_key` | `custom_host` or resource/deployment/api_version |
| bedrock | `aws_access_key_id`, `aws_secret_access_key` | `aws_region` |
| vertex-ai | service-account credential (JSON string field) | `vertex_project_id`, `vertex_region` |

Unknown providers: default to requiring `api_key`, and print a note telling the
user to confirm the provider's required fields (the ADK `models import` output
also names them). The map is data, easy to extend.

### 3. `scripts/wxo_add_provider.py` — the credential step (secret handling)

- CLI: `--provider <id>` (required), `--connection <name>` (default
  `wxo_<provider>`), `--env <draft|live>` (default `draft`),
  `--scope <team|member>` (default `team`).
- Behaviour: look up the provider's secret fields; read each from env/providers.env;
  if any is missing, exit non-zero naming the **environment-variable name(s)**
  only — never the value, never a partial value. Then run, via `subprocess`:
  - `orchestrate connections add -a <name>` (idempotent: treat "already exists" as ok)
  - `orchestrate connections configure -a <name> --env <env> -k key_value -t <scope>`
  - `orchestrate connections set-credentials -a <name> --env <env> -e "<field>=<value>" …`
- Secret passing: at implementation, first check `orchestrate connections
  set-credentials --help` for a file/stdin option to avoid argv exposure. If one
  exists, use it (write a chmod-600 temp file in the scratchpad, delete in a
  `finally`). If not, pass `-e field=value` and document the brief, local,
  single-user `ps` exposure in a code comment and the docs. Never log the command
  with the value expanded; never echo the value.
- Prints only status lines and the connection name. Exit codes: 0 ok, non-zero on
  missing creds / CLI failure.

### 4. `scripts/wxo_run_agent.py` — invoke an agent and get its reply

- CLI: `--agent <name|id>` (required), `--message <text>` (required),
  `--timeout <seconds>` (default 60), `--json` (print raw assistant content).
- Resolves the agent id (if a name was given) via `GET /v1/orchestrate/agents`.
- `POST /v1/orchestrate/runs`, then polls `GET /v1/orchestrate/threads/{thread_id}/messages`
  until an assistant message appears or timeout; prints the assistant text.
- Uses `cpd_config.http` / `get_token` / `get('wxo_instance_url')`. Read-mostly:
  the only writes are creating a run (inherent to invoking an agent).
- Exit non-zero on timeout or error, with a clear message.

### 5. `scripts/wxo_setup_agent.py` — one-shot full automation

- CLI (core): `--provider`, `--model` (e.g. `claude-3-5-sonnet-20241022` or
  `gemini-2.5-flash`), `--agent-name`, `--instructions` (default a generic one),
  `--connection` (default `wxo_<provider>`), `--display-name`, `--model-type`
  (default `chat`), `--provider-config KEY=VALUE` (repeatable, for non-secret
  fields like `custom_host`), `--test "<prompt>"` (optional), `--cleanup`.
- Flow:
  1. Call `wxo_add_provider` (import as a module, don't shell out to itself) to
     ensure the connection + credentials.
  2. Generate a model spec dict and `orchestrate models import --file <tmp> --app-id <conn>`
     (model name `virtual-model/<provider>/<model>`; the ADK adds the prefix when
     given `<provider>/<model>`). Non-secret `--provider-config` entries go into
     the spec's `provider_config`.
  3. Generate a native agent spec and `orchestrate agents import -f <tmp>`
     (`llm: virtual-model/<provider>/<model>`).
  4. If `--test`, call `wxo_run_agent` and print the reply.
- `--cleanup` mode: remove agent → model → connection (reverse order) and re-list
  to confirm, mirroring the verified teardown.
- Temp spec files go in the scratchpad (or a tempdir), cleaned up in `finally`.
- Reuses the field map and the credential helper; no secret ever passes through a
  spec file or argv from this script.

### 6. Docs: `references/orchestrate-adk.md` new section

"Back a native agent with an external provider (AI Gateway)" covering: concept
(virtual models, native-agent-only, tool-calling-only), the **egress
requirement** and air-gap fallbacks (`custom_host`/ollama/watsonx.ai-hosted), the
provider→fields table, the one-shot helper usage AND the equivalent manual
`orchestrate` commands, the runs invocation (with the 500-on-raw-completions
note), cleanup, and the `zytest_` convention. Cross-link from the "Choosing a
path" table in `SKILL.md`.

### 7. `SKILL.md` safety rails + credentials

- New hard rule under Safety rails: *Never read, print, echo, or inline an
  external-provider API key. Supply it only via `providers.env` / `WXO_*` env
  vars; let `wxo_add_provider.py` set it. If a key is pasted into chat, treat it
  as compromised and tell the user to rotate it.*
- Add `providers.env` to the credential story (a short note next to the config
  file description) and a `providers.env.example` pointer.

### 8. Tests: `tests/test_wxo_providers.py` (offline)

Following `tests/test_shell_scripts.py` (fake CLI stubs) and `conftest.py` env
cleanup. Cover:
- Field-map lookup: known provider → expected secret fields; unknown → `api_key`
  default + note.
- Missing credential → error names the **env-var name**, asserts the value/secret
  does NOT appear in stderr.
- `providers.env` parsing: comments/blank lines ignored; real env var overrides
  the file.
- `wxo_add_provider` builds the expected `orchestrate connections …` calls
  (assert against a fake `orchestrate` stub that records argv); assert no secret
  in a recorded log file when a stdin/file path is used (if supported).
- `wxo_run_agent` parses an assistant reply out of a canned threads/messages JSON
  (monkeypatch `cpd_config.http`).
- `conftest.py`: also clear `WXO_*` and `WXO_PROVIDERS_ENV`.

No test makes a real network call or touches the cluster.

## Security model

- The only component that handles the plaintext secret is `wxo_add_provider.py`,
  reading from env/providers.env and passing it to the ADK once. It never prints,
  logs, or returns the value.
- Claude's operating rule (SKILL.md) forbids inlining keys; Claude references
  `WXO_*` / providers.env and runs the helpers.
- `providers.env` is chmod 600 and git-ignored, same protections as `config.json`.
- Residual exposure: the provider key is momentarily in the ADK child process
  (argv or env) during `set-credentials`; this is local, single-user, and brief,
  and is documented. Preference order to minimize it: file/stdin > child env >
  argv, chosen by what `set-credentials` supports.

## Verification plan

- Offline: `uv run --with pytest pytest` green, including the new tests; new tests
  fail if the helpers are reverted (prove they test real behaviour).
- `bash -n` n/a (python helpers). `python -m py_compile` the new scripts.
- Optional live smoke (only with user go-ahead and a key in providers.env):
  `wxo_setup_agent.py --provider google --model gemini-2.5-flash
  --agent-name zytest_x --test "Reply with exactly: PONG" --cleanup`, then
  confirm nothing `zytest_` remains. Not part of CI.

## Open questions / to confirm during implementation

- Exact `orchestrate connections set-credentials` secret-input options (file/stdin
  vs `-e`) on ADK 1.12.0 — determines the argv-exposure handling.
- Exact `provider_config` field names for azure-openai / bedrock / vertex-ai in
  this ADK version (the map above lists intent; confirm spellings from ADK source
  or docs, or leave them pass-through via `--provider-config`).
