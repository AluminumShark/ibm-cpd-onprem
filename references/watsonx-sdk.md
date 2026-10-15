# ibm_watsonx_ai Python SDK path (watsonx.ai + WML)

Package `ibm_watsonx_ai` (verified with v1.3.39). It connects to a CPD cluster and
manages watsonx.ai + Watson Machine Learning: models, deployments, specs, prompt
templates, training. `wx_connect.py` (`python "$S/scripts/wx_connect.py"`) wires
this to the shared config and prints a read-only inventory; the patterns below
are what it uses.

Code below assumes `S` (shell) / `SKILL_DIR` (Python) holds this skill's base
directory (see SKILL.md); the working directory is usually the user's project.

## Connection (the robust form)
```python
import os, sys, urllib3; urllib3.disable_warnings()
SKILL_DIR = r"<this skill's base directory>"   # the same path as $S
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
import cpd_config as C
from ibm_watsonx_ai import APIClient, Credentials

creds = Credentials(
    url=C.get("url"),
    username=C.get("username"),
    api_key=C.get("api_key"),
    instance_id="openshift",          # required string for CPD
    version="5.2",                    # see version pitfall below
    verify=C.get("verify_ssl"),      # False for self-signed
)
client = APIClient(creds)
```

### Product-version pitfall (portability)
The SDK validates `version` against a built-in list. A cluster **newer** than the
SDK (e.g. backend 5.3 with an SDK that tops out at 5.2) raises
`WMLClientError: The product version 5.3 is not supported`, even though the REST
APIs are identical. `wx_connect.py` handles this by introspecting
`CPDVersion.supported_version_list` and falling back to the highest supported
value. If you hard-code it, use the SDK's max supported version, not the literal
backend version. All SDK routing keys off `>=5.1` thresholds, so any 5.x behaves
the same.

## Set a default scope BEFORE catalog calls
```python
client.set.default_space(C.get("space_id"))      # or .default_project(C.get("project_id"))
```
`foundation_models.*`, `software_specifications.*`, `hardware_specifications.*`
all raise "You must set the space/project id" until a default scope is set.

## Read-only inventory (methods confirmed working)
```python
fm = client.foundation_models
# Foundation models are exposed PER CAPABILITY — the generic text-gen list can be empty.
fm.get_chat_model_specs()                  # chat models
fm.get_embeddings_model_specs()            # embedding models
# also: get_chat_function_calling_model_specs(), get_rerank_model_specs(), get_model_specs()

client.software_specifications.list()       # -> pandas DataFrame
client.hardware_specifications.list()

client.deployments.get_details()            # all deployments in the space (dict)
client.deployments.get_details("<deployment_id>")

client.repository.list()                    # stored models/assets
client.training.get_details(limit=50)       # training jobs

client.spaces.get_details(limit=50)
client.projects.list()
client.connections.list()
client.data_assets.list()

# Prompt templates (switch to a project first)
client.set.default_project(C.get("project_id"))
from ibm_watsonx_ai.foundation_models.prompts import PromptTemplateManager
PromptTemplateManager(api_client=client).list()
```
`.list()` methods often PRINT a table and return `None`; prefer the
`get_details()` variants when you need to parse results in code.

## Inference via the SDK (alternative to raw REST)
```python
from ibm_watsonx_ai.foundation_models import ModelInference
client.set.default_space(C.get("space_id"))
model = ModelInference(deployment_id=C.get("deployment_id"), api_client=client)
resp = model.chat(messages=[{"role":"user","content":"Introduce yourself in one sentence."}])
print(resp["choices"][0]["message"]["content"])
```

## Running on Windows
Always `export PYTHONIOENCODING=utf-8 PYTHONUTF8=1` (PowerShell:
`$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"`) before running — model specs
and names can contain CJK/emoji that crash a non-UTF-8 console. See gotchas.md.
