import io

import openpyxl
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Order, OrderItem, Product
from tests.conftest import ADMIN_EMAIL, csrf_from


def product_form(client, path, **overrides):
    """Envía el formulario de producto con los valores actuales de la página, más los cambios."""
    page = client.get(path)
    data = {
        "csrf_token": csrf_from(page.text), "sku": "TB-001", "name": "Guantes Classic",
        "brand": "BALBOA", "category_id": "1", "price": "", "compare_at_price": "",
        "is_active": "1", "v-0-id": "", "v-0-size": "", "v-0-color": "", "v-0-stock": "0",
    }
    data.update(overrides)
    data = {k: v for k, v in data.items() if v is not None}
    files = data.pop("_files", None)
    return client.post(path, data=data, files=files, follow_redirects=False)


def get_product(sku):
    with SessionLocal() as db:
        p = db.scalar(select(Product).where(Product.sku == sku))
        p.variants  # cargar antes de cerrar la sesión
        return p


# --- Inicio de sesión ----------------------------------------------------------------

def test_panel_requires_login(client):
    r = client.get("/admin/productos", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/login?next=%2Fadmin%2Fproductos"


def test_wrong_password_is_rejected(client):
    page = client.get("/admin/login")
    r = client.post("/admin/login", data={
        "csrf_token": csrf_from(page.text), "email": ADMIN_EMAIL, "password": "incorrecta",
    })
    assert r.status_code == 400
    assert "Correo o contraseña incorrectos" in r.text
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_login_is_blocked_after_five_failures(client):
    for _ in range(5):
        page = client.get("/admin/login")
        client.post("/admin/login", data={
            "csrf_token": csrf_from(page.text), "email": ADMIN_EMAIL, "password": "mal",
        })
    page = client.get("/admin/login")
    r = client.post("/admin/login", data={
        "csrf_token": csrf_from(page.text), "email": ADMIN_EMAIL, "password": "ClaveSegura123",
    })
    assert "Demasiados intentos" in r.text


def test_login_without_csrf_token_is_rejected(client):
    client.get("/admin/login")
    r = client.post("/admin/login", data={"email": ADMIN_EMAIL, "password": "ClaveSegura123"})
    assert r.status_code == 403


def test_login_never_redirects_to_another_site(client):
    page = client.get("/admin/login")
    r = client.post("/admin/login", data={
        "csrf_token": csrf_from(page.text), "email": ADMIN_EMAIL, "password": "ClaveSegura123",
        "next": "https://sitio-falso.com",
    }, follow_redirects=False)
    assert r.headers["location"] == "/admin"


def test_logout(admin):
    page = admin.get("/admin")
    admin.post("/admin/logout", data={"csrf_token": csrf_from(page.text)})
    assert admin.get("/admin", follow_redirects=False).status_code == 303


def test_dashboard_counts_products_without_price(admin):
    r = admin.get("/admin")
    assert r.status_code == 200
    assert "1 producto sin precio" in r.text


# --- Productos -----------------------------------------------------------------------

def test_set_price_and_stock_makes_product_buyable(admin):
    p = get_product("TB-001")
    r = product_form(admin, f"/admin/productos/{p.id}", price="189.000",
                     **{"v-0-id": str(p.variants[0].id), "v-0-stock": "7"})
    assert r.status_code == 303

    p = get_product("TB-001")
    assert p.price == 189000 and p.stock == 7
    api = admin.get("/api/v1/products/guantes-classic").json()
    assert api["available"] is True and api["price"] == 189000


def test_invalid_values_show_errors_and_save_nothing(admin):
    p = get_product("TB-001")
    r = product_form(admin, f"/admin/productos/{p.id}", name="", price="caro",
                     compare_at_price="1000", **{"v-0-id": str(p.variants[0].id), "v-0-stock": "-2"})
    assert r.status_code == 400
    assert "Escribe el nombre del producto" in r.text
    assert "Escribe el precio en pesos" in r.text
    assert "El stock debe ser un número entero" in r.text
    assert get_product("TB-001").name == "Guantes Classic"


def test_sale_price_must_be_higher(admin):
    p = get_product("TB-001")
    r = product_form(admin, f"/admin/productos/{p.id}", price="200000", compare_at_price="150000",
                     **{"v-0-id": str(p.variants[0].id)})
    assert "El precio anterior debe ser mayor" in r.text


def test_create_product_with_sizes(admin):
    r = product_form(admin, "/admin/productos/nuevo", sku="TB-061", name="Guantes Pro 2.0",
                     price="250000", **{
                         "v-0-size": "12 oz", "v-0-stock": "3",
                         "v-1-size": "14 oz", "v-1-stock": "0",
                         "v-2-size": "16 oz", "v-2-stock": "5",
                     })
    assert r.status_code == 303
    p = get_product("TB-061")
    assert p.slug == "guantes-pro-2-0"
    assert sorted(v.size for v in p.variants) == ["12 oz", "14 oz", "16 oz"]
    assert p.stock == 8
    assert admin.get("/api/v1/products?q=guantes pro").json()["total"] == 1


def test_duplicate_sku_is_rejected(admin):
    r = product_form(admin, "/admin/productos/nuevo", sku="TB-001", name="Otro")
    assert r.status_code == 400
    assert "ya la tiene otro producto" in r.text


def test_mixing_single_and_sized_rows_is_rejected(admin):
    p = get_product("TB-001")
    r = product_form(admin, f"/admin/productos/{p.id}", **{
        "v-0-id": str(p.variants[0].id), "v-1-size": "14 oz", "v-1-stock": "2",
    })
    assert "cada una debe tener talla o color" in r.text


def test_delete_a_variant(admin):
    product_form(admin, "/admin/productos/nuevo", sku="TB-070", name="Vendas", **{
        "v-0-color": "Negro", "v-0-stock": "2", "v-1-color": "Rojo", "v-1-stock": "4",
    })
    p = get_product("TB-070")
    red = next(v for v in p.variants if v.color == "Rojo")
    black = next(v for v in p.variants if v.color == "Negro")
    product_form(admin, f"/admin/productos/{p.id}", sku="TB-070", name="Vendas", **{
        "v-0-id": str(black.id), "v-0-color": "Negro", "v-0-stock": "2",
        "v-1-id": str(red.id), "v-1-color": "Rojo", "v-1-stock": "4", "v-1-delete": "1",
    })
    assert [v.color for v in get_product("TB-070").variants] == ["Negro"]


def test_hide_product_removes_it_from_the_store(admin):
    p = get_product("TB-001")
    page = admin.get("/admin/productos")
    admin.post(f"/admin/productos/{p.id}/visibilidad", data={"csrf_token": csrf_from(page.text)})
    assert get_product("TB-001").is_active is False
    assert admin.get("/api/v1/products/guantes-classic").status_code == 404
    assert "TB-001" in admin.get("/admin/productos?estado=ocultos").text


def test_upload_photo(admin):
    p = get_product("TB-001")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    r = product_form(admin, f"/admin/productos/{p.id}", **{"v-0-id": str(p.variants[0].id)},
                     _files={"image": ("foto.png", png, "image/png")})
    assert r.status_code == 303
    assert get_product("TB-001").image.startswith("uploads/products/tb-001-")


def test_fake_image_is_rejected(admin):
    p = get_product("TB-001")
    r = product_form(admin, f"/admin/productos/{p.id}", **{"v-0-id": str(p.variants[0].id)},
                     _files={"image": ("foto.jpg", b"esto no es una imagen", "image/jpeg")})
    assert "La foto debe ser JPG, PNG o WEBP" in r.text


def test_product_filters(admin):
    assert "TB-001" in admin.get("/admin/productos?estado=sin-precio").text
    assert "TB-001" not in admin.get("/admin/productos?estado=agotados").text
    assert "TB-001" in admin.get("/admin/productos?q=classic").text


# --- Órdenes -------------------------------------------------------------------------

def test_change_order_status(admin):
    with SessionLocal() as db:
        order = Order(number="BB-0001", payment_method="contra_entrega", customer_name="Ana Pérez",
                      customer_email="ana@correo.com", customer_phone="3001234567",
                      address="Calle 1 # 2-3", city="Bogotá", subtotal=189000, shipping_cost=0,
                      total=189000, items=[OrderItem(sku="TB-001", product_name="Guantes Classic",
                                                     unit_price=189000, quantity=1)])
        db.add(order)
        db.commit()
        order_id = order.id

    assert "Ana Pérez" in admin.get("/admin/ordenes").text
    page = admin.get(f"/admin/ordenes/{order_id}")
    admin.post(f"/admin/ordenes/{order_id}/estado",
               data={"csrf_token": csrf_from(page.text), "status": "pagada"})
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        assert order.status == "pagada" and order.paid_at is not None


# --- Importar Excel ------------------------------------------------------------------

def excel(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ID producto", "Nombre del producto", "Marca", "Categoría",
               "Precio actual (pesos col)", "Stock / disponibilidad"])
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_excel_from_panel(admin):
    page = admin.get("/admin/importar")
    content = excel([
        ["TB-001", "Guantes Classic", "BALBOA", "Guantes de boxeo", 189000, 4],
        ["TB-002", "Vendas 4.5 m", "BALBOA", "Vendas", 35000, 10],
    ])
    r = admin.post("/admin/importar", data={"csrf_token": csrf_from(page.text)},
                   files={"excel": ("catalogo.xlsx", content)})
    assert r.status_code == 200
    assert "Excel importado: 1 nuevos, 1 actualizados" in r.text
    assert get_product("TB-001").price == 189000
    assert get_product("TB-002").stock == 10


def test_import_only_new_keeps_panel_edits(admin):
    p = get_product("TB-001")
    product_form(admin, f"/admin/productos/{p.id}", name="Nombre editado en el panel",
                 **{"v-0-id": str(p.variants[0].id)})
    page = admin.get("/admin/importar")
    admin.post("/admin/importar", data={"csrf_token": csrf_from(page.text), "only_new": "1"},
               files={"excel": ("catalogo.xlsx", excel([["TB-001", "Nombre del Excel", "", "", 1, 1]]))})
    assert get_product("TB-001").name == "Nombre editado en el panel"


def test_import_rejects_wrong_file(admin):
    page = admin.get("/admin/importar")
    r = admin.post("/admin/importar", data={"csrf_token": csrf_from(page.text)},
                   files={"excel": ("catalogo.xlsx", b"no es un excel")})
    assert r.status_code == 400
    assert "No se pudo leer el archivo" in r.text
