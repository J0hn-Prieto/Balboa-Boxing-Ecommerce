"""Panel de administración: inicio de sesión, productos, stock, órdenes e importación del Excel.

Son páginas HTML (no aparecen en Swagger). Todas, menos el inicio de sesión, exigen
una sesión de administrador, y todos los formularios llevan un token CSRF.
"""

import io
import math
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData, UploadFile

from app.config import get_settings
from app.database import get_db
from app.models import AdminUser, Category, Order, Product, ProductVariant
from app.routers.web import templates
from app.security import (
    DUMMY_HASH,
    clear_failures,
    csrf_token,
    csrf_valid,
    record_failure,
    too_many_attempts,
    verify_password,
)
from app.services import product_admin
from app.services.catalog import list_categories
from app.services.importer import CatalogImportError, run_import
from app.utils import normalize

settings = get_settings()
router = APIRouter(prefix="/admin", include_in_schema=False)

PAGE_SIZE = 25
MAX_EXCEL_BYTES = 5 * 1024 * 1024

ORDER_STATUSES = {
    "pendiente": "Pendiente",
    "pagada": "Pagada",
    "enviada": "Enviada",
    "entregada": "Entregada",
    "cancelada": "Cancelada",
}
PAYMENT_METHODS = {"tarjeta": "Tarjeta", "contra_entrega": "Contra entrega"}

PRODUCT_FILTERS = {
    "": "Todos",
    "visibles": "Visibles",
    "ocultos": "Ocultos",
    "sin-precio": "Sin precio",
    "agotados": "Agotados",
    "poco-stock": "Poco stock",
}


# --- Sesión -------------------------------------------------------------------------

class LoginRequired(Exception):
    def __init__(self, next_url: str):
        self.next_url = next_url


