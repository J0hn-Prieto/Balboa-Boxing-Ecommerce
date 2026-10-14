from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"


class Settings(BaseSettings):
    """Configuración de la tienda. Los valores se leen del archivo .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Balboa Boxing Club Bogotá"
    brand_short: str = "Balboa"
    debug: bool = False
    secret_key: str = "cambia-esta-clave"
    base_url: str = "http://localhost:8000"

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
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
