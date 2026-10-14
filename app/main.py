from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import STATIC_DIR, get_settings
from app.database import SessionLocal, engine
from app.models import Base
from app.routers import api_cart, api_catalog, web

settings = get_settings()

DESCRIPTION = """
API de la tienda en línea de **Balboa Boxing Club Bogotá**.

* **Catálogo**: categorías, marcas, búsqueda y detalle de productos.
* **Carrito**: agregar, cambiar cantidades y quitar productos.

Los precios están en pesos colombianos (COP) con IVA incluido.
"""

TAGS = [
    {"name": "Catálogo", "description": "Productos, categorías y marcas."},
    {"name": "Carrito", "description": "Carrito de compras del visitante, guardado por cookie."},
    {"name": "Sistema", "description": "Estado del servicio."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(engine)
    except OperationalError as e:
        raise RuntimeError(
            "No se pudo conectar a la base de datos. Revisa DB_PASSWORD y DB_PORT en el "
            "archivo .env y ejecuta: python -m scripts.create_db"
        ) from e
    yield


app = FastAPI(
    title="Balboa Boxing Club Bogotá — API",
    description=DESCRIPTION,
    version="0.1.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(api_catalog.router)
app.include_router(api_cart.router)
app.include_router(web.router)


@app.get("/api/v1/health", tags=["Sistema"], summary="Estado del servicio")
def health():
    return {"status": "ok"}


@app.exception_handler(StarletteHTTPException)
async def html_or_json_errors(request: Request, exc: StarletteHTTPException):
    """La API responde errores en JSON; las páginas de la tienda, en HTML."""
    if request.url.path.startswith("/api/") or exc.status_code != 404:
        return await http_exception_handler(request, exc)
    with SessionLocal() as db:
        ctx = web.base_context(db, request.cookies.get("cart_id"))
        return web.templates.TemplateResponse(request, "404.html", ctx, status_code=404)
