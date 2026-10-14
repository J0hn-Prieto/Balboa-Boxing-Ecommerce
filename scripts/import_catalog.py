"""Importa o actualiza los productos desde el Excel del catálogo.

Uso:
    python -m scripts.import_catalog
    python -m scripts.import_catalog "C:\\ruta\\catalogo.xlsx" --fotos "C:\\ruta\\fotos"

Se puede ejecutar las veces que haga falta: los productos se identifican por
"ID producto" y solo se actualizan. Un precio en 0 o un stock sin número no
sobrescriben lo que ya esté guardado en la base de datos.

Fotos: el archivo debe llamarse como el ID del producto, por ejemplo TB-001.jpg.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

import openpyxl
from sqlalchemy import select

from app.config import STATIC_DIR
from app.database import SessionLocal, engine
from app.models import Base, Category, Product, ProductVariant
from app.utils import normalize, slugify

DEFAULT_XLSX = Path(r"C:\Users\jhonp\OneDrive\Documentos\catalogo balboa\catalogo_balboa_boxing.xlsx")
UPLOADS = STATIC_DIR / "uploads" / "products"
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


def read_rows(path: Path) -> list[dict]:
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [COLUMNS.get(normalize(str(h or ""))) for h in next(rows)]
    missing = {"sku", "name"} - set(header)
    if missing:
        raise SystemExit(f"Al Excel le faltan las columnas: {', '.join(sorted(missing))}")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("xlsx", nargs="?", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--fotos", type=Path, help="Carpeta con las fotos, nombradas por ID de producto")
    parser.add_argument("--ocultar-faltantes", action="store_true",
                        help="Oculta de la tienda los productos que ya no están en el Excel")
    args = parser.parse_args()

    if not args.xlsx.is_file():
        print(f"No se encontró el archivo: {args.xlsx}")
        return 1
    if args.fotos and not args.fotos.is_dir():
        print(f"No se encontró la carpeta de fotos: {args.fotos}")
        return 1

    Base.metadata.create_all(engine)
    created = updated = photos = 0
    no_price, no_stock = [], []

    with SessionLocal() as db:
        categories = {c.name: c for c in db.scalars(select(Category))}
        for position, (name, _) in enumerate(CATEGORIES):
            if name not in categories:
                categories[name] = Category(name=name, slug=slugify(name), position=position)
                db.add(categories[name])
        db.flush()

        used_slugs = {slug: sku for slug, sku in db.execute(select(Product.slug, Product.sku))}
        seen = set()

        for row in read_rows(args.xlsx):
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
                created += 1
            else:
                updated += 1

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
            product.search_text = normalize(
                " ".join([sku, name, product.brand, product_type, product.category.name,
                          product.description, product.recommended_use])
            )

            price = to_int(row.get("price"))
            if price:
                product.price = price
            previous = to_int(row.get("compare_at_price"))
            if previous:
                product.compare_at_price = previous

            # El stock del Excel solo aplica a productos de presentación única;
            # los que tienen tallas o colores se gestionan por variante.
            stock = to_int(row.get("stock"))
            if stock is not None and not product.has_options:
                product.variants[0].stock = max(stock, 0)

            photo = find_photo(args.fotos, sku)
            if photo:
                UPLOADS.mkdir(parents=True, exist_ok=True)
                target = UPLOADS / f"{sku}{photo.suffix.lower()}"
                shutil.copyfile(photo, target)
                product.image = target.relative_to(STATIC_DIR).as_posix()
                photos += 1

            if not product.price:
                no_price.append(sku)
            if product.stock == 0:
                no_stock.append(sku)

        # Productos que están en la tienda pero ya no en el Excel
        missing = list(db.scalars(
            select(Product).where(Product.sku.not_in(seen), Product.is_active.is_(True))
        ))
        if args.ocultar_faltantes:
            for product in missing:
                product.is_active = False

        db.commit()

    if missing:
        skus = ", ".join(sorted(p.sku for p in missing))
        if args.ocultar_faltantes:
            print(f"Ocultos de la tienda por no estar en el Excel: {skus}")
        else:
            print(f"Siguen visibles en la tienda aunque no están en el Excel: {skus}\n"
                  "Para ocultarlos, repite el comando con --ocultar-faltantes")
    print(f"Productos nuevos: {created} | actualizados: {updated} | fotos copiadas: {photos}")
    print(f"Sin precio: {len(no_price)} | sin stock: {len(no_stock)}")
    if no_price:
        print("Los productos sin precio se muestran como 'Precio por confirmar' y no se pueden comprar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
