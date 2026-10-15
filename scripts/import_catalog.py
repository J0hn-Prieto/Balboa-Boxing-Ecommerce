"""Importa o actualiza los productos desde el Excel del catálogo.

Uso:
    python -m scripts.import_catalog
    python -m scripts.import_catalog "C:\\ruta\\catalogo.xlsx" --fotos "C:\\ruta\\fotos"

Sin ruta, usa el archivo de CATALOG_XLSX en .env (por defecto data/catalogo_balboa_boxing.xlsx).
También se puede importar desde el panel: /admin/importar.

Se puede ejecutar las veces que haga falta: los productos se identifican por
"ID producto" y solo se actualizan. Un precio en 0 o un stock sin número no
sobrescriben lo que ya esté guardado en la base de datos.

Fotos: el archivo debe llamarse como el ID del producto, por ejemplo TB-001.jpg.
"""

import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import Base
from app.services.importer import CatalogImportError, run_import


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("xlsx", nargs="?", type=Path, default=get_settings().catalog_xlsx_path)
    parser.add_argument("--fotos", type=Path, help="Carpeta con las fotos, nombradas por ID de producto")
    parser.add_argument("--ocultar-faltantes", action="store_true",
                        help="Oculta de la tienda los productos que ya no están en el Excel")
    parser.add_argument("--solo-nuevos", action="store_true",
                        help="Solo agrega productos nuevos; no cambia los que ya existen")
    args = parser.parse_args()

    if not args.xlsx.is_file():
        print(f"No se encontró el archivo: {args.xlsx}\n"
              "Indica la ruta del Excel o defínela en CATALOG_XLSX dentro del archivo .env.")
        return 1
    if args.fotos and not args.fotos.is_dir():
        print(f"No se encontró la carpeta de fotos: {args.fotos}")
        return 1

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        try:
            r = run_import(db, args.xlsx, photos_dir=args.fotos,
                           hide_missing=args.ocultar_faltantes, only_new=args.solo_nuevos)
        except CatalogImportError as e:
            print(e)
            return 1

    if r.missing:
        skus = ", ".join(r.missing)
        if r.hidden_missing:
            print(f"Ocultos de la tienda por no estar en el Excel: {skus}")
        else:
            print(f"Siguen visibles en la tienda aunque no están en el Excel: {skus}\n"
                  "Para ocultarlos, repite el comando con --ocultar-faltantes")
    print(f"Productos nuevos: {r.created} | actualizados: {r.updated} | "
          f"sin cambios: {r.skipped} | fotos copiadas: {r.photos}")
    print(f"Sin precio: {len(r.no_price)} | sin stock: {len(r.no_stock)}")
    if r.no_price:
        print("Los productos sin precio se muestran como 'Precio por confirmar' y no se pueden comprar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
