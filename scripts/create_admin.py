"""Crea un usuario administrador o le cambia la contraseña.

Uso:  python -m scripts.create_admin tu@correo.com

La contraseña se escribe en la terminal y no se muestra mientras la escribes.
"""

import argparse
import getpass
import re
import sys

from sqlalchemy import select

from app.database import SessionLocal, engine
from app.models import AdminUser, Base
from app.security import MIN_PASSWORD_LENGTH, hash_password

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def ask_password() -> str | None:
    password = getpass.getpass(f"Contraseña (mínimo {MIN_PASSWORD_LENGTH} caracteres): ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
        return None
    if getpass.getpass("Repite la contraseña: ") != password:
        print("Las contraseñas no coinciden.")
        return None
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("email", help="Correo con el que se inicia sesión en el panel")
    parser.add_argument("--desactivar", action="store_true", help="Quita el acceso a este usuario")
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not EMAIL_RE.match(email):
        print("Escribe un correo válido, por ejemplo admin@balboa.com")
        return 1

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        user = db.scalar(select(AdminUser).where(AdminUser.email == email))

        if args.desactivar:
            if user is None:
                print(f"No existe un administrador con el correo {email}.")
                return 1
            user.is_active = False
            db.commit()
            print(f"{email} ya no puede entrar al panel.")
            return 0

        if user:
            print(f"{email} ya existe. Escribe la nueva contraseña.")
        password = ask_password()
        if password is None:
            return 1

        if user is None:
            db.add(AdminUser(email=email, password_hash=hash_password(password)))
            message = f"Administrador creado. Entra en /admin con {email}."
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            message = f"Contraseña actualizada para {email}."
        db.commit()
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
