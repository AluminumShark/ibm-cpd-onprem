#!/usr/bin/env bash
# Print a CPD bearer token (~12h). Settings come from cpd_config.py
# (env vars CPD_* override ~/.config/cpd-onprem/config.json).
#   Usage:  TOKEN=$(bash cpd_token.sh)
set -euo pipefail
PY=${CPD_PYTHON:-python}
exec "$PY" "$(dirname "$0")/cpd_config.py" token
