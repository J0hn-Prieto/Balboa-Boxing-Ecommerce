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
3. Importa el catálogo desde el Excel:
   ```powershell
   python -m scripts.import_catalog
   ```
4. Inicia la tienda:
   ```powershell
   uvicorn app.main:app --reload
   ```

- Tienda: http://localhost:8000
- Swagger: http://localhost:8000/docs

## Catálogo, precios y fotos

- El Excel se puede volver a importar cuantas veces haga falta; los productos se
  actualizan por su "ID producto" y no se duplican.
- Si borras una fila del Excel, el producto sigue en la tienda hasta que importes con
  `python -m scripts.import_catalog --ocultar-faltantes`.
- Un producto con precio `0` aparece como "Precio por confirmar" y no se puede comprar.
- La columna "Stock / disponibilidad" debe tener un número para que el producto se pueda vender.
- Fotos: nombra cada archivo con el ID del producto (`TB-001.jpg`) y ejecuta:
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
  services/        Lógica del catálogo y del carrito
  routers/         Endpoints de la API y páginas de la tienda
  templates/       Páginas HTML
  static/          CSS, JavaScript e imágenes
scripts/           Crear la base de datos e importar el catálogo
```
