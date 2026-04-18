"""
Supabase JWT validator — validates access tokens from Supabase Auth.

HOW IT WORKS:
  1. Frontend authenticates with Supabase (email/password or Google OAuth)
  2. Supabase returns a signed JWT
  3. Frontend sends JWT in `Authorization: Bearer <token>` header
  4. This middleware validates the JWT using the Supabase JWT secret
  5. Extracts user_id, email, plan from the JWT claims

FAST PATH:
  JWT validation is pure CPU (no network calls) — under 1ms.
  No database query needed for each request.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
JWT_ALGORITHMS      = ["HS256"]


@dataclass
class AuthenticatedUser:
    """Represents a validated user from a Supabase JWT."""
    user_id:    str
    email:      str
    tenant_id:  str
    plan:       str           # "free" | "pro" | "enterprise"
    role:       str           # "user" | "admin"
    exp:        datetime
    raw_claims: dict

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _decode_jwt(token: str) -> dict:
    """Decode and validate a Supabase JWT."""
    try:
        from jose import jwt, JWTError, ExpiredSignatureError

        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=JWT_ALGORITHMS,
            options={"verify_aud": False},   # Supabase doesn't set aud consistently
        )
        return payload

    except Exception as e:
        # Import error means jose not installed
        if "jose" in str(type(e).__module__):
            raise
        logger.error(f"JWT library not available: {e}")
        raise HTTPException(status_code=500, detail="Auth dependencies not configured")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency: validate JWT and return AuthenticatedUser.

    Usage in routes:
        @router.get("/protected")
        async def protected(user: AuthenticatedUser = Depends(get_current_user)):
            return {"hello": user.email}
    """
    if not SUPABASE_JWT_SECRET:
        # Auth not configured — return anonymous user for development
        logger.warning("SUPABASE_JWT_SECRET not set — allowing anonymous access")
        return AuthenticatedUser(
            user_id="anonymous",
            email="dev@localhost",
            tenant_id="dev-tenant",
            plan="pro",
            role="admin",
            exp=datetime(2099, 12, 31, tzinfo=timezone.utc),
            raw_claims={},
        )

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = _decode_jwt(credentials.credentials)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Extract claims
    user_id   = payload.get("sub", "")
    email     = payload.get("email", "")
    tenant_id = payload.get("user_metadata", {}).get("tenant_id", user_id)
    plan      = payload.get("user_metadata", {}).get("plan", "free")
    role      = payload.get("role", "authenticated")
    exp       = datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc)

    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user ID (sub)")

    # Map Supabase role to app role
    app_role = "admin" if role in ("service_role", "supabase_admin") else "user"

    return AuthenticatedUser(
        user_id=user_id,
        email=email,
        tenant_id=tenant_id,
        plan=plan,
        role=app_role,
        exp=exp,
        raw_claims=payload,
    )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[AuthenticatedUser]:
    """
    Same as get_current_user, but returns None instead of 401 if no token.
    For endpoints that work with or without auth (e.g., public health check).
    """
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """FastAPI dependency: require admin role."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
