"""Contraseñas, sesión del panel y protección contra envíos de formularios falsos (CSRF)."""

import hmac
import secrets
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import Request

MIN_PASSWORD_LENGTH = 10

# Intentos de inicio de sesión: máximo 5 fallos cada 15 minutos por IP y correo.
_MAX_FAILURES = 5
_WINDOW_SECONDS = 15 * 60
_failures: dict[str, deque[float]] = defaultdict(deque)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# Hash de una contraseña cualquiera, para que un correo inexistente tarde lo mismo
# que uno existente y no se pueda adivinar qué correos están registrados.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def _attempt_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "?"
    return f"{ip}|{email.lower()}"


def too_many_attempts(request: Request, email: str) -> bool:
    attempts = _failures[_attempt_key(request, email)]
    now = time.monotonic()
    while attempts and now - attempts[0] > _WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _MAX_FAILURES


def record_failure(request: Request, email: str) -> None:
    _failures[_attempt_key(request, email)].append(time.monotonic())


def clear_failures(request: Request, email: str) -> None:
    _failures.pop(_attempt_key(request, email), None)


def csrf_token(request: Request) -> str:
    """Token secreto que cada formulario del panel envía de vuelta."""
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def csrf_valid(request: Request, submitted: str | None) -> bool:
    expected = request.session.get("csrf")
    return bool(expected and submitted) and hmac.compare_digest(expected, submitted)
