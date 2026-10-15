# Balboa Boxing Club Bogotá — Tienda en línea

E-commerce con FastAPI, PostgreSQL y plantillas Jinja2. La API queda documentada en Swagger.

## Puesta en marcha

Abre una terminal en esta carpeta y activa el entorno virtual:

```powershell
.\.venv\Scripts\Activate.ps1
```

1. Abre el archivo `.env` y escribe en `DB_PASSWORD` la contraseña del usuario `postgres`
   (la misma de pgAdmin). Si tu servidor no usa el puerto 5432, cambia `DB_PORT`.
2. Crea la base de datos y las tablas:
   ```powershell
   python -m scripts.create_db
   ```
3. Importa el catálogo desde el Excel (o súbelo después desde el panel):
   ```powershell
   python -m scripts.import_catalog "C:\ruta\catalogo_balboa_boxing.xlsx"
   ```
   Para no escribir la ruta cada vez, ponla en `CATALOG_XLSX` dentro del `.env`.
4. Crea tu usuario administrador (la contraseña se escribe en la terminal y no se ve):
   ```powershell
   python -m scripts.create_admin tu@correo.com
   ```
5. Inicia la tienda:
   ```powershell
   uvicorn app.main:app --reload
   ```

- Tienda: http://localhost:8000
- Panel de administración: http://localhost:8000/admin
- Swagger: http://localhost:8000/docs

## Panel de administración

En `/admin`, con el correo y la contraseña creados en el paso 4.

- **Resumen**: productos sin precio, agotados, con poco stock (3 o menos) y órdenes pendientes.
- **Productos**: buscar, filtrar, crear y editar. Precio, precio anterior (oferta), stock por
  talla o color, foto, visible u oculto, destacado en la portada.
- **Órdenes**: lista, detalle y cambio de estado (pendiente, pagada, enviada, entregada, cancelada).
- **Importar Excel**: sube el catálogo sin usar la terminal. La opción "Solo agregar productos
  nuevos" evita que el Excel reemplace lo que ya editaste en el panel.

Seguridad: contraseñas con bcrypt, sesión firmada que expira en 8 horas, token CSRF en todos los
formularios y bloqueo de 15 minutos tras 5 intentos fallidos. Para cambiar la contraseña o quitar
el acceso a alguien:

```powershell
python -m scripts.create_admin tu@correo.com              # cambiar contraseña
python -m scripts.create_admin otro@correo.com --desactivar
```

## Pruebas

Usan una base de datos SQLite temporal; no tocan PostgreSQL.

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

## Catálogo, precios y fotos

- El Excel se puede volver a importar cuantas veces haga falta; los productos se
  actualizan por su "ID producto" y no se duplican.
- Si borras una fila del Excel, el producto sigue en la tienda hasta que importes con
  `python -m scripts.import_catalog --ocultar-faltantes`.
- Un producto con precio `0` aparece como "Precio por confirmar" y no se puede comprar.
- La columna "Stock / disponibilidad" debe tener un número para que el producto se pueda vender.
- Fotos: súbelas desde la ficha de cada producto en el panel, o nombra cada archivo con el ID
  del producto (`TB-001.jpg`) y ejecuta:
  ```powershell
  python -m scripts.import_catalog --fotos "C:\ruta\a\las\fotos"
  ```

## Imágenes de la marca

Guárdalas en `app/static/img/` con estos nombres y aparecen solas:

| Archivo | Uso |
|---|---|
| `logo.png` o `logo.svg` | Logo del encabezado (ideal: versión clara sobre fondo transparente) |
| `hero.jpg` | Foto de la portada |
| `categorias/<slug>.jpg` | Foto de cada categoría, por ejemplo `categorias/guantes.jpg` |

## Estructura

```
app/
  main.py          Arranque de la aplicación y documentación Swagger
  config.py        Configuración leída del archivo .env
  models.py        Tablas de la base de datos
  schemas.py       Formatos de entrada y salida de la API
  security.py      Contraseñas, sesión del panel y CSRF
  services/        Lógica del catálogo, carrito, importación y edición de productos
  routers/         Endpoints de la API, páginas de la tienda y panel (admin.py)
  templates/       Páginas HTML (admin/ para el panel)
  static/          CSS, JavaScript e imágenes
scripts/           Crear la base de datos, importar el catálogo y crear administradores
tests/             Pruebas automáticas (pytest)
```
