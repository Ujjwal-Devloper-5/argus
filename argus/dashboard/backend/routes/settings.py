"""
Settings API — read and update Argus configuration.
"""
import os

import yaml
from fastapi import APIRouter, Depends

from argus.config import get_settings
from argus.dashboard.backend.auth import get_auth_dependency
from argus.dashboard.backend.models import SettingsResponse

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_auth_dependency())])


def _preserve_secret(new_val, current_secret):
    """Retain existing secret if new value is empty, None, or masked."""
    if not new_val or str(new_val) in ("********", ""):
        if hasattr(current_secret, 'get_secret_value'):
            return current_secret.get_secret_value()
        return current_secret
    return new_val


def _is_secret_field(name: str) -> bool:
    name_lower = str(name).lower()
    return any(term in name_lower for term in ('token', 'password', 'secret', 'api_key'))


def _apply_secrets_preservation(target_dict: dict, updates_dict: dict, current_section_obj=None):
    for k, v in updates_dict.items():
        attr_obj = getattr(current_section_obj, k, None) if current_section_obj else None
        if isinstance(v, dict):
            if k not in target_dict or not isinstance(target_dict[k], dict):
                target_dict[k] = {}
            _apply_secrets_preservation(target_dict[k], v, attr_obj)
        elif isinstance(v, list):
            target_list = target_dict.get(k, [])
            new_list = []
            for idx, item in enumerate(v):
                if isinstance(item, dict):
                    curr_item = target_list[idx] if isinstance(target_list, list) and idx < len(target_list) and isinstance(target_list[idx], dict) else {}
                    item_copy = dict(item)
                    for ik, iv in item.items():
                        if _is_secret_field(ik):
                            item_copy[ik] = _preserve_secret(iv, curr_item.get(ik))
                    new_list.append(item_copy)
                else:
                    new_list.append(item)
            target_dict[k] = new_list
        else:
            if _is_secret_field(k):
                current_secret = target_dict.get(k)
                if current_secret is None and attr_obj is not None:
                    current_secret = attr_obj
                target_dict[k] = _preserve_secret(v, current_secret)
            else:
                target_dict[k] = v


@router.get("", response_model=SettingsResponse)
async def get_current_settings():
    settings = get_settings()

    def mask_secrets(d):
        if not isinstance(d, dict):
            return d
        res = {}
        for k, v in d.items():
            if _is_secret_field(k):
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

    active_settings = get_settings()

    for k, v in updates.items():
        if k in allowed_keys:
            current_section = getattr(active_settings, k, None)
            if isinstance(v, dict):
                if k not in current_config or not isinstance(current_config[k], dict):
                    current_config[k] = {}
                _apply_secrets_preservation(current_config[k], v, current_section)
            elif isinstance(v, list):
                _apply_secrets_preservation(current_config, {k: v}, active_settings)
            else:
                if _is_secret_field(k):
                    current_config[k] = _preserve_secret(v, current_config.get(k) or current_section)
                else:
                    current_config[k] = v

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        yaml.safe_dump(current_config, f)

    get_settings.cache_clear()

    return {"success": True, "message": "Settings updated"}