class AdminError(Exception):
    """Error que se muestra como página dentro del panel."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


def safe_next(url: str | None) -> str:
    """Solo se permite volver a páginas del panel, nunca a otro sitio."""
    if url and url.startswith("/admin") and not url.startswith("//") and "\\" not in url:
        return url
    return "/admin"


def current_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    admin_id = request.session.get("admin_id")
    started = request.session.get("admin_at", 0)
    if admin_id and time.time() - started < settings.admin_session_hours * 3600:
        user = db.get(AdminUser, admin_id)
        if user and user.is_active:
            return user
    request.session.pop("admin_id", None)
    path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    raise LoginRequired(path)


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session["flash"] = [kind, message]


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200):
    base = {
        "csrf": csrf_token(request),
        "flash": request.session.pop("flash", None),
        "admin_email": request.session.get("admin_email"),
    }
    return templates.TemplateResponse(
        request, f"admin/{name}", base | (ctx or {}), status_code=status_code,
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )


async def checked_form(request: Request) -> FormData:
    form = await request.form()
    if not csrf_valid(request, form.get("csrf_token")):
        raise AdminError(403, "El formulario expiró. Vuelve a la página anterior, recárgala e inténtalo de nuevo.")
    return form


# --- Inicio de sesión ---------------------------------------------------------------

@router.get("/login")
def login_page(request: Request, next: str = "", db: Session = Depends(get_db)):
    if request.session.get("admin_id"):
        return redirect(safe_next(next))
    no_admins = db.scalar(select(func.count(AdminUser.id))) == 0
    return render(request, "login.html", {"next": safe_next(next), "no_admins": no_admins})


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await checked_form(request)
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    next_url = safe_next(str(form.get("next", "")))

    def fail(message: str):
        return render(request, "login.html",
                      {"next": next_url, "email": email, "error": message}, status_code=400)

    if too_many_attempts(request, email):
        return fail("Demasiados intentos. Espera 15 minutos e inténtalo de nuevo.")

    user = db.scalar(select(AdminUser).where(AdminUser.email == email)) if email else None
    password_ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if not (user and user.is_active and password_ok):
        record_failure(request, email)
        return fail("Correo o contraseña incorrectos.")

    clear_failures(request, email)
    request.session.clear()  # una sesión nueva al entrar
    request.session.update(admin_id=user.id, admin_email=user.email, admin_at=int(time.time()))
    return redirect(next_url)


@router.post("/logout")
async def logout(request: Request):
    await checked_form(request)
    request.session.clear()
    flash(request, "Sesión cerrada.")
    return redirect("/admin/login")


# --- Resumen -------------------------------------------------------------------------

@router.get("")
def dashboard(request: Request, admin: AdminUser = Depends(current_admin), db: Session = Depends(get_db)):
    products = list(db.scalars(select(Product).options(selectinload(Product.variants))))
    active = [p for p in products if p.is_active]
    sold_out = [p for p in active if p.has_price and p.stock == 0]
    low = [p for p in active if p.has_price and 0 < p.stock <= product_admin.LOW_STOCK]
    pending = db.scalar(select(func.count(Order.id)).where(Order.status == "pendiente"))
    recent = list(db.scalars(select(Order).order_by(Order.created_at.desc()).limit(5)))
    return render(request, "dashboard.html", {
        "section": "resumen",
        "stats": {
            "active": len(active),
            "hidden": len(products) - len(active),
            "no_price": sum(1 for p in active if not p.has_price),
            "sold_out": len(sold_out),
            "low": len(low),
            "pending": pending,
        },
        "attention": (sold_out + sorted(low, key=lambda p: p.stock))[:10],
        "recent_orders": recent,
        "statuses": ORDER_STATUSES,
        "low_stock": product_admin.LOW_STOCK,
    })


# --- Productos -----------------------------------------------------------------------

def _stock_expr():
    return (
        select(func.coalesce(func.sum(ProductVariant.stock), 0))
        .where(ProductVariant.product_id == Product.id)
        .correlate(Product)
        .scalar_subquery()
    )


@router.get("/productos")
def products_page(
    request: Request,
    q: str = "",
    estado: str = "",
    categoria: str = "",
    pagina: int = 1,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    stock = _stock_expr()
    stmt = select(Product)
    for word in normalize(q).split():
        stmt = stmt.where(or_(Product.search_text.contains(word), func.lower(Product.sku).contains(word)))
    if categoria.isdigit():
        stmt = stmt.where(Product.category_id == int(categoria))
    if estado == "visibles":
        stmt = stmt.where(Product.is_active.is_(True))
    elif estado == "ocultos":
        stmt = stmt.where(Product.is_active.is_(False))
    elif estado == "sin-precio":
        stmt = stmt.where(Product.price == 0)
    elif estado == "agotados":
        stmt = stmt.where(Product.price > 0, stock == 0)
    elif estado == "poco-stock":
        stmt = stmt.where(Product.price > 0, stock > 0, stock <= product_admin.LOW_STOCK)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pages = max(math.ceil(total / PAGE_SIZE), 1)
    page = min(max(pagina, 1), pages)
    products = list(db.scalars(
        stmt.options(selectinload(Product.variants), selectinload(Product.category))
        .order_by(Product.sku)
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ))
    return render(request, "products.html", {
        "section": "productos",
        "products": products,
        "total": total,
        "page": page,
        "pages": pages,
        "q": q,
        "estado": estado if estado in PRODUCT_FILTERS else "",
        "categoria": categoria,
        "filters": PRODUCT_FILTERS,
        "categories": [c for c, _ in list_categories(db)],
        "low_stock": product_admin.LOW_STOCK,
        "page_url": lambda n: str(request.url.include_query_params(pagina=n)),
        "here": request.url.path + (f"?{request.url.query}" if request.url.query else ""),
    })


def _product_form(request: Request, db: Session, values: dict, product: Product | None,
                  errors: dict | None = None, status_code: int = 200):
    return render(request, "product_form.html", {
        "section": "productos",
        "product": product,
        "v": values,
        "errors": errors or {},
        "categories": [c for c, _ in list_categories(db)],
    }, status_code=status_code)


def _get_product(db: Session, product_id: int) -> Product:
    product = db.scalar(
        select(Product).where(Product.id == product_id)
        .options(selectinload(Product.variants), selectinload(Product.category))
    )
    if product is None:
        raise AdminError(404, "Ese producto no existe.")
    return product


@router.get("/productos/nuevo")
def new_product_page(request: Request, admin: AdminUser = Depends(current_admin),
                     db: Session = Depends(get_db)):
    return _product_form(request, db, product_admin.empty_values(), None)


@router.get("/productos/{product_id}")
def edit_product_page(product_id: int, request: Request, admin: AdminUser = Depends(current_admin),
                      db: Session = Depends(get_db)):
    product = _get_product(db, product_id)
    return _product_form(request, db, product_admin.values_from_product(product), product)


async def _save_product(request: Request, db: Session, product: Product | None):
    form = await checked_form(request)
    values = product_admin.values_from_form(form)
    image = form.get("image")
    image = image if isinstance(image, UploadFile) and image.filename else None
    data, errors = product_admin.validate(db, values, product, image)
    if errors:
        return _product_form(request, db, values, product, errors, status_code=400)

    is_new = product is None
    product = product_admin.apply(db, data, product)
    flash(request, "Producto creado." if is_new else "Cambios guardados.")
    return redirect(f"/admin/productos/{product.id}")


@router.post("/productos/nuevo")
async def create_product(request: Request, admin: AdminUser = Depends(current_admin),
                         db: Session = Depends(get_db)):
    return await _save_product(request, db, None)


@router.post("/productos/{product_id}")
async def update_product(product_id: int, request: Request, admin: AdminUser = Depends(current_admin),
                         db: Session = Depends(get_db)):
    return await _save_product(request, db, _get_product(db, product_id))


@router.post("/productos/{product_id}/visibilidad")
async def toggle_visibility(product_id: int, request: Request, admin: AdminUser = Depends(current_admin),
                            db: Session = Depends(get_db)):
    form = await checked_form(request)
    product = _get_product(db, product_id)
    product.is_active = not product.is_active
    db.commit()
    state = "visible en la tienda" if product.is_active else "oculto de la tienda"
    flash(request, f"{product.sku} quedó {state}.")
    return redirect(safe_next(str(form.get("next", ""))) if form.get("next")
                    else f"/admin/productos/{product.id}")


# --- Órdenes -------------------------------------------------------------------------

@router.get("/ordenes")
def orders_page(request: Request, estado: str = "", q: str = "", pagina: int = 1,
                admin: AdminUser = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Order)
    if estado in ORDER_STATUSES:
        stmt = stmt.where(Order.status == estado)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(
            func.lower(Order.number).like(like),
            func.lower(Order.customer_name).like(like),
            func.lower(Order.customer_email).like(like),
            Order.customer_phone.like(like),
        ))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pages = max(math.ceil(total / PAGE_SIZE), 1)
    page = min(max(pagina, 1), pages)
    orders = list(db.scalars(
        stmt.order_by(Order.created_at.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    ))
    return render(request, "orders.html", {
        "section": "ordenes",
        "orders": orders,
        "total": total,
        "page": page,
        "pages": pages,
        "estado": estado,
        "q": q,
        "statuses": ORDER_STATUSES,
        "payments": PAYMENT_METHODS,
        "page_url": lambda n: str(request.url.include_query_params(pagina=n)),
    })


def _get_order(db: Session, order_id: int) -> Order:
    order = db.scalar(select(Order).where(Order.id == order_id).options(selectinload(Order.items)))
    if order is None:
        raise AdminError(404, "Esa orden no existe.")
    return order


@router.get("/ordenes/{order_id}")
def order_page(order_id: int, request: Request, admin: AdminUser = Depends(current_admin),
               db: Session = Depends(get_db)):
    return render(request, "order.html", {
        "section": "ordenes",
        "order": _get_order(db, order_id),
        "statuses": ORDER_STATUSES,
        "payments": PAYMENT_METHODS,
    })


@router.post("/ordenes/{order_id}/estado")
async def update_order_status(order_id: int, request: Request, admin: AdminUser = Depends(current_admin),
                              db: Session = Depends(get_db)):
    form = await checked_form(request)
    order = _get_order(db, order_id)
    status = str(form.get("status", ""))
    if status not in ORDER_STATUSES:
        flash(request, "Elige un estado de la lista.", "error")
        return redirect(f"/admin/ordenes/{order.id}")
    order.status = status
    if status == "pagada" and order.paid_at is None:
        order.paid_at = datetime.now(timezone.utc)
    db.commit()
    flash(request, f"Orden marcada como {ORDER_STATUSES[status].lower()}.")
    return redirect(f"/admin/ordenes/{order.id}")


# --- Importar Excel ------------------------------------------------------------------

@router.get("/importar")
def import_page(request: Request, admin: AdminUser = Depends(current_admin)):
    return render(request, "import.html", {"section": "importar"})


@router.post("/importar")
async def import_excel(request: Request, admin: AdminUser = Depends(current_admin),
                       db: Session = Depends(get_db)):
    form = await checked_form(request)
    upload = form.get("excel")
    options = {"only_new": form.get("only_new") == "1", "hide_missing": form.get("hide_missing") == "1"}

    def fail(message: str):
        return render(request, "import.html",
                      {"section": "importar", "error": message, "options": options}, status_code=400)

    if not isinstance(upload, UploadFile) or not upload.filename:
        return fail("Elige el archivo de Excel del catálogo.")
    if not re.search(r"\.xlsx$", upload.filename, re.I):
        return fail("El archivo debe ser un Excel con extensión .xlsx.")
    content = await upload.read(MAX_EXCEL_BYTES + 1)
    if len(content) > MAX_EXCEL_BYTES:
        return fail("El archivo pesa más de 5 MB.")

    try:
        result = run_import(db, io.BytesIO(content), **options)
    except CatalogImportError as e:
        db.rollback()
        return fail(str(e))

    flash(request, f"Excel importado: {result.created} nuevos, {result.updated} actualizados.")
    return render(request, "import.html",
                  {"section": "importar", "result": result, "options": options,
                   "filename": upload.filename})


def login_redirect(exc: LoginRequired) -> RedirectResponse:
    target = "/admin/login" if exc.next_url in ("/admin", "/admin/") else (
        f"/admin/login?next={quote(exc.next_url, safe='')}"
    )
    return redirect(target)
