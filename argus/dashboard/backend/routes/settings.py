"""
Settings API — read and update Argus configuration.
"""
import os

import yaml
from fastapi import APIRouter, Depends

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import SettingsResponse

settings = get_settings()
router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_auth_dependency(settings))])

@router.get("", response_model=SettingsResponse)
async def get_current_settings():
    def mask_secrets(d):
        if not isinstance(d, dict):
            return d
        res = {}
        for k, v in d.items():
            if 'token' in k.lower() or 'password' in k.lower() or 'secret' in k.lower() or 'api_key' in k.lower():
                res[k] = "********" if v else None
            elif isinstance(v, dict):
                res[k] = mask_secrets(v)
            elif isinstance(v, list):
                res[k] = [mask_secrets(i) if isinstance(i, dict) else i for i in v]
            elif hasattr(v, 'get_secret_value'):
                res[k] = "********"
            else:
                res[k] = v
        return res

    dump = settings.model_dump()
    return SettingsResponse(
        cameras=mask_secrets(dump.get('cameras', [])),
        detection=mask_secrets(dump.get('detection', {})),
        llm=mask_secrets(dump.get('llm', {})),
        alerts=mask_secrets(dump.get('alerts', {})),
        kafka=mask_secrets(dump.get('kafka', {})),
        storage=mask_secrets(dump.get('storage', {}))
    )

@router.put("")
async def update_settings(updates: dict):
    # Only allow safe fields (implementation is basic for this example)
    allowed_keys = {'cameras', 'detection', 'llm', 'alerts', 'storage'}

    config_path = "config/config.yaml"
    if os.path.exists(config_path):
        with open(config_path) as f:
            current_config = yaml.safe_load(f) or {}
    else:
        current_config = {}

    for k, v in updates.items():
        if k in allowed_keys:
            if isinstance(v, dict) and k in current_config and isinstance(current_config[k], dict):
                current_config[k].update(v)
            else:
                current_config[k] = v

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        yaml.safe_dump(current_config, f)

    return {"success": True, "message": "Settings updated"}
