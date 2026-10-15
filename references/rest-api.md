# REST API path (CPD bearer token + curl)

All verified first-hand against a live cluster. On-prem clusters usually use a
self-signed cert → every `curl` uses `-k` (drop it once a real CA is trusted, or
swap it for `--cacert "$CPD_CA_BUNDLE"` with a private CA).
Resolve `$CPD_URL` etc. from config:
`python "$S/scripts/cpd_config.py" get url` (`python3` on macOS/Linux).

Commands below assume `S` holds this skill's base directory, set in the same
call (see SKILL.md); the shell usually sits in the user's project, not here.

## 1. Get a bearer token (valid ~12h)
```bash
TOKEN=$(bash "$S/scripts/cpd_token.sh")          # uses cpd_config.py
AUTH="Authorization: Bearer $TOKEN"
CPD_URL=$(python "$S/scripts/cpd_config.py" get url)
```
Equivalent raw call:
```bash
curl -sk -m 30 -X POST "$CPD_URL/icp4d-api/v1/authorize" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$CPD_USERNAME\",\"api_key\":\"$CPD_API_KEY\"}"
```
A 200 looks like `{"_messageCode_":"200","message":"Success","token":"..."}`.
`401` = wrong key/user, or the key belongs to a different account.

## 2. Chat with a deployed foundation model
```bash
DEP=$(python "$S/scripts/cpd_config.py" resolve-deployment)
curl -sk -m 180 -H "$AUTH" -H 'Content-Type: application/json' \
  "$CPD_URL/ml/v1/deployments/$DEP/text/chat?version=2024-05-01" \
  -d '{"messages":[{"role":"user","content":"Introduce yourself in one sentence."}]}'
```
- **Body may contain only** `messages` (+ optional `context`, `tools`,
  `tool_choice`, `tool_choice_option`). Adding `max_tokens` etc. → HTTP 400
  `json_validation_error`; generation params are baked into the deployment.
- Use `version=2024-05-01`. Older stamps are unreliable on current clusters.
- Response: `.choices[0].message.content` (answer),
  `.choices[0].message.reasoning_content` (chain-of-thought — usually stripped),
  `.usage` (tokens). Third-party-model deployments add a licence disclaimer under
  `.system.warnings` — expected.
- Streaming: same URL with `/text/chat_stream` → `text/event-stream` SSE.
- Tool calling: add a `tools` array of OpenAI-style function specs (works on
  models whose specs list `chat_function_calling`).

## 3. Inventory endpoints
```bash
# Installed services / add-ons
curl -sk -H "$AUTH" "$CPD_URL/zen-data/v1/addOn/query" -X POST \
  -H 'Content-Type: application/json' -d '{}'

# All service instances (watsonx Orchestrate, volumes, ...)
curl -sk -H "$AUTH" "$CPD_URL/zen-data/v3/service_instances?fetch_all_instances=true"

# Spaces and projects
curl -sk -H "$AUTH" "$CPD_URL/v2/spaces?limit=50"
curl -sk -H "$AUTH" "$CPD_URL/v2/projects?limit=50"

# Assets in a project (prompts, notebooks, flows, ...)
PROJECT_ID=$(python "$S/scripts/cpd_config.py" get project_id)
curl -sk -H "$AUTH" -X POST \
  "$CPD_URL/v2/asset_types/asset/search?project_id=$PROJECT_ID" \
  -H 'Content-Type: application/json' -d '{"query":"*:*","limit":100}'

# WML deployments in a space
SPACE_ID=$(python "$S/scripts/cpd_config.py" get space_id)
curl -sk -H "$AUTH" "$CPD_URL/ml/v4/deployments?space_id=$SPACE_ID&version=2024-05-01"

# Foundation model specs available to this cluster
curl -sk -H "$AUTH" "$CPD_URL/ml/v1/foundation_model_specs?version=2024-05-01&limit=100"
```

## 4. Parsing tips
- Pipe JSON through `python -c` for robust parsing; `jq` may not be installed.
- Prefix with `export PYTHONIOENCODING=utf-8 PYTHONUTF8=1` when a Python parser in
  the pipe may print CJK (see gotchas.md).

## PowerShell equivalents
```powershell
$body = @{ username = $env:CPD_USERNAME; api_key = $env:CPD_API_KEY } | ConvertTo-Json
$tok  = (Invoke-RestMethod -SkipCertificateCheck -Method Post `
         -Uri "$env:CPD_URL/icp4d-api/v1/authorize" `
         -ContentType 'application/json' -Body $body).token
$H = @{ Authorization = "Bearer $tok" }
$chat = @{ messages = @(@{ role='user'; content='Introduce yourself in one sentence.' }) } | ConvertTo-Json -Depth 6
Invoke-RestMethod -SkipCertificateCheck -Method Post -Headers $H -ContentType 'application/json' `
  -Uri "$env:CPD_URL/ml/v1/deployments/$env:CPD_DEPLOYMENT_ID/text/chat?version=2024-05-01" -Body $chat
```
`-SkipCertificateCheck` needs PowerShell 7+. On Windows PowerShell 5.1 use
`curl.exe -k` instead.
