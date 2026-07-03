from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status

try:
    import jwt
except ImportError:  # pragma: no cover - local fallback for minimal dev installs.
    jwt = None

from app.repositories.user_repository import get_or_create_dev_user, get_user_by_id


JWT_ALGORITHM = "HS256"
PASSWORD_HASH_ITERATIONS = 260_000


def get_jwt_secret_key() -> str:
    # TODO: Set JWT_SECRET_KEY in production; the fallback is for local dev only.
    return os.getenv("JWT_SECRET_KEY") or "dev-only-jwt-secret-change-me"


def get_access_token_expire_minutes() -> int:
    raw_value = os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
    if not raw_value:
        return 60 * 24 * 7
    try:
        return int(raw_value)
    except ValueError:
        return 60 * 24 * 7


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations, salt, expected_digest = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def create_access_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=get_access_token_expire_minutes())
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if jwt is not None:
        return jwt.encode(payload, get_jwt_secret_key(), algorithm=JWT_ALGORITHM)
    return encode_hs256_token(payload)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        if jwt is not None:
            return jwt.decode(
                token,
                get_jwt_secret_key(),
                algorithms=[JWT_ALGORITHM],
            )
        return decode_hs256_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user_optional_or_dev(request: Request) -> dict[str, Any]:
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        return get_or_create_dev_user()
    token = extract_bearer_token(authorization)
    payload = decode_access_token(token)
    user = get_user_by_id(int(payload.get("sub", 0)))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_required(request: Request) -> dict[str, Any]:
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = extract_bearer_token(authorization)
    payload = decode_access_token(token)
    user = get_user_by_id(int(payload.get("sub", 0)))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_dev() -> dict[str, Any]:
    return get_or_create_dev_user()


def extract_bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


def encode_hs256_token(payload: dict[str, Any]) -> str:
    header = {"typ": "JWT", "alg": JWT_ALGORITHM}
    header_segment = base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_segment = base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_segment}.{payload_segment}".encode()
    signature = hmac.new(
        get_jwt_secret_key().encode(),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_segment}.{payload_segment}.{base64url_encode(signature)}"


def decode_hs256_token(token: str) -> dict[str, Any]:
    header_segment, payload_segment, signature_segment = token.split(".", 2)
    signing_input = f"{header_segment}.{payload_segment}".encode()
    expected_signature = hmac.new(
        get_jwt_secret_key().encode(),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual_signature = base64url_decode(signature_segment)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("invalid signature")
    payload = json.loads(base64url_decode(payload_segment))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("token expired")
    return payload


def base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
