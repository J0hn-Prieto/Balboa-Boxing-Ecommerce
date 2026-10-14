import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CategoryOut, Message, ProductDetail, ProductPage
from app.services import catalog

router = APIRouter(prefix="/api/v1")


@router.get("/categories", response_model=list[CategoryOut], tags=["Catálogo"],
            summary="Listar categorías")
def list_categories(db: Session = Depends(get_db)):
    return [
        CategoryOut(id=c.id, name=c.name, slug=c.slug, product_count=n)
        for c, n in catalog.list_categories(db)
    ]


@router.get("/brands", response_model=list[str], tags=["Catálogo"], summary="Listar marcas")
def list_brands(db: Session = Depends(get_db)):
    return catalog.list_brands(db)


@router.get("/products", response_model=ProductPage, tags=["Catálogo"],
            summary="Buscar y filtrar productos")
def list_products(
    q: str = Query("", description="Texto a buscar en nombre, marca, categoría y descripción"),
    category: str = Query("", description="Slug de la categoría, por ejemplo 'guantes'"),
    brand: str = Query("", description="Nombre exacto de la marca"),
    min_price: int | None = Query(None, ge=0, description="Precio mínimo en COP"),
    max_price: int | None = Query(None, ge=0, description="Precio máximo en COP"),
    in_stock: bool = Query(False, description="Solo productos con precio y stock"),
    sort: Literal["destacados", "precio_asc", "precio_desc", "nombre", "nuevo"] = "destacados",
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
):
    filters = catalog.ProductFilters(
        q=q, category=category, brand=brand, min_price=min_price, max_price=max_price,
        in_stock=in_stock, sort=sort, page=page, page_size=page_size,
    )
    items, total = catalog.list_products(db, filters)
    return ProductPage(
        items=items, total=total, page=page, page_size=page_size,
        pages=math.ceil(total / page_size),
    )


@router.get("/products/{slug}", response_model=ProductDetail, tags=["Catálogo"],
            summary="Detalle de un producto", responses={404: {"model": Message}})
def get_product(slug: str, db: Session = Depends(get_db)):
    product = catalog.get_product(db, slug)
    if product is None:
        raise HTTPException(404, "Producto no encontrado")
    return product
