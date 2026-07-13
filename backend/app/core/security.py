import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings


class TokenError(ValueError):
    """访问令牌格式、签名或声明无效。"""


class TokenExpiredError(TokenError):
    """访问令牌已过期。"""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$%s$%s" % (_encode(salt), _encode(derived))


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, n, r, p, encoded_salt, encoded_hash = password_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = _decode(encoded_salt)
        expected = _decode(encoded_hash)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def create_access_token(
    user_id: str,
    username: str,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded_header = _encode_json(header)
    encoded_payload = _encode_json(payload)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_encode(signature)}"


def decode_access_token(token: str) -> dict[str, object]:
    settings = get_settings()
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        header = _decode_json(encoded_header)
        payload = _decode_json(encoded_payload)
        signature = _decode(encoded_signature)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError("Invalid token") from exc

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise TokenError("Invalid token")
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise TokenError("Invalid token")

    user_id = payload.get("sub")
    username = payload.get("username")
    expires_at = payload.get("exp")
    if not isinstance(user_id, str) or not isinstance(username, str) or not isinstance(expires_at, int):
        raise TokenError("Invalid token")
    if expires_at <= int(datetime.now(timezone.utc).timestamp()):
        raise TokenExpiredError("Token has expired")
    return payload


def _encode_json(value: dict[str, object]) -> str:
    return _encode(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _decode_json(value: str) -> dict[str, object]:
    decoded = json.loads(_decode(value).decode("utf-8"))
    if not isinstance(decoded, dict):
        raise TokenError("Invalid token")
    return decoded


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
