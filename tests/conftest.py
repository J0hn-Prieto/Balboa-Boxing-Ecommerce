"""Configuración de las pruebas: base de datos SQLite temporal, sin tocar PostgreSQL."""

import os
import re
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="balboa-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["DEBUG"] = "true"
os.environ["SECRET_KEY"] = "clave-solo-para-pruebas-" + "x" * 32

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402

config.UPLOADS_DIR = _tmp / "uploads" / "products"  # las fotos de prueba no van a la carpeta real

from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AdminUser, Base, Product, ProductVariant  # noqa: E402
from app.security import _failures, hash_password  # noqa: E402
from app.services import importer, product_admin  # noqa: E402
from app.services.catalog import search_text_for  # noqa: E402

product_admin.UPLOADS_DIR = config.UPLOADS_DIR
product_admin.STATIC_DIR = _tmp
importer.UPLOADS_DIR = config.UPLOADS_DIR

ADMIN_EMAIL = "admin@balboa.test"
ADMIN_PASSWORD = "ClaveSegura123"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _failures.clear()
    with SessionLocal() as db:
        cats = importer.ensure_categories(db)
        db.add(AdminUser(email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD)))
        p = Product(sku="TB-001", name="Guantes Classic", slug="guantes-classic", brand="BALBOA",
                    category=cats["Guantes"], price=0, variants=[ProductVariant(stock=0)])
        p.search_text = search_text_for(p)
        db.add(p)
        db.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "La página no tiene token CSRF"
    return match.group(1)


@pytest.fixture
def admin(client):
    """Cliente con la sesión de administrador iniciada."""
    page = client.get("/admin/login")
    r = client.post("/admin/login", data={
        "csrf_token": csrf_from(page.text), "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
    }, follow_redirects=False)
    assert r.status_code == 303
    return client
