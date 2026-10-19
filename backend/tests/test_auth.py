import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt import PyJWKClient

from app.main import create_app

ALLOWED_ORIGIN = "http://localhost:5173"
JWKS_URL = "https://test-project.example/auth/v1/.well-known/jwks.json"
ISSUER = "https://test-project.example/auth/v1"
AUDIENCE = "authenticated"
KEY_ID = "test-es256-key"


@pytest.fixture
def signing_keys() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePrivateKey]:
    return (
        ec.generate_private_key(ec.SECP256R1()),
        ec.generate_private_key(ec.SECP256R1()),
    )


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    signing_keys: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePrivateKey],
) -> Iterator[TestClient]:
    valid_private_key, _ = signing_keys
    public_jwk = json.loads(
        jwt.algorithms.ECAlgorithm.to_jwk(valid_private_key.public_key())
    )
    public_jwk.update({"kid": KEY_ID, "alg": "ES256", "use": "sig"})
    jwks = {"keys": [public_jwk]}

    monkeypatch.setenv("SUPABASE_JWKS_URL", JWKS_URL)
    monkeypatch.setenv("SUPABASE_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("ENABLE_AUTH_PROBE", "true")
    monkeypatch.setattr(PyJWKClient, "fetch_data", lambda self: jwks)

    with TestClient(create_app()) as test_client:
        yield test_client


def make_token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    subject: str | None = None,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_at: datetime | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject or str(uuid4()),
        "iat": now,
        "exp": expires_at or now + timedelta(minutes=5),
    }
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": KEY_ID},
    )


def assert_unauthorized(response) -> None:
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == {
        "code": "UNAUTHORIZED",
        "message": "Authentication is required.",
        "details": None,
    }
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN


def test_valid_token_returns_verified_user_id(
    client: TestClient,
    signing_keys: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePrivateKey],
) -> None:
    user_id = str(uuid4())
    token = make_token(signing_keys[0], subject=user_id)

    response = client.get(
        "/api/v1/auth/probe",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "user_id": user_id}
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert response.headers["X-Request-ID"]


def test_missing_token_returns_401(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/probe", headers={"Origin": ALLOWED_ORIGIN}
    )

    assert_unauthorized(response)


@pytest.mark.parametrize(
    "authorization",
    ["Basic abc", "Bearer", "Bearer not-a-jwt"],
)
def test_malformed_token_returns_401(
    client: TestClient, authorization: str
) -> None:
    response = client.get(
        "/api/v1/auth/probe",
        headers={"Origin": ALLOWED_ORIGIN, "Authorization": authorization},
    )

    assert_unauthorized(response)


def test_expired_token_returns_401(
    client: TestClient,
    signing_keys: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePrivateKey],
) -> None:
    token = make_token(
        signing_keys[0], expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    response = client.get(
        "/api/v1/auth/probe",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Authorization": f"Bearer {token}",
        },
    )

    assert_unauthorized(response)


def test_invalid_signature_returns_401(
    client: TestClient,
    signing_keys: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePrivateKey],
) -> None:
    token = make_token(signing_keys[1])

    response = client.get(
        "/api/v1/auth/probe",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Authorization": f"Bearer {token}",
        },
    )

    assert_unauthorized(response)


@pytest.mark.parametrize(
    ("issuer", "audience"),
    [("https://wrong-issuer.example", AUDIENCE), (ISSUER, "wrong-audience")],
)
def test_wrong_issuer_or_audience_returns_401(
    client: TestClient,
    signing_keys: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePrivateKey],
    issuer: str,
    audience: str,
) -> None:
    token = make_token(signing_keys[0], issuer=issuer, audience=audience)

    response = client.get(
        "/api/v1/auth/probe",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Authorization": f"Bearer {token}",
        },
    )

    assert_unauthorized(response)


def test_probe_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_AUTH_PROBE", raising=False)

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/auth/probe")

    assert response.status_code == 404
