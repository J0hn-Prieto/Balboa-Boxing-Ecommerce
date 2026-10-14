"""Crea la base de datos de la tienda en PostgreSQL y sus tablas.

Uso:  python -m scripts.create_db
"""

import sys

import psycopg
from psycopg import sql

from app.config import get_settings


def main() -> int:
    s = get_settings()
    if s.database_url:
        print("DATABASE_URL está definida; se omite la creación de la base de datos.")
    else:
        if not s.db_password:
            print("Falta DB_PASSWORD en el archivo .env (la contraseña del usuario de PostgreSQL).")
            return 1
        try:
            conn = psycopg.connect(
                host=s.db_host, port=s.db_port, user=s.db_user, password=s.db_password,
                dbname="postgres", autocommit=True,
            )
        except psycopg.OperationalError as e:
            print(f"No se pudo conectar a PostgreSQL en {s.db_host}:{s.db_port} con el usuario "
                  f"'{s.db_user}'.\nRevisa DB_PASSWORD y DB_PORT en el archivo .env.\n\nDetalle: {e}")
            return 1
        with conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (s.db_name,)
            ).fetchone()
            if exists:
                print(f"La base de datos '{s.db_name}' ya existe.")
            else:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(s.db_name)))
                print(f"Base de datos '{s.db_name}' creada.")

    from app.database import engine
    from app.models import Base

    Base.metadata.create_all(engine)
    print("Tablas listas: " + ", ".join(sorted(Base.metadata.tables)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
