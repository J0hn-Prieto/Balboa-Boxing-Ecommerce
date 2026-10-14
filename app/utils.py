import re
import unicodedata
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
