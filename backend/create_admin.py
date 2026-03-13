from getpass import getpass
from datetime import datetime

from database import SessionLocal
from models import Role, User, HC
from auth_service import hash_password


def main():
    db = SessionLocal()
    try:
        roles = db.query(Role).order_by(Role.id_rol.asc()).all()
        print("Roles disponibles:")
        for role in roles:
            print(f"{role.id_rol} - {role.nombre_rol}")

        print("\nDebes usar un doc_id que ya exista en HC.")
        doc_id = input("doc_id: ").strip()

        hc = db.query(HC).filter(HC.id_doc == doc_id).first()
        if not hc:
            print("Ese doc_id no existe en la tabla hc.")
            return

        print(f"Persona encontrada en HC: {hc.nombre_usuario}")

        email = input("Email: ").strip().lower()
        username = input("Username: ").strip()
        password = getpass("Contraseña: ").strip()
        rol_id = int(input("ID del rol: ").strip())

        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print("Ya existe un usuario con ese email.")
            return

        now = datetime.now()

        user = User(
            rol_id=rol_id,
            doc_id=doc_id,
            email=email,
            password=hash_password(password),
            estado_user="activo",
            user=username,
            created_at=now,
            updated_at=now,
            created_by=1,
            updated_by=1,
            failed_password_attempts=0,
            force_password_change=0,
        )

        db.add(user)
        db.commit()
        print("Usuario creado correctamente en la tabla users.")

    except Exception as exc:
        db.rollback()
        print("Error creando usuario:", exc)
    finally:
        db.close()


if __name__ == "__main__":
    main()