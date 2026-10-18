from dataclasses import dataclass

from fastapi import Depends, Header

from app.auth.jwt import JwtVerificationError, claims_to_user, verify_supabase_jwt
from app.core.config import get_settings
from app.core.errors import ProxyError


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None
    role: str = "user"


def _gateway_user(secret: str, gateway_secret: str | None, user: str | None, tenant: str | None, role: str | None) -> CurrentUser:
    """KAIROS INTEGRATION: trusted-gateway authentication.

    When KAIROS_GATEWAY_SECRET is set, the only accepted credential is the Kairos API gateway: a matching shared
    secret plus the identity Kairos already authenticated. Bearer tokens and the development bypass are refused,
    so this worker has no login of its own and cannot be reached around Kairos. Case ownership is namespaced by
    tenant so one site can never read another site's cases."""
    import secrets as _secrets

    if not gateway_secret or not _secrets.compare_digest(gateway_secret, secret):
        raise ProxyError("Gateway credential required", status_code=401, code="unauthorized")
    if not user or not tenant:
        raise ProxyError("Gateway identity headers missing", status_code=401, code="unauthorized")
    return CurrentUser(id=f"{tenant}:{user}", role="admin" if role == "admin" else "user")


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_kairos_gateway_secret: str | None = Header(default=None),
    x_kairos_user: str | None = Header(default=None),
    x_kairos_tenant: str | None = Header(default=None),
    x_kairos_role: str | None = Header(default=None),
) -> CurrentUser:
    import os as _os

    _secret = _os.environ.get("KAIROS_GATEWAY_SECRET", "")
    if _secret:
        # A direct (non-DI) call, e.g. from require_admin_or_api_key, leaves Header() defaults in place: treat as absent.
        def _s(value):
            return value if isinstance(value, str) else None
        return _gateway_user(_secret, _s(x_kairos_gateway_secret), _s(x_kairos_user), _s(x_kairos_tenant), _s(x_kairos_role))
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ProxyError("Missing bearer token", status_code=401, code="unauthorized")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise ProxyError("Invalid bearer token", status_code=401, code="unauthorized")

    settings = get_settings()
    if settings.environment == "development" and not settings.supabase_jwt_secret:
        return CurrentUser(id=token)

    try:
        claims = verify_supabase_jwt(token)
    except JwtVerificationError as exc:
        raise ProxyError(f"Invalid token: {exc}", status_code=401, code="unauthorized") from exc

    user = claims_to_user(claims)
    if not user["id"]:
        raise ProxyError("Token missing subject", status_code=401, code="unauthorized")
    return CurrentUser(id=user["id"], email=user.get("email"), role=user.get("role", "user"))


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise ProxyError("Admin permission required", status_code=403, code="forbidden")
    return user


async def require_admin_or_api_key(
    authorization: str | None = Header(default=None),
    x_admin_api_key: str | None = Header(default=None),
) -> CurrentUser:
    """Admin access via either a Supabase JWT with role=admin, or a static
    ADMIN_API_KEY header -- for service-to-service/CI callers that shouldn't
    need a user session (e.g. a scheduled reindex trigger, a CI health
    check). Only usable when ADMIN_API_KEY is actually configured."""
    settings = get_settings()
    if settings.admin_api_key and x_admin_api_key:
        import secrets
        if secrets.compare_digest(x_admin_api_key, settings.admin_api_key):
            return CurrentUser(id="service-api-key", role="admin")
        raise ProxyError("Invalid API key", status_code=401, code="unauthorized")
    return await require_admin(await get_current_user(authorization))
