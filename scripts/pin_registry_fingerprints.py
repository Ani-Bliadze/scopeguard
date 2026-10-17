"""ADMIN ACTION: re-pin trusted schema fingerprints in config/tool_registry.json after a reviewed schema change."""

import json

from backend.settings import CONFIG_DIR
from backend.tool_schemas import schema_fingerprint

path = CONFIG_DIR / "tool_registry.json"
reg = json.loads(path.read_text(encoding="utf-8"))
for tool in reg["tools"]:
    tool["schema_sha256"] = schema_fingerprint(tool["tool_id"])
path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
print("pinned", len(reg["tools"]), "tool schema fingerprints")
