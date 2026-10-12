#!/usr/bin/env python
"""Connect to the configured CPD cluster via the ibm_watsonx_ai SDK and print a
read-only inventory (deployments, chat/embedding models, spaces). Creates nothing.

Settings come from cpd_config.py (env CPD_* > ~/.config/cpd-onprem/config.json).
Requires the ibm_watsonx_ai package (the other scripts here do not).

Run:  python wx_connect.py
"""
import os
import sys
import urllib3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpd_config as C  # noqa: E402

urllib3.disable_warnings()


def pick_supported_version(requested):
    """Return a product version the installed SDK accepts.

    The SDK validates `version` against a built-in list; a cluster newer than the
    SDK (e.g. backend 5.3 with an SDK that tops out at 5.2) is rejected even
    though the APIs are identical. Fall back to the SDK's highest supported value.
    """
    try:
        from ibm_watsonx_ai.utils.utils import CPDVersion
        supported = list(CPDVersion.supported_version_list)
    except Exception:
        return requested or "5.2"
    if requested and requested in supported:
        return requested
    # choose the numerically highest supported version
    def keyf(v):
        try:
            return tuple(int(x) for x in str(v).split("."))
        except Exception:
            return (0,)
    best = max(supported, key=keyf) if supported else (requested or "5.2")
    if requested and requested != best:
        sys.stderr.write(f"[info] SDK does not accept version={requested}; using {best} "
                         f"(API behaviour is identical)\n")
    return best


def main():
    from ibm_watsonx_ai import APIClient, Credentials

    url = C.get("url")
    username = C.get("username")
    api_key = C.get("api_key")
    for name, val in (("CPD_URL", url), ("CPD_USERNAME", username), ("CPD_API_KEY", api_key)):
        if not val:
            sys.exit(f"missing {name} — run cpd_init.py or set the env var")

    version = pick_supported_version(C.get("cpd_version") or os.environ.get("CPD_VERSION"))
    verify = C.get("verify_ssl")

    creds = Credentials(url=url, username=username, api_key=api_key,
                        instance_id="openshift", version=version, verify=verify)
    client = APIClient(creds)
    print(f"connected | SDK {client.version} | version={version}")

    space_id = C.get("space_id")
    if space_id:
        client.set.default_space(space_id)       # required before catalog calls

        deps = client.deployments.get_details().get("resources", [])
        print(f"\ndeployments in space ({len(deps)}):")
        for r in deps:
            e = r["entity"]
            bm = e.get("base_model_id")
            model = bm.get("model_id") if isinstance(bm, dict) else bm
            print("  -", r["metadata"]["id"], "|", e.get("name"), "|", model,
                  "|", e.get("status", {}).get("state"))

        fm = client.foundation_models

        def ids(fn):
            try:
                d = fn()
                res = d.get("resources", d) if isinstance(d, dict) else d
                return [x.get("model_id") for x in res] if isinstance(res, list) else []
            except Exception as ex:
                return [f"<err {type(ex).__name__}>"]
        print("\nfoundation models:")
        print("  chat:      ", ids(fm.get_chat_model_specs))
        print("  embeddings:", ids(fm.get_embeddings_model_specs))
    else:
        print("\n(no space_id configured — run cpd_init.py to pick one; "
              "skipping deployment/model listing)")

    sp = client.spaces.get_details(limit=50).get("resources", [])
    print(f"\nspaces ({len(sp)}):", [s['entity']['name'] for s in sp])
    print("\nOK (read-only; nothing created).")


if __name__ == "__main__":
    main()
