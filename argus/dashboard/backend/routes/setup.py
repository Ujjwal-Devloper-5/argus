"""
Argus Dashboard — First-Run Setup Wizard API.

Handles:
  - GET  /api/setup/status   — check if setup is needed
  - POST /api/setup/complete  — write config.yaml + .env from wizard form
  - GET  /api/setup/users    — check if a dashboard user exists
  - POST /api/setup/users    — create/update dashboard user credentials
  - POST /api/setup/test     — test a single connection (DB, Telegram, etc.)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

import structlog
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, SecretStr

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/setup", tags=["setup"])

# Paths (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[5]  # ~/homelab/argus/
_CONFIG_YAML = _PROJECT_ROOT / "config" / "config.yaml"
_ENV_FILE = _PROJECT_ROOT / ".env"
_USERS_FILE = _PROJECT_ROOT / "data" / ".dashboard_users.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config_exists() -> bool:
    """Return True if a real (non-example) config.yaml exists with at least one camera."""
    if not _CONFIG_YAML.exists():
        return False
    try:
        data = yaml.safe_load(_CONFIG_YAML.read_text()) or {}
        cameras = data.get("cameras", [])
        return bool(cameras)
    except Exception:
        return False


def _user_exists() -> bool:
    """Return True if at least one dashboard user has been created."""
    if not _USERS_FILE.exists():
        return False
    try:
        users = json.loads(_USERS_FILE.read_text())
        return bool(users)
    except Exception:
        return False


def _hash_password(password: str) -> str:
    """Securely hash a dashboard password using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"pbkdf2:sha256:260000:{salt}:{dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        _, algo, iterations, salt, dk_hex = stored.split(":")
        dk = hashlib.pbkdf2_hmac(
            algo.split("-")[-1] if "-" in algo else algo.split(":")[-1],
            password.encode(), salt.encode(), int(iterations),
        )
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SetupStatus(BaseModel):
    needs_setup: bool          # True → wizard required (no config/cameras)
    needs_user: bool           # True → user creation required
    config_exists: bool
    user_exists: bool
    project_root: str


class CameraSetup(BaseModel):
    name: str
    rtsp_url: str
    fps: int = 15
    post_event_seconds: int = 30


class LLMSetup(BaseModel):
    provider: str = "ollama"
    model: str = "llava"
    ollama_host: str = "http://localhost:11434"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    laya_enabled: bool = True
    laya_model: str = "convaiinnovations/laya-typed-decisions"


class AlertsSetup(BaseModel):
    routing: str = "telegram"
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_enabled: bool = False
    discord_bot_token: str | None = None
    discord_channel_id: str | None = None


class StorageSetup(BaseModel):
    backend: str = "local"
    local_path: str = "./data/clips"
    rclone_remote: str | None = None
    rclone_path: str | None = None
    retention_days: int = 30


class KafkaSetup(BaseModel):
    enabled: bool = False
    bootstrap_servers: str = "localhost:9092"


class SetupPayload(BaseModel):
    """Full wizard submission payload."""
    cameras: list[CameraSetup]
    database_url: str = "sqlite+aiosqlite:///./data/argus.db"
    llm: LLMSetup = LLMSetup()
    alerts: AlertsSetup = AlertsSetup()
    storage: StorageSetup = StorageSetup()
    kafka: KafkaSetup = KafkaSetup()
    # Dashboard credentials
    dashboard_username: str = "admin"
    dashboard_password: str


class CreateUserPayload(BaseModel):
    username: str
    password: str
    confirm_password: str


class TestConnectionPayload(BaseModel):
    type: str   # "database" | "telegram" | "discord" | "ollama" | "kafka"
    params: dict[str, Any] = {}


class SetupResponse(BaseModel):
    success: bool
    message: str
    details: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status", response_model=SetupStatus)
