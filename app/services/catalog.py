from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Category, Product, ProductVariant
from app.utils import normalize

SORT_OPTIONS = {
    "destacados": "Destacados",
    "precio_asc": "Precio: menor a mayor",
    "precio_desc": "Precio: mayor a menor",
    "nombre": "Nombre",
    "nuevo": "Más recientes",
}


@dataclass
class ProductFilters:
    q: str = ""
    category: str = ""  # slug de la categoría
    brand: str = ""
    min_price: int | None = None
    max_price: int | None = None
    in_stock: bool = False
    sort: str = "destacados"
    page: int = 1
    page_size: int = 12


def _in_stock_clause():
    return (
        select(ProductVariant.id)
        .where(ProductVariant.product_id == Product.id, ProductVariant.stock > 0)
        .exists()
    )


def list_products(db: Session, f: ProductFilters) -> tuple[list[Product], int]:
    """Devuelve la página de productos pedida y el total de coincidencias."""
    stmt = select(Product).where(Product.is_active.is_(True))

    for word in normalize(f.q).split():
        stmt = stmt.where(Product.search_text.contains(word))
    if f.category:
        stmt = stmt.join(Product.category).where(Category.slug == f.category)
    if f.brand:
        stmt = stmt.where(Product.brand == f.brand)
    if f.min_price is not None:
        stmt = stmt.where(Product.price >= f.min_price)
    if f.max_price is not None:
        stmt = stmt.where(Product.price > 0, Product.price <= f.max_price)
    if f.in_stock:
        stmt = stmt.where(Product.price > 0, _in_stock_clause())

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    # Los productos sin precio van al final al ordenar por precio.
    no_price_last = Product.price == 0
    order = {
        "precio_asc": (no_price_last, Product.price.asc(), Product.name),
        "precio_desc": (no_price_last, Product.price.desc(), Product.name),
        "nombre": (Product.name,),
        "nuevo": (Product.created_at.desc(), Product.id.desc()),
    }.get(f.sort, (Product.is_featured.desc(), Product.id))

    page = max(f.page, 1)
    stmt = (
        stmt.options(selectinload(Product.variants), selectinload(Product.category))
        .order_by(*order)
        .offset((page - 1) * f.page_size)
        .limit(f.page_size)
    )
    return list(db.scalars(stmt)), total


def get_product(db: Session, slug: str) -> Product | None:
    stmt = (
        select(Product)
        .where(Product.slug == slug, Product.is_active.is_(True))
        .options(selectinload(Product.variants), selectinload(Product.category))
    )
    return db.scalar(stmt)


def related_products(db: Session, product: Product, limit: int = 4) -> list[Product]:
    stmt = (
        select(Product)
        .where(
            Product.category_id == product.category_id,
            Product.id != product.id,
            Product.is_active.is_(True),
        )
        .options(selectinload(Product.variants), selectinload(Product.category))
        .order_by(Product.is_featured.desc(), func.abs(Product.id - product.id))
        .limit(limit)
    )
    return list(db.scalars(stmt))


def list_categories(db: Session) -> list[tuple[Category, int]]:
    """Categorías con su número de productos activos."""
    stmt = (
        select(Category, func.count(Product.id))
        .outerjoin(Product, (Product.category_id == Category.id) & Product.is_active.is_(True))
        .group_by(Category.id)
        .order_by(Category.position, Category.name)
    )
    return [(c, n) for c, n in db.execute(stmt)]


def get_category(db: Session, slug: str) -> Category | None:
    return db.scalar(select(Category).where(Category.slug == slug))


def list_brands(db: Session) -> list[str]:
    stmt = (
        select(Product.brand)
        .where(Product.is_active.is_(True), Product.brand != "")
        .distinct()
        .order_by(Product.brand)
    )
    return list(db.scalars(stmt))
