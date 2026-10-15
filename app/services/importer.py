"""Importa o actualiza los productos desde el Excel del catálogo.

Lo usan el comando "python -m scripts.import_catalog" y la página "Importar Excel" del panel.
Los productos se identifican por "ID producto": si ya existe, se actualiza; si no, se crea.
Un precio en 0 o un stock sin número no sobrescriben lo que ya esté guardado.
"""

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import STATIC_DIR, UPLOADS_DIR
from app.models import Category, Product, ProductVariant
from app.services.catalog import search_text_for
from app.utils import normalize, slugify

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Encabezado del Excel (normalizado) -> nombre interno
COLUMNS = {
    "id producto": "sku",
    "nombre del producto": "name",
    "marca": "brand",
    "categoria": "product_type",
    "descripcion": "description",
    "precio actual (pesos col)": "price",
    "precio anterior (pesos col)": "compare_at_price",
    "stock / disponibilidad": "stock",
    "tallas / pesos": "size_info",
    "colores disponibles": "color_info",
    "material / tecnologia": "material",
    "uso recomendado": "recommended_use",
}

# Categorías de la tienda, en el orden del menú. La primera palabra clave que
# coincida con el inicio de la columna "Categoría" del Excel decide el grupo.
CATEGORIES = [
    ("Guantes", ("guantes",)),
    ("Vendas y vendaje", ("vendas", "vendaje", "cinta")),
    ("Protección", ("proteccion",)),
    ("Calzado", ("calzado",)),
    ("Ropa", ("ropa",)),
    ("Entrenamiento", ("equipo de entrenamiento",)),
    ("Kits", ("kit",)),
    ("Accesorios", ("accesorios",)),
]
FALLBACK_CATEGORY = "Accesorios"

# Notas del Excel que no son información para el cliente
PLACEHOLDER_WORDS = ("confirmar", "verificar", "no especificado", "no aplica")


class CatalogImportError(Exception):
    """El archivo no se puede importar; el mensaje es para el usuario."""


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0  # ya existían y se pidió importar solo productos nuevos
    photos: int = 0
    no_price: list[str] = field(default_factory=list)
    no_stock: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # en la tienda pero no en el Excel
    hidden_missing: bool = False


def clean_text(value) -> str:
    text = re.sub(r"\s*\(seg[uú]n[^)]*\)", "", str(value or "")).strip()
    return "" if any(w in normalize(text) for w in PLACEHOLDER_WORDS) else text


def to_int(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[.,$\s]", "", str(value))
    return int(digits) if digits.isdigit() else None


def category_for(product_type: str) -> str:
    text = normalize(product_type)
    for name, keywords in CATEGORIES:
        if text.startswith(keywords):
            return name
    return FALLBACK_CATEGORY


def read_rows(source: Path | BinaryIO) -> list[dict]:
    try:
        ws = openpyxl.load_workbook(source, data_only=True, read_only=True).worksheets[0]
    except Exception as e:  # archivo dañado o que no es un Excel
        raise CatalogImportError("No se pudo leer el archivo. Debe ser un Excel (.xlsx).") from e
    rows = ws.iter_rows(values_only=True)
    try:
        header = [COLUMNS.get(normalize(str(h or ""))) for h in next(rows)]
    except StopIteration:
        raise CatalogImportError("El Excel está vacío.") from None
    missing = {"sku", "name"} - set(header)
    if missing:
        names = {"sku": "ID producto", "name": "Nombre del producto"}
        raise CatalogImportError(
            "Al Excel le faltan las columnas: " + ", ".join(names[m] for m in sorted(missing))
        )
    return [
        {key: value for key, value in zip(header, row) if key}
        for row in rows
        if any(cell is not None for cell in row)
    ]


def find_photo(folder: Path | None, sku: str) -> Path | None:
    if folder is None:
        return None
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in IMAGE_EXTENSIONS and f.stem.strip().upper() == sku.upper():
            return f
    return None


def ensure_categories(db: Session) -> dict[str, Category]:
    categories = {c.name: c for c in db.scalars(select(Category))}
    for position, (name, _) in enumerate(CATEGORIES):
        if name not in categories:
            categories[name] = Category(name=name, slug=slugify(name), position=position)
            db.add(categories[name])
    db.flush()
    return categories


def run_import(
    db: Session,
    source: Path | BinaryIO,
    photos_dir: Path | None = None,
    hide_missing: bool = False,
    only_new: bool = False,
) -> ImportResult:
    """Importa el Excel y guarda los cambios. Si algo falla, no se guarda nada."""
    rows = read_rows(source)
    result = ImportResult(hidden_missing=hide_missing)
    categories = ensure_categories(db)
    used_slugs = {slug: sku for slug, sku in db.execute(select(Product.slug, Product.sku))}
    seen = set()

    for row in rows:
        sku = str(row.get("sku") or "").strip()
        name = str(row.get("name") or "").strip()
        if not sku or not name:
            continue
        seen.add(sku)

        product = db.scalar(select(Product).where(Product.sku == sku))
        if product is None:
            slug = slugify(name)
            if used_slugs.get(slug, sku) != sku:  # dos productos con el mismo nombre
                slug = f"{slug}-{slugify(sku)}"
            used_slugs[slug] = sku
            product = Product(sku=sku, slug=slug, variants=[ProductVariant(stock=0)])
            db.add(product)
            result.created += 1
        elif only_new:
            result.skipped += 1
            continue
        else:
            result.updated += 1

        product_type = str(row.get("product_type") or "").strip()
        product.name = name
        product.brand = str(row.get("brand") or "").strip()
        product.product_type = product_type
        product.category = categories[category_for(product_type)]
        product.description = str(row.get("description") or "").strip()
        product.size_info = clean_text(row.get("size_info"))
        product.color_info = clean_text(row.get("color_info"))
        product.material = clean_text(row.get("material"))
        product.recommended_use = clean_text(row.get("recommended_use"))
        product.search_text = search_text_for(product)

        price = to_int(row.get("price"))
        if price:
            product.price = price
        previous = to_int(row.get("compare_at_price"))
        if previous:
            product.compare_at_price = previous

        # El stock del Excel solo aplica a productos de presentación única;
        # los que tienen tallas o colores se gestionan por variante en el panel.
        stock = to_int(row.get("stock"))
        if stock is not None and not product.has_options:
            product.variants[0].stock = max(stock, 0)

        photo = find_photo(photos_dir, sku)
        if photo:
            UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            target = UPLOADS_DIR / f"{sku}{photo.suffix.lower()}"
            shutil.copyfile(photo, target)
            product.image = target.relative_to(STATIC_DIR).as_posix()
            result.photos += 1

        if not product.price:
            result.no_price.append(sku)
        if product.stock == 0:
            result.no_stock.append(sku)

    if not seen:
        db.rollback()
        raise CatalogImportError("El Excel no tiene filas con ID producto y nombre.")

    missing = list(db.scalars(
        select(Product).where(Product.sku.not_in(seen), Product.is_active.is_(True))
    ))
    result.missing = sorted(p.sku for p in missing)
    if hide_missing:
        for product in missing:
            product.is_active = False

    db.commit()
    return result
