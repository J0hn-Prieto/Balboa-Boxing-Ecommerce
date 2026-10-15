import secrets
import warnings
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"
UPLOADS_DIR = STATIC_DIR / "uploads" / "products"

DEFAULT_SECRET_KEY = "cambia-esta-clave"


class Settings(BaseSettings):
    """Configuración de la tienda. Los valores se leen del archivo .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Balboa Boxing Club Bogotá"
    brand_short: str = "Balboa"
    debug: bool = False
    secret_key: str = DEFAULT_SECRET_KEY
    base_url: str = "http://localhost:8000"

    # Panel de administración
    admin_session_hours: int = 8

    # Excel del catálogo que usa "python -m scripts.import_catalog" si no se indica otro.
    # Ruta absoluta, o relativa a la carpeta del proyecto.
    catalog_xlsx: Path = Path("data") / "catalogo_balboa_boxing.xlsx"

    # Base de datos. Si DATABASE_URL está definida, tiene prioridad.
    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "balboa_ecommerce"
    db_user: str = "postgres"
    db_password: str = ""

    # Envíos (pesos colombianos)
    free_shipping_threshold: int = 120_000
    shipping_cost: int = 10_000

    # Contacto y redes
    whatsapp_number: str = "573118323432"
    whatsapp_message: str = "Hola, quiero información sobre un producto"
    phone_number: str = "+573118323432"
    instagram_url: str = (
        "https://www.instagram.com/explore/locations/1940252736244634/balboa-boxing-club-bogota/"
    )
    facebook_url: str = ""

    @property
    def catalog_xlsx_path(self) -> Path:
        path = self.catalog_xlsx.expanduser()
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def session_secret(self) -> str:
        """Clave para firmar la cookie de sesión del panel.

        En desarrollo, si SECRET_KEY está vacía, se usa una clave temporal (las sesiones se
        cierran al reiniciar el servidor). En producción es obligatorio definirla.
        """
        if self.secret_key and self.secret_key != DEFAULT_SECRET_KEY:
            return self.secret_key
        if not self.debug:
            raise RuntimeError(
                "Falta SECRET_KEY en el archivo .env. Genera una con:\n"
                '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        warnings.warn("SECRET_KEY no está definida en .env; se usa una clave temporal.")
        return _TEMP_SECRET

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


_TEMP_SECRET = secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()
