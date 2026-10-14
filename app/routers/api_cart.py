from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CartItemIn, CartItemUpdate, CartOut, Message
from app.services import cart as cart_service
from app.services.cart import CartError

CART_COOKIE = "cart_id"
CART_MAX_AGE = 60 * 60 * 24 * 30  # 30 días

router = APIRouter(
    prefix="/api/v1/cart",
    tags=["Carrito"],
    responses={409: {"model": Message, "description": "Sin stock, sin precio o no disponible"}},
)


def _respond(db: Session, cart_id: str) -> dict:
    return cart_service.summarize(cart_service.get_cart(db, cart_id))


@router.get("", response_model=CartOut, summary="Ver el carrito")
def get_cart(cart_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    """El carrito se identifica con la cookie `cart_id`, que se crea al agregar
    el primer producto."""
    return cart_service.summarize(cart_service.get_cart(db, cart_id))


@router.post("/items", response_model=CartOut, status_code=201, summary="Agregar un producto")
def add_item(
    body: CartItemIn,
    response: Response,
    cart_id: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    cart = cart_service.get_or_create_cart(db, cart_id)
    try:
        cart_service.add_item(db, cart, body.variant_id, body.quantity)
    except CartError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    response.set_cookie(CART_COOKIE, cart.id, max_age=CART_MAX_AGE, httponly=True, samesite="lax")
    return _respond(db, cart.id)


@router.patch("/items/{item_id}", response_model=CartOut, summary="Cambiar la cantidad")
def update_item(
    item_id: int,
    body: CartItemUpdate,
    cart_id: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    cart = cart_service.get_cart(db, cart_id)
    if cart is None:
        raise HTTPException(404, "El carrito está vacío")
    try:
        cart_service.set_quantity(db, cart, item_id, body.quantity)
    except CartError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    return _respond(db, cart.id)


@router.delete("/items/{item_id}", response_model=CartOut, summary="Quitar un producto")
def remove_item(item_id: int, cart_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    cart = cart_service.get_cart(db, cart_id)
    if cart is None:
        raise HTTPException(404, "El carrito está vacío")
    try:
        cart_service.remove_item(db, cart, item_id)
    except CartError as e:
        raise HTTPException(404, str(e))
    return _respond(db, cart.id)


@router.delete("", response_model=CartOut, summary="Vaciar el carrito")
def clear_cart(cart_id: str | None = Cookie(None), db: Session = Depends(get_db)):
    cart = cart_service.get_cart(db, cart_id)
    if cart is not None:
        cart_service.clear(db, cart)
    return cart_service.summarize(cart)
