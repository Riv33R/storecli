"""
auth.py — Модуль аутентификации на основе cookie-сессий.

Логика:
  1. Учётные данные (логин/пароль) хранятся в .env
  2. При POST /api/login генерируется подписанный токен (HMAC-SHA256)
  3. Токен сохраняется в httpOnly cookie 'session'
  4. Middleware проверяет cookie на каждый запрос (кроме исключений)
"""

import hashlib
import hmac
import logging
import os
import secrets
import time

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Секретный ключ для подписи токенов (генерируется при старте, если не задан)
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))

# TTL сессии — 24 часа по умолчанию
SESSION_TTL = int(os.getenv("SESSION_TTL", "86400"))

# Учётные данные
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "admin")

# Пути, не требующие авторизации
PUBLIC_PATHS = {
    "/login",
    "/api/login",
    "/api/logout",
}

# Префиксы, которые пропускаются (статика CSS/JS/шрифты)
PUBLIC_PREFIXES = (
    "/static/",
)


def verify_credentials(username: str, password: str) -> bool:
    """Проверяет логин и пароль."""
    # Constant-time сравнение для защиты от timing attacks
    user_ok = hmac.compare_digest(username, AUTH_USERNAME)
    pass_ok = hmac.compare_digest(password, AUTH_PASSWORD)
    return user_ok and pass_ok


def create_session_token(username: str) -> str:
    """
    Создаёт подписанный токен сессии.

    Формат: username:timestamp:signature
    """
    timestamp = str(int(time.time()))
    payload = f"{username}:{timestamp}"
    signature = _sign(payload)
    return f"{payload}:{signature}"


def validate_session_token(token: str) -> str | None:
    """
    Проверяет и декодирует токен сессии.

    Returns:
        username если токен валиден, None иначе.
    """
    if not token:
        return None

    parts = token.split(":")
    if len(parts) != 3:
        return None

    username, timestamp_str, signature = parts

    # Проверяем подпись
    payload = f"{username}:{timestamp_str}"
    expected = _sign(payload)

    if not hmac.compare_digest(signature, expected):
        logger.warning("Невалидная подпись сессии для '%s'", username)
        return None

    # Проверяем TTL
    try:
        created = int(timestamp_str)
        if time.time() - created > SESSION_TTL:
            logger.info("Сессия '%s' истекла", username)
            return None
    except ValueError:
        return None

    return username


def _sign(payload: str) -> str:
    """HMAC-SHA256 подпись."""
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def is_public_path(path: str) -> bool:
    """Проверяет, является ли путь публичным (не требует авторизации)."""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False
