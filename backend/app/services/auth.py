import hashlib
import secrets
from datetime import timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings
from app.models.entities import now_utc

AUTH_SALT = "ai-arbitr-auth"
VERIFIED_IP_SALT = "ai-arbitr-verified-ip"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
VERIFIED_IP_MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expires_at():
    return now_utc() + timedelta(minutes=10)


def make_session_cookie(user_id: str) -> str:
    serializer = URLSafeTimedSerializer(settings.app_secret_key, salt=AUTH_SALT)
    return serializer.dumps({"user_id": user_id})


def read_session_cookie(value: str | None) -> str | None:
    if not value:
        return None
    serializer = URLSafeTimedSerializer(settings.app_secret_key, salt=AUTH_SALT)
    try:
        data = serializer.loads(value, max_age=SESSION_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    return data.get("user_id")


def make_verified_ip_cookie(user_id: str, ip_address: str) -> str:
    serializer = URLSafeTimedSerializer(settings.app_secret_key, salt=VERIFIED_IP_SALT)
    return serializer.dumps({"user_id": user_id, "ip": ip_address})


def read_verified_ip_cookie(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    serializer = URLSafeTimedSerializer(settings.app_secret_key, salt=VERIFIED_IP_SALT)
    try:
        data = serializer.loads(value, max_age=VERIFIED_IP_MAX_AGE_SECONDS)
    except BadSignature:
        return None
    if not isinstance(data, dict):
        return None
    user_id = data.get("user_id")
    ip_address = data.get("ip")
    if not user_id or not ip_address:
        return None
    return {"user_id": user_id, "ip": ip_address}
