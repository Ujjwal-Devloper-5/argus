"""
HTTP Basic Auth middleware for Argus dashboard.
Credentials come from DashboardConfig (username + password).
"""
import secrets
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

logger = structlog.get_logger(__name__)
security = HTTPBasic()


def get_auth_dependency(settings):
    """Factory that returns a FastAPI dependency using settings credentials."""
    def verify_credentials(credentials: Annotated[HTTPBasicCredentials, Depends(security)]) -> str:
        correct_username = secrets.compare_digest(
            credentials.username.encode("utf8"),
            settings.dashboard.username.encode("utf8"),
        )
        correct_password = secrets.compare_digest(
            credentials.password.encode("utf8"),
            settings.dashboard.password.get_secret_value().encode("utf8"),
        )
        if not (correct_username and correct_password):
            logger.warning("Dashboard auth failed", username=credentials.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username
    return verify_credentials
