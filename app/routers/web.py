import math

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import STATIC_DIR, TEMPLATES_DIR, get_settings
from app.database import get_db
from app.services import cart as cart_service
from app.services import catalog
from app.utils import format_cop, format_datetime, whatsapp_link

settings = get_settings()
router = APIRouter(include_in_schema=False)

LOGO_FILES = ("img/logo.svg", "img/logo.png", "img/logo.webp", "img/logo.jpg")


def static_exists(path: str) -> bool:
    return (STATIC_DIR / path).is_file()


def wa_link(message: str | None = None) -> str:
    return whatsapp_link(settings.whatsapp_number, message or settings.whatsapp_message)


templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.filters["cop"] = format_cop
templates.env.filters["fecha"] = format_datetime
templates.env.globals.update(settings=settings, static_exists=static_exists, wa_link=wa_link)


def base_context(db: Session, cart_id: str | None) -> dict:
    """Datos que usa la plantilla base en todas las páginas."""
    cart = cart_service.summarize(cart_service.get_cart(db, cart_id))
    return {
        "nav_categories": catalog.list_categories(db),
        "cart_count": cart["count"],
        "logo": next((f for f in LOGO_FILES if static_exists(f)), None),
    }


@router.get("/")
def home(request: Request, cart_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    featured, _ = catalog.list_products(db, catalog.ProductFilters(page_size=8))
    ctx = base_context(db, cart_id) | {"featured": featured}
    return templates.TemplateResponse(request, "index.html", ctx)


def _catalog_page(request: Request, db: Session, cart_id: str | None, f: catalog.ProductFilters):
    category = catalog.get_category(db, f.category) if f.category else None
    if f.category and category is None:
        raise HTTPException(404)
    products, total = catalog.list_products(db, f)
    pages = max(math.ceil(total / f.page_size), 1)
    ctx = base_context(db, cart_id) | {
        "products": products,
        "total": total,
        "pages": pages,
        "f": f,
        "category": category,
        "brands": catalog.list_brands(db),
        "sort_options": catalog.SORT_OPTIONS,
        "page_url": lambda n: str(request.url.include_query_params(pagina=n)),
    }
    return templates.TemplateResponse(request, "catalog.html", ctx)


def _filters(
    q: str = "",
    marca: str = "",
    precio_min: str = "",
    precio_max: str = "",
    disponibles: bool = False,
    orden: str = "destacados",
    pagina: int = Query(1, ge=1),
) -> catalog.ProductFilters:
    # Los precios llegan como texto porque el formulario envía "" si se dejan vacíos.
    to_int = lambda v: int(v) if v.strip().isdigit() else None
    return catalog.ProductFilters(
        q=q.strip(), brand=marca, min_price=to_int(precio_min), max_price=to_int(precio_max),
        in_stock=disponibles, sort=orden, page=pagina,
    )


@router.get("/catalogo")
def catalog_page(
    request: Request,
    categoria: str = "",
    f: catalog.ProductFilters = Depends(_filters),
    cart_id: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    f.category = categoria
    return _catalog_page(request, db, cart_id, f)


@router.get("/categoria/{slug}")
def category_page(
    request: Request,
    slug: str,
    f: catalog.ProductFilters = Depends(_filters),
    cart_id: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    f.category = slug
    return _catalog_page(request, db, cart_id, f)


@router.get("/producto/{slug}")
def product_page(
    request: Request, slug: str, cart_id: str | None = Cookie(None), db: Session = Depends(get_db)
):
    product = catalog.get_product(db, slug)
    if product is None:
        raise HTTPException(404)
    ctx = base_context(db, cart_id) | {
        "product": product,
        "related": catalog.related_products(db, product),
    }
    return templates.TemplateResponse(request, "product.html", ctx)


@router.get("/carrito")
def cart_page(request: Request, cart_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    ctx = base_context(db, cart_id) | {
        "cart": cart_service.summarize(cart_service.get_cart(db, cart_id))
    }
    return templates.TemplateResponse(request, "cart.html", ctx)
