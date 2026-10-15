"""Crear y editar productos desde el panel: lectura del formulario, validación y guardado."""

import re
import secrets
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile

from app.config import STATIC_DIR, UPLOADS_DIR
from app.models import Category, Product, ProductVariant
from app.services.catalog import search_text_for
from app.utils import slugify

LOW_STOCK = 3  # Con esta cantidad o menos, el producto aparece en "Poco stock"
MAX_PRICE = 100_000_000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

TEXT_FIELDS = {  # campo: largo máximo
    "brand": 80,
    "product_type": 120,
    "size_info": 200,
    "color_info": 200,
    "material": 200,
    "recommended_use": 200,
}

# Firma de los primeros bytes de cada formato de imagen permitido
IMAGE_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".webp": (b"RIFF",),
}


@dataclass
class VariantData:
    id: int | None
    size: str | None
    color: str | None
    stock: int


@dataclass
class ProductData:
    sku: str
    name: str
    category_id: int | None
    description: str
    price: int
    compare_at_price: int | None
    is_active: bool
    is_featured: bool
    texts: dict[str, str]
    variants: list[VariantData]
    delete_variant_ids: set[int] = field(default_factory=set)
    image: tuple[str, bytes] | None = None  # (extensión, contenido)
    remove_image: bool = False


# --- Valores que muestra el formulario ---------------------------------------------

def empty_values() -> dict:
    return {
        "sku": "", "name": "", "category_id": "", "description": "", "price": "",
        "compare_at_price": "", "is_active": True, "is_featured": False,
        **{f: "" for f in TEXT_FIELDS},
        "variants": [{"id": "", "size": "", "color": "", "stock": "0", "delete": False}],
        "remove_image": False,
    }


def values_from_product(p: Product) -> dict:
    return {
        "sku": p.sku, "name": p.name, "category_id": str(p.category_id or ""),
        "description": p.description, "price": str(p.price or ""),
        "compare_at_price": str(p.compare_at_price or ""),
        "is_active": p.is_active, "is_featured": p.is_featured,
        **{f: getattr(p, f) or "" for f in TEXT_FIELDS},
        "variants": [
            {"id": str(v.id), "size": v.size or "", "color": v.color or "",
             "stock": str(v.stock), "delete": False}
            for v in p.variants
        ],
        "remove_image": False,
    }


def values_from_form(form: FormData) -> dict:
    def text(name: str) -> str:
        value = form.get(name, "")
        return value.strip() if isinstance(value, str) else ""

    rows = []
    indexes = sorted({int(m.group(1)) for k in form.keys() if (m := re.match(r"^v-(\d+)-", k))})
    for i in indexes:
        row = {k: text(f"v-{i}-{k}") for k in ("id", "size", "color", "stock")}
        row["delete"] = form.get(f"v-{i}-delete") == "1"
        rows.append(row)

    return {
        "sku": text("sku"), "name": text("name"), "category_id": text("category_id"),
        "description": text("description"), "price": text("price"),
        "compare_at_price": text("compare_at_price"),
        "is_active": form.get("is_active") == "1", "is_featured": form.get("is_featured") == "1",
        **{f: text(f) for f in TEXT_FIELDS},
        "variants": rows,
        "remove_image": form.get("remove_image") == "1",
    }


# --- Validación ----------------------------------------------------------------------

def parse_money(text: str) -> int | None:
    """Acepta 189000, 189.000 o $189.000. Devuelve None si no es un número entero."""
    digits = re.sub(r"[\s.$]", "", text)
    return int(digits) if digits.isdigit() else None


def _image_extension(filename: str, head: bytes) -> str | None:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext = ".jpg" if ext == ".jpeg" else ext
    signatures = IMAGE_SIGNATURES.get(ext)
    if not signatures or not head.startswith(signatures):
        return None
    if ext == ".webp" and head[8:12] != b"WEBP":
        return None
    return ext


