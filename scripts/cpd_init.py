#!/usr/bin/env python
"""Interactive setup for an on-prem IBM Cloud Pak for Data cluster.

Prompts for the cluster URL, username and API key, verifies them by fetching a
token, then queries the cluster to let you pick a default space, deployment,
project and watsonx Orchestrate instance — so you never have to know any IDs by
hand. Writes everything to ~/.config/cpd-onprem/config.json (git-ignored, chmod
600 where supported).

Run:  python cpd_init.py
Re-run any time to point at a different cluster or refresh the discovered IDs.
Pure standard library; works offline-free against any CPD/Software Hub cluster.
"""
import json
import os
import sys
from getpass import getpass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpd_config as C  # noqa: E402


def ask(prompt, default=None, secret=False):
    suffix = f" [{default}]" if default else ""
    while True:
        val = (getpass(f"{prompt}{suffix}: ") if secret
               else input(f"{prompt}{suffix}: ").strip())
        if val:
            return val
        if default is not None:
            return default
        print("  (required)")


def choose(label, items, render, current=None):
    """Let the user pick one item from a list; return the chosen item or None."""
    if not items:
        print(f"  (no {label} found)")
        return None
    print(f"\n{label}:")
    for i, it in enumerate(items, 1):
        mark = "  *" if current and render(it)[0] == current else "   "
        print(f"{mark}{i:>2}. {render(it)[1]}")
    print("    0. skip")
    while True:
        raw = input(f"pick a {label} number [0]: ").strip() or "0"
        if raw.isdigit():
            n = int(raw)
            if n == 0:
                return None
            if 1 <= n <= len(items):
                return items[n - 1]
        print("  invalid choice")


def main():
    print("=== IBM Cloud Pak for Data — connection setup ===\n")
    existing = C.load_file()

    url = ask("Cluster URL", existing.get("url") or os.environ.get("CPD_URL"))
    username = ask("Username", existing.get("username")
                   or os.environ.get("CPD_USERNAME"))
    key_hint = "(blank keeps current / uses CPD_API_KEY)" if (
        existing.get("api_key") or os.environ.get("CPD_API_KEY")) else ""
    api_key = getpass(f"API key {key_hint}: ").strip()

    verify_default = bool(existing.get("verify_ssl", False))
    verify = ask("Verify TLS cert? (y/N — N for self-signed)",
                 "y" if verify_default else "N").lower().startswith("y")

    # Build a throwaway cfg for verification/discovery (env still overrides inside C)
    cfg = dict(existing)
    cfg.update(url=url, username=username, verify_ssl=verify)
    if api_key:
        cfg["api_key"] = api_key

    print("\nverifying credentials…")
    token = C.get_token(cfg)  # exits with a clear message on failure
    print("  ok — authenticated.")

    # ---- discover scopes -------------------------------------------------
    _, sp = C.http("GET", "/v2/spaces?limit=100", token=token, cfg=cfg)
    spaces = sp.get("resources", []) if isinstance(sp, dict) else []
    chosen_space = choose(
        "space", spaces,
        lambda s: (s["metadata"]["id"], f'{s["entity"]["name"]}  ({s["metadata"]["id"]})'),
        current=cfg.get("space_id"))
    space_id = chosen_space["metadata"]["id"] if chosen_space else cfg.get("space_id", "")

    deployment_id = cfg.get("deployment_id", "")
    if space_id:
        _, dp = C.http("GET",
                       f"/ml/v4/deployments?space_id={space_id}&version=2024-05-01",
                       token=token, cfg=cfg)
        deps = dp.get("resources", []) if isinstance(dp, dict) else []

        def dep_render(d):
            e = d["entity"]
            bm = e.get("base_model_id")
            model = bm.get("model_id") if isinstance(bm, dict) else (bm or "")
            state = e.get("status", {}).get("state", "")
            return (d["metadata"]["id"],
                    f'{e.get("name")}  [{model} / {state}]  ({d["metadata"]["id"]})')
        chosen_dep = choose("deployment", deps, dep_render, current=deployment_id)
        if chosen_dep:
            deployment_id = chosen_dep["metadata"]["id"]

    _, pr = C.http("GET", "/v2/projects?limit=100", token=token, cfg=cfg)
    projects = pr.get("resources", []) if isinstance(pr, dict) else []
    chosen_proj = choose(
        "project", projects,
        lambda p: (p["metadata"]["guid"],
                   f'{p["entity"]["name"]}  ({p["metadata"]["guid"]})'),
        current=cfg.get("project_id"))
    project_id = chosen_proj["metadata"]["guid"] if chosen_proj else cfg.get("project_id", "")

    # watsonx Orchestrate instance (optional, for the ADK)
    wxo_url = cfg.get("wxo_instance_url", "")
    _, si = C.http("GET",
                   "/zen-data/v3/service_instances?fetch_all_instances=true",
                   token=token, cfg=cfg)
    insts = [i for i in (si.get("service_instances", []) if isinstance(si, dict) else [])
             if i.get("addon_type") == "orchestrate"]
    chosen_wxo = choose(
        "watsonx Orchestrate instance", insts,
        lambda i: (str(i.get("id")), f'{i.get("display_name")}  (id {i.get("id")})'))
    if chosen_wxo:
        wxo_url = (url.rstrip("/") +
                   f"/orchestrate/cpd-instance-operands/instances/{chosen_wxo['id']}")

    # ---- store api key? --------------------------------------------------
    store_key = False
    if api_key:
        store_key = ask("Store the API key in the config file? (y/N — N = use "
                        "CPD_API_KEY env var)", "N").lower().startswith("y")

    out = {
        "url": url,
        "username": username,
        "api_key": api_key if (api_key and store_key) else "",
        "verify_ssl": verify,
        "space_id": space_id,
        "project_id": project_id,
        "deployment_id": deployment_id,
        "wxo_instance_url": wxo_url,
    }
    C.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(C.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(C.CONFIG_PATH, 0o600)
    except Exception:
        pass

    print(f"\nsaved → {C.CONFIG_PATH}")
    shown = dict(out); shown["api_key"] = C._mask(out["api_key"]) if out["api_key"] else "(use CPD_API_KEY)"
    print(json.dumps(shown, ensure_ascii=False, indent=2))
    if not out["api_key"]:
        var = "$env:CPD_API_KEY" if os.name == "nt" else "export CPD_API_KEY="
        print(f"\nAPI key not stored. Set it per shell, e.g.  {var}\"<key>\"")
    print("\nDone. Try:  python cpd_config.py show   |   bash wx_chat.sh \"hello\"")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\naborted.")
        sys.exit(130)
