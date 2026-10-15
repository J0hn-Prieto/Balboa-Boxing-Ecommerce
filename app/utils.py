import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote


def normalize(text: str) -> str:
    """Minúsculas y sin tildes, para que "protección" y "proteccion" coincidan."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-")


def format_cop(value: int | None) -> str:
    return "$" + f"{int(value or 0):,}".replace(",", ".")


def whatsapp_link(number: str, message: str) -> str:
    return f"https://wa.me/{number}?text={quote(message)}"


BOGOTA = ZoneInfo("America/Bogota")


def format_datetime(value: datetime | None) -> str:
    """Fecha y hora de Bogotá, por ejemplo 14/10/2026 8:45 p. m."""
    if value is None:
        return ""
    if value.tzinfo is None:  # SQLite guarda las fechas sin zona horaria (están en UTC)
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    local = value.astimezone(BOGOTA)
    hour = local.hour % 12 or 12
    suffix = "a. m." if local.hour < 12 else "p. m."
    return f"{local:%d/%m/%Y} {hour}:{local:%M} {suffix}"
