#!/usr/bin/env bash
# One-shot chat against a deployed foundation model on the configured cluster.
#   Usage:  bash wx_chat.sh "your question"  [deployment_id]
# Deployment: arg2 > CPD_DEPLOYMENT_ID > config > auto-discovered ready one.
# Settings & token come from cpd_config.py. Prints the assistant answer only.
set -euo pipefail
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1   # avoid cp950 crash on CJK/emoji output

# Python 3.8+: $CPD_PYTHON, else the first of python3/python that actually runs
# (macOS has no `python`; Windows' `python3` may be a Store stub that fails).
PY=${CPD_PYTHON:-}
if [ -z "$PY" ]; then
  for c in python3 python; do
    if "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then PY=$c; break; fi
  done
fi
[ -n "$PY" ] || { echo "no Python 3.8+ found (tried python3, python) — install one or set CPD_PYTHON" >&2; exit 1; }
HERE="$(dirname "$0")"

PROMPT="${1:?usage: wx_chat.sh \"question\" [deployment_id]}"
URL=$("$PY" "$HERE/cpd_config.py" get url)
[ -n "$URL" ] || { echo "no cluster URL — run cpd_init.py or set CPD_URL" >&2; exit 1; }
TOKEN=$("$PY" "$HERE/cpd_config.py" token)
DEP="${2:-$("$PY" "$HERE/cpd_config.py" resolve-deployment)}"
VERIFY=$("$PY" "$HERE/cpd_config.py" get verify_ssl)

CURL=(-sS -m 180)  # -S: show curl's error, not a silent set -e exit; array keeps a CA path with spaces one argument
case "$VERIFY" in
  True|true|1)     # verify, against the private CA bundle when one is configured
    CA=$("$PY" "$HERE/cpd_config.py" get ca_bundle)
    if [ -n "$CA" ]; then CURL+=(--cacert "$CA"); fi ;;
  *) CURL+=(-k) ;;   # self-signed -> -k
esac

payload=$(PROMPT="$PROMPT" "$PY" -c 'import os,json;print(json.dumps({"messages":[{"role":"user","content":os.environ["PROMPT"]}]}))')

resp=$(curl "${CURL[@]}" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  "$URL/ml/v1/deployments/$DEP/text/chat?version=2024-05-01" -d "$payload")

# printf, not echo: macOS's sh expands backslashes such as \n inside the JSON
printf '%s\n' "$resp" | "$PY" -c '
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
