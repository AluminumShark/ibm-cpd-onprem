#!/usr/bin/env bash
# Print a CPD bearer token (~12h). Settings come from cpd_config.py
# (env vars CPD_* override ~/.config/cpd-onprem/config.json).
#   Usage:  TOKEN=$(bash cpd_token.sh)
set -euo pipefail

# Python 3.8+: $CPD_PYTHON, else the first of python3/python that actually runs
# (macOS has no `python`; Windows' `python3` may be a Store stub that fails).
PY=${CPD_PYTHON:-}
if [ -z "$PY" ]; then
  for c in python3 python; do
    if "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then PY=$c; break; fi
  done
fi
[ -n "$PY" ] || { echo "no Python 3.8+ found (tried python3, python) — install one or set CPD_PYTHON" >&2; exit 1; }
exec "$PY" "$(dirname "$0")/cpd_config.py" token
