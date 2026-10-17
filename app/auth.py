"""Verify Supabase Auth JWTs.

Supabase projects sign access tokens either with asymmetric keys (ES256/RS256,
published at /auth/v1/.well-known/jwks.json) or, on older projects, with a
shared HS256 secret. Both are supported: if SUPABASE_JWT_SECRET is set it is
used, otherwise the signing key is looked up in the project's JWKS.
"""

import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str | None
    claims: dict[str, Any] = field(repr=False)


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=600)


def get_jwks_client(settings: Settings) -> jwt.PyJWKClient:
    return _jwks_client(settings.jwks_url)


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    """Return the token's claims, or raise jwt.PyJWTError if it is invalid."""
    options = {"require": ["exp", "sub", "aud"]}
    issuer = settings.jwt_issuer if settings.supabase_url else None

    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=issuer,
            options=options,
        )

    if not settings.supabase_url:
        raise jwt.InvalidTokenError("Auth is not configured: set SUPABASE_URL")

    signing_key = get_jwks_client(settings).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=ASYMMETRIC_ALGORITHMS,
        audience=settings.jwt_audience,
        issuer=issuer,
        options=options,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None:
        raise _unauthorized("Missing bearer token")

    try:
        claims = decode_token(credentials.credentials, settings)
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid token") from exc

    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise _unauthorized("Invalid token subject") from exc

    return CurrentUser(id=user_id, email=claims.get("email"), claims=claims)
