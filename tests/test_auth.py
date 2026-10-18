import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.auth import decode_token
from app.config import Settings
from tests.conftest import SUPABASE_URL


def test_health_needs_no_auth(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_root_redirects_to_the_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
    assert client.get("/docs").status_code == 200


def test_docs_offer_bearer_auth_and_describe_every_tag(client):
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    described = {tag["name"] for tag in schema["tags"]}
    used = {tag for path in schema["paths"].values() for op in path.values() for tag in op["tags"]}
    assert used <= described


def test_missing_token_is_401(client):
    response = client.get("/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_valid_token_returns_teacher(client, auth_headers):
    user_id = uuid.uuid4()
    headers = auth_headers(
        user_id, email="ms.frizzle@example.edu", user_metadata={"name": "Frizzle"}
    )
    response = client.get("/me", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user_id),
        "name": "Frizzle",
        "email": "ms.frizzle@example.edu",
    }


@pytest.mark.parametrize(
    ("kwargs", "detail"),
    [
        ({"expires_in": -10}, "Token has expired"),
        ({"audience": "anon"}, "Invalid token"),
        ({"issuer": "https://evil.example.com/auth/v1"}, "Invalid token"),
        ({"secret": "some-other-secret-that-is-32-bytes!"}, "Invalid token"),
        ({"sub": "not-a-uuid"}, "Invalid token subject"),
    ],
)
def test_bad_tokens_are_401(client, make_token, kwargs, detail):
    sub = kwargs.pop("sub", None)
    token = make_token(sub, **kwargs)
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == detail


def test_garbage_token_is_401(client):
    response = client.get("/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401


def test_asymmetric_tokens_verified_with_jwks(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    settings = Settings(supabase_url=SUPABASE_URL, supabase_jwt_secret="")

    class FakeSigningKey:
        key = private_key.public_key()

    class FakeJWKSClient:
        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    monkeypatch.setattr("app.auth.get_jwks_client", lambda _settings: FakeJWKSClient())

    now = int(time.time())
    claims = {
        "sub": str(uuid.uuid4()),
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "exp": now + 60,
    }
    token = jwt.encode(claims, private_key, algorithm="ES256", headers={"kid": "k1"})
    assert decode_token(token, settings)["sub"] == claims["sub"]

    other_key = ec.generate_private_key(ec.SECP256R1())
    forged = jwt.encode(claims, other_key, algorithm="ES256", headers={"kid": "k1"})
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(forged, settings)


def test_hs256_token_rejected_when_only_jwks_configured(monkeypatch):
    """An attacker can't sign HS256 with a public key to bypass JWKS verification."""
    settings = Settings(supabase_url=SUPABASE_URL, supabase_jwt_secret="")

    class FakeSigningKey:
        key = ec.generate_private_key(ec.SECP256R1()).public_key()

    class FakeJWKSClient:
        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    monkeypatch.setattr("app.auth.get_jwks_client", lambda _settings: FakeJWKSClient())
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated", "exp": int(time.time()) + 60},
        "x" * 32,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_token(token, settings)


def test_cors_exposes_content_disposition(client):
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()
