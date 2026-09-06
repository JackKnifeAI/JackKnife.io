from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone

CLIENTS_ROOT = Path(__file__).resolve().parents[1] / "clients"

def ensure_workspace(profile_id:str, email:str=""):
    base=CLIENTS_ROOT/profile_id
    for name in ("evidence","blueprints","manifests","integrations","uploads","audit"):
        (base/name).mkdir(parents=True, exist_ok=True)
    meta=base/"profile.json"
    if not meta.exists():
        meta.write_text(json.dumps({
            "profile_id":profile_id, "email":email, "created_at":datetime.now(timezone.utc).isoformat(),
            "workspace_version":1, "status":"PROFILE_CREATED"
        }, indent=2))
    return base

def write_json(profile_id:str, relative:str, obj):
    base=ensure_workspace(profile_id)
    p=base/relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True))
    return str(p)
