"""
Argus Dashboard — Hardened JWT Authentication with single-use nonce WebSocket tickets.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Dict, Tuple

import jwt
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.security import HTTPBasicCredentials
from pydantic import BaseModel

from argus.config import get_settings

# Persist JWT secret across restarts
_SECRET_FILE = Path("data/.jwt_secret")

def _load_or_create_secret() -> str:
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_text().strip()
    secret = secrets.token_hex(32)
    _SECRET_FILE.write_text(secret)
    return secret

JWT_SECRET = os.environ.get("ARGUS_JWT_SECRET") or _load_or_create_secret()
ALGORITHM = "HS256"

# Single-use nonce store: nonce -> (username, expiry_timestamp)
_TICKET_STORE: Dict[str, Tuple[str, float]] = {}


def _purge_expired_tickets() -> None:
    now = time.time()
    expired = [k for k, (_, exp) in _TICKET_STORE.items() if exp < now]
    for k in expired:
        _TICKET_STORE.pop(k, None)


def hash_password(password: str) -> dict:
    """PBKDF2-HMAC-SHA256 with 260,000 iterations."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 260_000)
    return {"salt": salt, "hash": dk.hex(), "iterations": 260_000}


def verify_password(password: str, stored: dict) -> bool:
    """Constant-time PBKDF2 verification."""
    try:
        salt = bytes.fromhex(stored["salt"])
        iterations = stored.get("iterations", 260_000)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return secrets.compare_digest(dk.hex(), stored["hash"])
    except (KeyError, ValueError):
        return False


def _load_users() -> dict:
    users_file = Path("data/.dashboard_users.json")
    if users_file.exists():
        with open(users_file) as f:
            return json.load(f)
    return {}


def _verify_any(username: str, password: str) -> bool:
    """Tries file-based users first, then config.yaml fallback."""
    users = _load_users()
    if username in users:
        return verify_password(password, users[username])
    # Config fallback
    try:
        settings = get_settings()
        return (
            username == settings.dashboard.username
            and secrets.compare_digest(password, settings.dashboard.password.get_secret_value())
        )
    except Exception:
        return False


def create_ws_ticket(username: str) -> str:
    """Create a single-use 30-second nonce for WebSocket authentication."""
    _purge_expired_tickets()
    nonce = secrets.token_urlsafe(32)
    _TICKET_STORE[nonce] = (username, time.time() + 30.0)
    return nonce


def verify_ws_ticket(ticket: str) -> bool:
    """Consume and verify a single-use WebSocket nonce."""
    _purge_expired_tickets()
    if not ticket or ticket not in _TICKET_STORE:
        return False
    _, expiry = _TICKET_STORE.pop(ticket)
    return time.time() <= expiry


class LoginRequest(BaseModel):
    username: str
    password: str


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(req: LoginRequest, response: Response):
    if not _verify_any(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    payload = {"sub": req.username, "exp": time.time() + 24 * 3600}
    token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
    response.set_cookie(
        key="argus_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=24 * 3600,
    )
    return {"success": True, "username": req.username}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("argus_token")
    return {"success": True}


@router.get("/ticket")
async def get_ws_ticket(request: Request):
    username = _get_username_from_request(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"ticket": create_ws_ticket(username)}


@router.get("/me")
async def get_me(request: Request):
    username = _get_username_from_request(request)
    if not username:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"username": username}


def _get_username_from_request(request: Request) -> str | None:
    token = request.cookies.get("argus_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.PyJWTError:
        return None


def get_auth_dependency():
    """FastAPI dependency for protected routes. Call as Depends(get_auth_dependency())."""
    def dependency(request: Request) -> str:
        username = _get_username_from_request(request)
        if not username:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return username
    return dependency
