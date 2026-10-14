#!/usr/bin/env python3
"""Register an external LLM provider's credentials as a watsonx Orchestrate
key_value connection, for use as a native-agent model via the AI Gateway.

The ONLY component in this toolkit that handles a provider's plaintext secret.
It reads each secret field from the environment or `providers.env` (real env var
wins, then the file), checks every required field is present, then hands the
value to the ADK once. It never prints, logs, or returns the value; on a missing
field it names the environment-variable NAME only.

Secret-input note (ADK 1.12.0-2.18.1): `orchestrate connections set-credentials` has no
file/stdin option — only `-e <key>=<value>` (and `--api-key` etc.), all on argv.
So a key_value secret is briefly visible to a local `ps` while the child runs.
This is local, single-user and short-lived; we never echo it and we scrub it from
any captured child output. There is no file/stdin alternative to prefer.

Resolution for every field value (mirrors cpd_config): real env var > file.
  file default:  ~/.config/cpd-onprem/providers.env   (chmod 600, git-ignored)
  override:      $WXO_PROVIDERS_ENV

Naming convention:  WXO_<PROVIDER_UPPER>_<FIELD_UPPER>
  e.g.  WXO_ANTHROPIC_API_KEY, WXO_OPENAI_API_KEY, WXO_GOOGLE_API_KEY,
        WXO_BEDROCK_AWS_ACCESS_KEY_ID, WXO_BEDROCK_AWS_SECRET_ACCESS_KEY

CLI:
    python wxo_add_provider.py --provider anthropic
    python wxo_add_provider.py --provider bedrock --connection wxo_bedrock --env draft
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# provider id -> which credential fields are secret (go into providers.env / the
# key_value connection) vs non-secret config (go into the model spec's
# provider_config, NOT the credential file). Field names match the ADK's
# ProviderConfig / Portkey key_value entries. Easy to extend — it is just data.
PROVIDER_FIELDS = {
    "openai":       {"secret": ["api_key"], "config": []},
    "anthropic":    {"secret": ["api_key"], "config": []},
    "google":       {"secret": ["api_key"], "config": []},
    "mistral-ai":   {"secret": ["api_key"], "config": []},
    "groq":         {"secret": ["api_key"], "config": []},
    "cohere":       {"secret": ["api_key"], "config": []},
    "together-ai":  {"secret": ["api_key"], "config": []},
    "openrouter":   {"secret": ["api_key"], "config": []},
    "x-ai":         {"secret": ["api_key"], "config": []},
    "jina":         {"secret": ["api_key"], "config": []},
    # ollama needs no real secret (the gateway accepts any api_key); point it at
    # your host with --provider-config custom_host=...
    "ollama":       {"secret": [], "config": ["custom_host"]},
    "azure-openai": {"secret": ["api_key"],
                     "config": ["custom_host"]},  # or resource/deployment/api_version
    "bedrock":      {"secret": ["aws_access_key_id", "aws_secret_access_key"],
                     "config": ["aws_region"]},
    "vertex-ai":    {"secret": ["vertex_service_account_json"],
                     "config": ["vertex_project_id", "vertex_region"]},
}
# Unknown providers: assume a single api_key and tell the user to confirm.
DEFAULT_FIELDS = {"secret": ["api_key"], "config": []}

_SECRETS: set[str] = set()   # plaintext values to scrub from any emitted text


def provider_fields(provider: str):
    """(fields dict, known?) — unknown providers fall back to api_key."""
    entry = PROVIDER_FIELDS.get(provider)
    if entry is not None:
        return entry, True
    return DEFAULT_FIELDS, False


def default_connection(provider: str) -> str:
    return "wxo_" + provider


def field_env_var(provider: str, field: str) -> str:
    """WXO_<PROVIDER_UPPER>_<FIELD_UPPER>, hyphens -> underscores."""
    clean = lambda s: s.upper().replace("-", "_")
    return "WXO_%s_%s" % (clean(provider), clean(field))


def providers_env_path() -> Path:
    override = os.environ.get("WXO_PROVIDERS_ENV")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "cpd-onprem" / "providers.env"


def load_providers_file(path=None) -> dict:
    """Parse NAME=VALUE lines; '#' comments and blank lines ignored. The value is
    the rest of the line, stripped — no quoting games."""
    if path is None:
        path = providers_env_path()
    out: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out                                   # absent file is fine
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        name, value = s.split("=", 1)
        out[name.strip()] = value.strip()
    return out


def resolve_field(env_name: str, file_values: dict):
    """Real environment variable wins, else the providers.env file."""
    v = os.environ.get(env_name)
    if v:
        return v
    return file_values.get(env_name)


def collect_credentials(provider: str, providers_file=None):
    """Return (creds {field: value}, missing [env-var names]). No printing."""
    entry, _ = provider_fields(provider)
    file_values = load_providers_file(providers_file)
    creds: dict[str, str] = {}
    missing: list[str] = []
    for field in entry["secret"]:
        env_name = field_env_var(provider, field)
        value = resolve_field(env_name, file_values)
        if value:
            creds[field] = value
            _SECRETS.add(value)                       # for output scrubbing
        else:
            missing.append(env_name)
    return creds, missing


def _scrub(text):
    """Replace any known secret value with *** before anything is emitted."""
    if not text:
        return text
    for v in _SECRETS:
        if v:
            text = text.replace(v, "***")
    return text


def _redacted_cmd(cmd):
    """A display copy of an argv with `key=value` secrets masked to `key=***`."""
    shown = []
    for a in cmd:
        if "=" in a and a.split("=", 1)[1] in _SECRETS:
            shown.append(a.split("=", 1)[0] + "=***")
        else:
            shown.append(a)
    return shown


def _run(cmd, redact=False):
    """Run an orchestrate command. Output is always scrubbed of secrets; the
    echoed command is redacted when it carries a secret."""
    sys.stdout.write("  $ " + " ".join(_redacted_cmd(cmd) if redact else cmd) + "\n")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.stdout:
        sys.stdout.write(_scrub(proc.stdout))
    if proc.stderr:
        sys.stderr.write(_scrub(proc.stderr))
    return proc


def _looks_present(proc) -> bool:
    out = ((proc.stdout or "") + (proc.stderr or "")).lower()
    return "exist" in out or "already" in out


def add_provider(provider, connection=None, env="draft", scope="team",
                 orchestrate="orchestrate", providers_file=None) -> int:
    """Ensure a key_value connection exists and carries the provider's secrets.
    Returns 0 on success, non-zero on missing creds or CLI failure."""
    connection = connection or default_connection(provider)
    entry, known = provider_fields(provider)
    if not known:
        sys.stderr.write(
            "[note] '%s' is not in the known provider map; assuming it needs an "
            "api_key. Confirm its required fields (orchestrate models import names "
            "them, or check the provider's docs).\n" % provider)

    creds, missing = collect_credentials(provider, providers_file)
    if missing:
        sys.stderr.write(
            "[error] missing credential(s) for provider '%s' — set the "
            "environment variable(s) below, or add them to %s:\n"
            % (provider, providers_env_path()))
        for name in missing:                          # names only, never values
            sys.stderr.write("    - %s\n" % name)
        return 2

    # 1. create the connection (idempotent: an existing one is not an error)
    proc = _run([orchestrate, "connections", "add", "-a", connection])
    if proc.returncode != 0 and not _looks_present(proc):
        sys.stderr.write("[error] 'connections add' failed for '%s'.\n" % connection)
        return proc.returncode or 1

    # 2. configure it as a team/member key_value connection
    proc = _run([orchestrate, "connections", "configure", "-a", connection,
                 "--env", env, "-k", "key_value", "-t", scope])
    if proc.returncode != 0:
        sys.stderr.write("[error] 'connections configure' failed for '%s'.\n" % connection)
        return proc.returncode or 1

    # 3. set the secret entries (if any). set-credentials has no file/stdin input
    #    on this ADK, so the value rides on argv — redacted in our echo, scrubbed
    #    from captured output; the brief local `ps` exposure is documented above.
    if creds:
        cmd = [orchestrate, "connections", "set-credentials", "-a", connection,
               "--env", env]
        for field, value in creds.items():
            cmd += ["-e", "%s=%s" % (field, value)]
        proc = _run(cmd, redact=True)
        if proc.returncode != 0:
            sys.stderr.write("[error] 'connections set-credentials' failed for '%s'.\n"
                             % connection)
            return proc.returncode or 1
        sys.stdout.write("[ok] credentials set on connection '%s' (%s).\n"
                         % (connection, ", ".join(creds.keys())))
    else:
        sys.stdout.write("[ok] connection '%s' needs no secret; non-secret config "
                         "(e.g. custom_host) goes in the model spec.\n" % connection)

    sys.stdout.write("[ok] connection: %s\n" % connection)
    return 0


def main(argv) -> int:
    p = argparse.ArgumentParser(description="Register an external LLM provider as "
                                            "a watsonx Orchestrate key_value connection.")
    p.add_argument("--provider", required=True,
                   help="provider id, e.g. anthropic, openai, google, bedrock")
    p.add_argument("--connection", default=None,
                   help="connection (app) id; default wxo_<provider>")
    p.add_argument("--env", default="draft", choices=["draft", "live"])
    p.add_argument("--scope", default="team", choices=["team", "member"])
    args = p.parse_args(argv)
    return add_provider(args.provider, connection=args.connection,
                        env=args.env, scope=args.scope)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
