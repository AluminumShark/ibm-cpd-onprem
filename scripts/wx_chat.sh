#!/usr/bin/env bash
# One-shot chat against a deployed foundation model on the configured cluster.
#   Usage:  bash wx_chat.sh "your question"  [deployment_id]
# Deployment: arg2 > CPD_DEPLOYMENT_ID > config > auto-discovered ready one.
# Settings & token come from cpd_config.py. Prints the assistant answer only.
set -euo pipefail
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1   # avoid cp950 crash on CJK/emoji output
PY=${CPD_PYTHON:-python}
HERE="$(dirname "$0")"

PROMPT="${1:?usage: wx_chat.sh \"question\" [deployment_id]}"
URL=$("$PY" "$HERE/cpd_config.py" get url)
[ -n "$URL" ] || { echo "no cluster URL — run cpd_init.py or set CPD_URL" >&2; exit 1; }
TOKEN=$("$PY" "$HERE/cpd_config.py" token)
DEP="${2:-$("$PY" "$HERE/cpd_config.py" resolve-deployment)}"
VERIFY=$("$PY" "$HERE/cpd_config.py" get verify_ssl)

CURL="-s -m 180"
case "$VERIFY" in True|true|1) : ;; *) CURL="$CURL -k";; esac   # self-signed -> -k

payload=$(PROMPT="$PROMPT" "$PY" -c 'import os,json;print(json.dumps({"messages":[{"role":"user","content":os.environ["PROMPT"]}]}))')

resp=$(curl $CURL -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  "$URL/ml/v1/deployments/$DEP/text/chat?version=2024-05-01" -d "$payload")

echo "$resp" | "$PY" -c '
import sys, json
d = json.load(sys.stdin)
ch = d.get("choices")
if ch:
    print(ch[0]["message"].get("content",""))
    u = d.get("usage",{})
    if u: sys.stderr.write(f"[usage] {u}\n")
else:
    print(json.dumps(d, ensure_ascii=False)[:600])
'
