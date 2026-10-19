import os
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import (
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from app.auth.exceptions import AuthenticationError

bearer_scheme = HTTPBearer(auto_error=False)
ALLOWED_ALGORITHMS = ["ES256", "RS256"]


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_jwk_set=True, timeout=5)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()

    token = credentials.credentials.strip()
    if not token:
        raise AuthenticationError()

    jwks_url = os.getenv("SUPABASE_JWKS_URL", "").strip()
    issuer = os.getenv("SUPABASE_JWT_ISSUER", "").strip()
    audience = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated").strip()
    if not jwks_url or not issuer or not audience:
        raise RuntimeError("Supabase JWT verification is not configured.")

    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=ALLOWED_ALGORITHMS,
            issuer=issuer,
            audience=audience,
            options={"require": ["iss", "aud", "exp", "sub"]},
        )
        return str(UUID(claims["sub"]))
    except PyJWKClientConnectionError:
        # A JWKS outage is an operational failure, not evidence of a bad token.
        # Let the common handler return its sanitized INTERNAL_ERROR envelope.
        raise
    except (InvalidTokenError, PyJWKClientError, ValueError, TypeError, KeyError):
        raise AuthenticationError() from None