def validate(db: Session, v: dict, product: Product | None,
             image: UploadFile | None) -> tuple[ProductData | None, dict[str, str]]:
    errors: dict[str, str] = {}

    sku = v["sku"]
    if not sku:
        errors["sku"] = "Escribe la referencia, por ejemplo TB-061."
    elif len(sku) > 40 or not SKU_RE.match(sku):
        errors["sku"] = "Usa solo letras, números, guiones y puntos (máximo 40 caracteres)."
    else:
        other = db.scalar(select(Product).where(Product.sku == sku))
        if other is not None and other is not product:
            errors["sku"] = f"La referencia {sku} ya la tiene otro producto: {other.name}."

    name = v["name"]
    if not name:
        errors["name"] = "Escribe el nombre del producto."
    elif len(name) > 200:
        errors["name"] = "El nombre puede tener máximo 200 caracteres."

    category_id = None
    if v["category_id"]:
        if v["category_id"].isdigit() and db.get(Category, int(v["category_id"])):
            category_id = int(v["category_id"])
        else:
            errors["category_id"] = "Elige una categoría de la lista."

    price = 0
    if v["price"]:
        price = parse_money(v["price"])
        if price is None or price > MAX_PRICE:
            errors["price"] = "Escribe el precio en pesos, sin decimales. Ejemplo: 189000."
            price = 0

    compare = None
    if v["compare_at_price"]:
        compare = parse_money(v["compare_at_price"])
        if compare is None or compare > MAX_PRICE:
            errors["compare_at_price"] = "Escribe el precio anterior en pesos. Ejemplo: 220000."
        elif compare == 0:
            compare = None
        elif price and compare <= price:
            errors["compare_at_price"] = "El precio anterior debe ser mayor que el precio actual."
        elif not price and "price" not in errors:
            errors["compare_at_price"] = "Para mostrar una oferta, primero escribe el precio actual."

    texts = {}
    for f, max_len in TEXT_FIELDS.items():
        if len(v[f]) > max_len:
            errors[f] = f"Máximo {max_len} caracteres."
        texts[f] = v[f]

    # Variantes (talla / color / stock)
    existing = {var.id: var for var in (product.variants if product else [])}
    variants, delete_ids, seen = [], set(), set()
    for i, row in enumerate(v["variants"]):
        vid = int(row["id"]) if row["id"].isdigit() and int(row["id"]) in existing else None
        if row["delete"]:
            if vid:
                delete_ids.add(vid)
            continue
        if vid is None and not (row["size"] or row["color"]) and row["stock"] in ("", "0"):
            continue  # fila nueva vacía
        if len(row["size"]) > 40 or len(row["color"]) > 60:
            errors[f"v-{i}"] = "Talla: máximo 40 caracteres. Color: máximo 60."
        stock_text = row["stock"] or "0"
        if not stock_text.isdigit() or int(stock_text) > 100_000:
            errors[f"v-{i}"] = "El stock debe ser un número entero de 0 en adelante."
            stock_text = "0"
        key = (row["size"].lower(), row["color"].lower())
        if key in seen:
            errors[f"v-{i}"] = "Esta combinación de talla y color está repetida."
        seen.add(key)
        variants.append(VariantData(vid, row["size"] or None, row["color"] or None, int(stock_text)))

    if not variants:
        errors["variants"] = ("El producto necesita al menos una fila de stock. Si no tiene tallas "
                              "ni colores, deja talla y color vacíos y escribe solo el stock.")
    elif len(variants) > 1 and any(not (x.size or x.color) for x in variants):
        errors["variants"] = ("Cuando hay varias filas, cada una debe tener talla o color. "
                              "Elimina la fila sin talla ni color o complétala.")

    image_data = None
    if image is not None:
        content = image.file.read(MAX_IMAGE_BYTES + 1)
        ext = _image_extension(image.filename or "", content[:16])
        if len(content) > MAX_IMAGE_BYTES:
            errors["image"] = "La foto pesa más de 5 MB. Redúcela e inténtalo de nuevo."
        elif ext is None:
            errors["image"] = "La foto debe ser JPG, PNG o WEBP."
        else:
            image_data = (ext, content)

    if errors:
        return None, errors
    return ProductData(
        sku=sku, name=name, category_id=category_id, description=v["description"],
        price=price, compare_at_price=compare, is_active=v["is_active"],
        is_featured=v["is_featured"], texts=texts, variants=variants,
        delete_variant_ids=delete_ids, image=image_data, remove_image=v["remove_image"],
    ), {}


# --- Guardado ------------------------------------------------------------------------

def _unique_slug(db: Session, name: str, sku: str) -> str:
    base = slugify(name) or slugify(sku)
    for candidate in (base, f"{base}-{slugify(sku)}"):
        if db.scalar(select(Product.id).where(Product.slug == candidate)) is None:
            return candidate
    return f"{base}-{secrets.token_hex(3)}"


def _delete_upload(image: str | None) -> None:
    """Borra una foto vieja solo si la subió el panel o el importador."""
    if not image:
        return
    path = (STATIC_DIR / image).resolve()
    if path.is_file() and UPLOADS_DIR.resolve() in path.parents:
        path.unlink()


def apply(db: Session, data: ProductData, product: Product | None) -> Product:
    if product is None:
        product = Product(slug=_unique_slug(db, data.name, data.sku))
        db.add(product)
    # La dirección (slug) de un producto existente no cambia, para no romper enlaces ya compartidos.

    product.sku = data.sku
    product.name = data.name
    product.category = db.get(Category, data.category_id) if data.category_id else None
    product.description = data.description
    product.price = data.price
    product.compare_at_price = data.compare_at_price
    product.is_active = data.is_active
    product.is_featured = data.is_featured
    for f, value in data.texts.items():
        setattr(product, f, value)

    by_id = {var.id: var for var in product.variants}
    for vid in data.delete_variant_ids:
        product.variants.remove(by_id[vid])
    for row in data.variants:
        var = by_id.get(row.id) if row.id else None
        if var is None:
            var = ProductVariant()
            product.variants.append(var)
        var.size, var.color, var.stock = row.size, row.color, row.stock

    if data.remove_image or data.image:
        _delete_upload(product.image)
        product.image = None
    if data.image:
        ext, content = data.image
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOADS_DIR / f"{slugify(data.sku)}-{secrets.token_hex(3)}{ext}"
        target.write_bytes(content)
        product.image = target.relative_to(STATIC_DIR).as_posix()

    product.search_text = search_text_for(product)
    db.commit()
    return product
