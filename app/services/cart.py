import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Cart, CartItem, Product, ProductVariant


class CartError(Exception):
    """Operación del carrito que no se puede completar; el mensaje es para el cliente."""


def _load_options():
    return selectinload(Cart.items).selectinload(CartItem.variant).selectinload(
        ProductVariant.product
    ).selectinload(Product.variants)


def get_cart(db: Session, cart_id: str | None) -> Cart | None:
    if not cart_id:
        return None
    return db.scalar(select(Cart).where(Cart.id == cart_id).options(_load_options()))


def get_or_create_cart(db: Session, cart_id: str | None) -> Cart:
    cart = get_cart(db, cart_id)
    if cart is None:
        cart = Cart(id=uuid.uuid4().hex)
        db.add(cart)
        db.flush()
    return cart


def _check_purchasable(variant: ProductVariant, quantity: int) -> None:
    product = variant.product
    if not product.is_active:
        raise CartError("Este producto ya no está disponible.")
    if not product.has_price:
        raise CartError("Este producto aún no tiene precio. Consulta por WhatsApp.")
    if variant.stock <= 0:
        raise CartError("Producto agotado.")
    if quantity > variant.stock:
        raise CartError(f"Solo quedan {variant.stock} unidades disponibles.")


def add_item(db: Session, cart: Cart, variant_id: int, quantity: int) -> None:
    variant = db.get(ProductVariant, variant_id)
    if variant is None:
        raise CartError("El producto no existe.")
    item = next((i for i in cart.items if i.variant_id == variant_id), None)
    new_quantity = quantity + (item.quantity if item else 0)
    _check_purchasable(variant, new_quantity)
    if item:
        item.quantity = new_quantity
    else:
        cart.items.append(CartItem(variant_id=variant_id, quantity=quantity))
    db.commit()


def set_quantity(db: Session, cart: Cart, item_id: int, quantity: int) -> None:
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:
        raise CartError("El producto no está en el carrito.")
    _check_purchasable(item.variant, quantity)
    item.quantity = quantity
    db.commit()


def remove_item(db: Session, cart: Cart, item_id: int) -> None:
    item = next((i for i in cart.items if i.id == item_id), None)
    if item is None:
        raise CartError("El producto no está en el carrito.")
    cart.items.remove(item)
    db.commit()


def clear(db: Session, cart: Cart) -> None:
    cart.items.clear()
    db.commit()


def shipping_for(subtotal: int) -> int:
    settings = get_settings()
    if subtotal == 0 or subtotal >= settings.free_shipping_threshold:
        return 0
    return settings.shipping_cost


def summarize(cart: Cart | None) -> dict:
    """Totales del carrito. Los precios siempre se toman del producto actual."""
    settings = get_settings()
    lines = []
    for item in cart.items if cart else []:
        variant, product = item.variant, item.variant.product
        lines.append(
            {
                "id": item.id,
                "variant_id": variant.id,
                "variant_label": variant.label if product.has_options else "",
                "sku": product.sku,
                "name": product.name,
                "slug": product.slug,
                "image": product.image,
                "category": product.category.name if product.category else "",
                "unit_price": product.price,
                "quantity": item.quantity,
                "line_total": product.price * item.quantity,
                "stock": variant.stock,
            }
        )
    subtotal = sum(line["line_total"] for line in lines)
    shipping = shipping_for(subtotal)
    return {
        "items": lines,
        "count": sum(line["quantity"] for line in lines),
        "subtotal": subtotal,
        "shipping_cost": shipping,
        "total": subtotal + shipping,
        "free_shipping_threshold": settings.free_shipping_threshold,
        "missing_for_free_shipping": max(settings.free_shipping_threshold - subtotal, 0)
        if subtotal
        else settings.free_shipping_threshold,
    }
