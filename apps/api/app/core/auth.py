import jwt
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request

from app.config import settings, CLUSTER_INTOUCH_MAP, normalize_cluster_key

logger = logging.getLogger(__name__)

# Auth slug → Intouch base URL (derived from canonical config)
# Login uses lowercase slugs; CLUSTER_INTOUCH_MAP uses canonical CAPS keys.
CLUSTER_URLS = {
    "apac2":         CLUSTER_INTOUCH_MAP.get("APAC2", ""),
    "apac":          CLUSTER_INTOUCH_MAP.get("APAC", ""),
    "eu":            CLUSTER_INTOUCH_MAP.get("EU", ""),
    "north-america": CLUSTER_INTOUCH_MAP.get("US", ""),
    "tata":          CLUSTER_INTOUCH_MAP.get("TATA", ""),
    "ushc":          CLUSTER_INTOUCH_MAP.get("USHC", ""),
    "sea":           CLUSTER_INTOUCH_MAP.get("SEA", ""),
}


async def login_to_capillary(username: str, password: str, cluster: str) -> dict:
    """Authenticate against Capillary Intouch and return token + user info."""
    base_url = CLUSTER_URLS.get(cluster.lower())
    if not base_url:
        raise HTTPException(400, f"Unknown cluster: {cluster}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Login
        login_resp = await client.post(
            f"{base_url}/arya/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if login_resp.status_code != 200:
            raise HTTPException(401, "Invalid credentials")

        login_data = login_resp.json()
        if not login_data.get("success"):
            raise HTTPException(401, login_data.get("message", "Login failed"))

        cap_token = login_data["token"]

        # Step 2: Get user info
        user_resp = await client.get(
            f"{base_url}/arya/api/v1/auth/user",
            headers={"Authorization": f"Bearer {cap_token}"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(401, "Failed to fetch user info")

        user_data = user_resp.json()
        user_attrs = user_data.get("user", {}).get("attributes", {})
        proxy_org_list = user_data.get("user", {}).get("proxyOrgList", [])

        orgs = [
            {"id": org.get("orgID"), "name": org.get("orgName", f"Org {org.get('orgID')}")}
            for org in proxy_org_list
            if org.get("orgID")
        ]

        return {
            "capillary_token": cap_token,
            "email": user_attrs.get("email", username),
            "display_name": user_attrs.get("name", username),
            "cluster": cluster,
            "base_url": base_url,
            "orgs": orgs,
        }


def create_session_token(
    user_id: int,
    email: str,
    is_admin: bool,
    capillary_token: str,
    cluster: str,
    base_url: str,
) -> str:
    """Create a JWT session token for the application."""
    payload = {
        "user_id": user_id,
        "email": email,
        "is_admin": is_admin,
        "capillary_token": capillary_token,
        "cluster": cluster,
        "base_url": base_url,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=settings.jwt_algorithm)


def decode_session_token(token: str) -> dict:
    """Decode and validate a session JWT token."""
    try:
        return jwt.decode(token, settings.session_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session token")


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency to extract current user from JWT."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]
    return decode_session_token(token)


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency that requires admin access."""
    if not current_user.get("is_admin"):
        raise HTTPException(403, "Admin access required")
    return current_user