async def setup_status() -> SetupStatus:
    """Check whether the first-run setup wizard needs to run."""
    cfg = _config_exists()
    usr = _user_exists()
    return SetupStatus(
        needs_setup=not cfg,
        needs_user=not usr,
        config_exists=cfg,
        user_exists=usr,
        project_root=str(_PROJECT_ROOT),
    )


@router.post("/complete", response_model=SetupResponse)
async def complete_setup(payload: SetupPayload) -> SetupResponse:
    """
    Write config.yaml, .env, and dashboard user from wizard form data.
    Called once on first run.
    """
    if _config_exists() and _user_exists():
        raise HTTPException(400, "Setup already completed. Use settings API to change config.")

    try:
        # ----------------------------------------------------------------
        # 1. Build config.yaml structure
        # ----------------------------------------------------------------
        config: dict[str, Any] = {
            "cameras": [
                {
                    "name": cam.name,
                    "rtsp_url": cam.rtsp_url,
                    "fps": cam.fps,
                    "post_event_seconds": cam.post_event_seconds,
                }
                for cam in payload.cameras
            ],
            "detection": {"enabled": True, "confidence": 0.5},
            "recognition": {"enabled": True, "similarity_threshold": 0.45},
            "llm": {
                "provider": payload.llm.provider,
                "model": payload.llm.model,
                "ollama_host": payload.llm.ollama_host,
                "laya_enabled": payload.llm.laya_enabled,
                "laya_model": payload.llm.laya_model,
            },
            "alerts": {
                "routing": payload.alerts.routing,
                "telegram": {
                    "enabled": payload.alerts.telegram_enabled,
                    "chat_id": payload.alerts.telegram_chat_id or "",
                },
                "discord": {
                    "enabled": payload.alerts.discord_enabled,
                    "channel_id": payload.alerts.discord_channel_id or "",
                },
                "quiet_hours": {"enabled": False},
            },
            "storage": {
                "backend": payload.storage.backend,
                "local_path": payload.storage.local_path,
                "retention_days": payload.storage.retention_days,
                "rclone_remote": payload.storage.rclone_remote or "",
                "rclone_path": payload.storage.rclone_path or "",
            },
            "kafka": {
                "enabled": payload.kafka.enabled,
                "bootstrap_servers": payload.kafka.bootstrap_servers,
            },
            "dashboard": {
                "username": payload.dashboard_username,
                "password": payload.dashboard_password,
            },
        }

        # ----------------------------------------------------------------
        # 2. Write config.yaml
        # ----------------------------------------------------------------
        _CONFIG_YAML.parent.mkdir(parents=True, exist_ok=True)
        with _CONFIG_YAML.open("w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        logger.info("Setup wizard wrote config.yaml", path=str(_CONFIG_YAML))

        # ----------------------------------------------------------------
        # 3. Write secrets to .env (never stored in YAML)
        # ----------------------------------------------------------------
        env_lines = [
            f"DATABASE_URL={payload.database_url}",
        ]
        if payload.llm.openai_api_key:
            env_lines.append(f"OPENAI_API_KEY={payload.llm.openai_api_key}")
        if payload.llm.anthropic_api_key:
            env_lines.append(f"ANTHROPIC_API_KEY={payload.llm.anthropic_api_key}")
        if payload.llm.google_api_key:
            env_lines.append(f"GOOGLE_API_KEY={payload.llm.google_api_key}")
        if payload.alerts.telegram_bot_token:
            env_lines.append(f"TELEGRAM_BOT_TOKEN={payload.alerts.telegram_bot_token}")
        if payload.alerts.discord_bot_token:
            env_lines.append(f"DISCORD_BOT_TOKEN={payload.alerts.discord_bot_token}")
        if payload.kafka.enabled:
            env_lines.append(f"KAFKA_BOOTSTRAP_SERVERS={payload.kafka.bootstrap_servers}")

        _ENV_FILE.write_text("\n".join(env_lines) + "\n")
        logger.info("Setup wizard wrote .env", path=str(_ENV_FILE))

        # ----------------------------------------------------------------
        # 4. Create dashboard user
        # ----------------------------------------------------------------
        _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        users = {
            payload.dashboard_username: {
                "password_hash": _hash_password(payload.dashboard_password),
                "role": "admin",
            }
        }
        _USERS_FILE.write_text(json.dumps(users, indent=2))
        logger.info("Setup wizard created dashboard user", username=payload.dashboard_username)

        return SetupResponse(
            success=True,
            message="Setup complete! Restart Argus to apply configuration.",
            details={"cameras_configured": len(payload.cameras), "config_path": str(_CONFIG_YAML)},
        )

    except Exception as e:
        logger.error("Setup wizard failed", error=str(e))
        raise HTTPException(500, f"Setup failed: {e}") from e


@router.get("/users/check")
async def check_users() -> dict[str, bool]:
    """Quick check: has at least one dashboard user been created?"""
    return {"user_exists": _user_exists()}


@router.post("/users", response_model=SetupResponse)
async def create_user(payload: CreateUserPayload) -> SetupResponse:
    """
    Create the initial dashboard admin user.
    Blocked if a user already exists (must use settings to change password).
    """
    if _user_exists():
        raise HTTPException(400, "A dashboard user already exists. Use Settings to change password.")

    if payload.password != payload.confirm_password:
        raise HTTPException(422, "Passwords do not match.")

    if len(payload.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters.")

    try:
        _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        users = {
            payload.username: {
                "password_hash": _hash_password(payload.password),
                "role": "admin",
            }
        }
        _USERS_FILE.write_text(json.dumps(users, indent=2))
        logger.info("Dashboard user created", username=payload.username)
        return SetupResponse(success=True, message=f"User '{payload.username}' created successfully.")
    except Exception as e:
        raise HTTPException(500, f"Failed to create user: {e}") from e


@router.post("/test", response_model=SetupResponse)
async def test_connection(payload: TestConnectionPayload) -> SetupResponse:
    """Test a single connection (Telegram bot, database URL, Ollama, etc.)."""
    kind = payload.type
    params = payload.params

    if kind == "database":
        url = params.get("url", "")
        if not url:
            raise HTTPException(422, "database_url is required")
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            engine = create_async_engine(url, echo=False)
            async with engine.connect() as conn:
                from sqlalchemy import text
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            return SetupResponse(success=True, message="Database connection successful.")
        except Exception as e:
            return SetupResponse(success=False, message=f"Database connection failed: {e}")

    if kind == "ollama":
        host = params.get("host", "http://localhost:11434")
        try:
            import urllib.request
            with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
                data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return SetupResponse(success=True, message=f"Ollama reachable. Models: {', '.join(models[:5]) or 'none'}")
        except Exception as e:
            return SetupResponse(success=False, message=f"Ollama unreachable: {e}")

    if kind == "telegram":
        token = params.get("bot_token", "")
        if not token:
            raise HTTPException(422, "bot_token is required")
        try:
            import urllib.request
            url = f"https://api.telegram.org/bot{token}/getMe"
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read())
            username = data.get("result", {}).get("username", "unknown")
            return SetupResponse(success=True, message=f"Telegram bot validated: @{username}")
        except Exception as e:
            return SetupResponse(success=False, message=f"Telegram validation failed: {e}")

    if kind == "kafka":
        servers = params.get("bootstrap_servers", "localhost:9092")
        try:
            from aiokafka.admin import AIOKafkaAdminClient
            admin = AIOKafkaAdminClient(bootstrap_servers=servers)
            await admin.start()
            await admin.close()
            return SetupResponse(success=True, message=f"Kafka reachable at {servers}")
        except Exception as e:
            return SetupResponse(success=False, message=f"Kafka unreachable: {e}")

    raise HTTPException(422, f"Unknown test type: {kind}. Use: database, ollama, telegram, kafka")
