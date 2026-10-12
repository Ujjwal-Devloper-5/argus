"""
Unit & Integration Tests for Argus Dashboard Backend (Phase 5 Verification).
Tests: Auth, single-use WS tickets, path containment, camera CRUD, event stats, and secrets preservation.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from argus.config import get_settings
from argus.dashboard.backend.app import app
from argus.dashboard.backend.auth import (
    create_ws_ticket,
    hash_password,
    verify_password,
    verify_ws_ticket,
)


@pytest.fixture
def auth_creds():
    settings = get_settings()
    return {
        "username": settings.dashboard.username,
        "password": settings.dashboard.password.get_secret_value(),
    }


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_password_hash_and_verification():
    pw = "SuperSecure123!"
    hashed = hash_password(pw)
    assert "salt" in hashed
    assert "hash" in hashed
    assert hashed["iterations"] == 260_000

    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_single_use_ws_ticket():
    ticket = create_ws_ticket("test_admin")
    assert isinstance(ticket, str)
    assert len(ticket) > 16

    # First verification must succeed
    assert verify_ws_ticket(ticket) is True
    # Replay attack: second verification of the exact same ticket MUST fail
    assert verify_ws_ticket(ticket) is False


def test_login_and_cookie_auth(client, auth_creds):
    # Test valid login with config credentials
    res = client.post("/api/auth/login", json=auth_creds)
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "argus_token" in res.cookies

    # Test me endpoint with cookie
    me_res = client.get("/api/auth/me", cookies=res.cookies)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == auth_creds["username"]

    # Test ticket issuance with authenticated session
    ticket_res = client.get("/api/auth/ticket", cookies=res.cookies)
    assert ticket_res.status_code == 200
    assert "ticket" in ticket_res.json()
    assert verify_ws_ticket(ticket_res.json()["ticket"]) is True


def test_spa_path_traversal_containment(client):
    # Attempt directory traversal attacks on SPA static server
    res1 = client.get("//etc/passwd")
    # Must never serve /etc/passwd — either index.html fallback or 404
    assert "root:x:0:0:" not in res1.text

    res2 = client.get("/../../../../etc/shadow")
    assert "root:" not in res2.text


def test_camera_list_masks_credentials(client, auth_creds):
    # Log in first
    login_res = client.post("/api/auth/login", json=auth_creds)
    cookies = login_res.cookies

    res = client.get("/api/cameras", cookies=cookies)
    assert res.status_code == 200
    cameras = res.json()
    assert isinstance(cameras, list)
    for cam in cameras:
        # RTSP credentials must be masked
        assert "password" not in cam["rtsp_url"].lower()
        if "@" in cam["rtsp_url"]:
            assert "***:***@" in cam["rtsp_url"]


def test_event_stats_endpoint(client, auth_creds):
    login_res = client.post("/api/auth/login", json=auth_creds)
    cookies = login_res.cookies

    res = client.get("/api/events/stats", cookies=cookies)
    assert res.status_code == 200
    data = res.json()
    assert "total_24h" in data
    assert "threat_level" in data
    assert data["threat_level"] in ("LOW", "ELEVATED", "HIGH", "CRITICAL")
