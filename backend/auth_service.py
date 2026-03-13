import json
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Tuple

import bcrypt
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import (
    COOKIE_NAME,
    OTP_DISABLED,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_MINUTES,
    PASSWORD_MAX_ATTEMPTS,
    PASSWORD_MIN_AGE_HOURS,
    RESET_OTP_TTL_MINUTES,
    SESSION_TTL_HOURS,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)
from models import (
    AuthSession,
    HC,
    LogEvent,
    LoginOtpChallenge,
    PasswordRecord,
    Role,
    User,
)

LOGIN_PREFIX = "LOGIN_"
PWD_PREFIX = "PWD_"


def utcnow() -> datetime:
    return datetime.utcnow()


def normalize_role(rol_id: Optional[int], rol_nombre: Optional[str]) -> str:
    rid = int(rol_id or 0)
    if rid == 1:
        return "admin"
    if rid == 2:
        return "jefe"
    if rid == 3:
        return "lider"
    if rid == 4:
        return "supervisor"
    if rid == 5:
        return "prompter"
    if rid == 6:
        return "analista"

    name = (rol_nombre or "").strip().lower()
    mapping = {
        "administrador": "admin",
        "admin": "admin",
        "jefe": "jefe",
        "lider": "lider",
        "líder": "lider",
        "leader": "lider",
        "supervisor": "supervisor",
        "prompter": "prompter",
        "analista": "analista",
        "analyst": "analista",
    }
    return mapping.get(name, "lider")


def mask_email(email: str) -> str:
    if "@" not in email:
        return email
    user_part, domain = email.split("@", 1)
    if len(user_part) <= 2:
        return f"{user_part[:1]}***@{domain}"
    return f"{user_part[:2]}***{user_part[-1]}@{domain}"


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes.")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        password_bytes = password.encode("utf-8")
        hash_bytes = password_hash.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception:
        return False


def password_policy(
    password: str,
    confirm_password: str,
    username: str = "",
    email: str = "",
) -> Tuple[bool, list]:
    errors = []

    if password != confirm_password:
        errors.append("Las contraseñas no coinciden.")

    if len(password) < 8:
        errors.append("La contraseña debe tener mínimo 8 caracteres.")
    if not any(ch.islower() for ch in password):
        errors.append("La contraseña debe tener al menos una minúscula.")
    if not any(ch.isupper() for ch in password):
        errors.append("La contraseña debe tener al menos una mayúscula.")
    if not any(ch.isdigit() for ch in password):
        errors.append("La contraseña debe tener al menos un número.")
    if not any(not ch.isalnum() for ch in password):
        errors.append("La contraseña debe tener al menos un carácter especial.")
    if len(password.encode("utf-8")) > 72:
        errors.append("La contraseña no puede superar 72 bytes.")

    lowered = password.lower()
    if username and username.lower() in lowered:
        errors.append("La contraseña no debe contener tu nombre.")
    if email:
        local = email.split("@")[0].lower()
        if local and local in lowered:
            errors.append("La contraseña no debe contener tu correo.")

    return (len(errors) == 0, errors)


def generate_otp_code() -> str:
    return f"{secrets.randbelow(900000) + 100000}"


def is_active_user(user: Optional[User]) -> bool:
    if not user:
        return False
    return str(user.estado_user or "").strip().lower() == "activo"


def user_payload(user: User, hc: Optional[HC] = None, role: Optional[Role] = None) -> dict:
    role_name = role.nombre_rol if role else (user.role.nombre_rol if getattr(user, "role", None) else None)
    return {
        "id": user.id_user,
        "nombre": hc.nombre_usuario if hc else user.user,
        "email": user.email,
        "rol": normalize_role(user.rol_id, role_name),
        "rol_id": user.rol_id,
        "rol_nombre": role_name,
        "doc_id": user.doc_id,
        "username": user.user,
    }


def log_event(
    db: Session,
    *,
    event_category: str,
    event_type: str,
    success: bool,
    user_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    identifier: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_method: Optional[str] = None,
    request_path: Optional[str] = None,
    http_status: Optional[int] = None,
    error_code: Optional[str] = None,
    message: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    try:
        row = LogEvent(
            event_category=event_category,
            event_type=event_type,
            success=1 if success else 0,
            user_id=user_id,
            target_user_id=target_user_id,
            identifier=identifier,
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
            request_method=request_method,
            request_path=request_path,
            http_status=http_status,
            error_code=error_code,
            message=message,
            meta_json=json.dumps(meta, ensure_ascii=False) if meta is not None else None,
            created_at=utcnow(),
        )
        db.add(row)
        db.flush()
    except Exception:
        # nunca rompas el flujo por auditoría
        pass


def find_user_by_email(db: Session, email: str) -> Optional[User]:
    return (
        db.query(User)
        .filter(func.lower(User.email) == email.strip().lower())
        .first()
    )


def ensure_password_record_seed(db: Session, user: User) -> None:
    existing = (
        db.query(PasswordRecord)
        .filter(PasswordRecord.user_id == user.id_user)
        .first()
    )
    if existing:
        return

    record = PasswordRecord(
        user_id=user.id_user,
        password_hash=user.password,
        hash_alg="bcrypt",
        set_at=user.created_at or utcnow(),
        set_by=None,
        set_reason="create",
    )
    db.add(record)
    db.flush()


def assert_min_password_age(db: Session, user_id: int) -> None:
    record = (
        db.query(PasswordRecord)
        .filter(
            PasswordRecord.user_id == user_id,
            PasswordRecord.set_reason != "create",
        )
        .order_by(PasswordRecord.set_at.desc())
        .first()
    )
    if not record:
        return

    diff = utcnow() - record.set_at
    min_delta = timedelta(hours=PASSWORD_MIN_AGE_HOURS)
    if diff < min_delta:
        remaining_hours = max(1, int((min_delta - diff).total_seconds() // 3600) + 1)
        raise ValueError(
            f"Debes esperar aproximadamente {remaining_hours}h antes de volver a cambiar la contraseña."
        )


def assert_not_reused_password(
    db: Session,
    user_id: int,
    plain_password: str,
    last_n: int = 5,
) -> None:
    rows = (
        db.query(PasswordRecord)
        .filter(PasswordRecord.user_id == user_id)
        .order_by(PasswordRecord.set_at.desc())
        .limit(last_n)
        .all()
    )

    for row in rows:
        if verify_password(plain_password, row.password_hash):
            raise ValueError("No puedes reutilizar una contraseña reciente.")


def rotate_password_record(
    db: Session,
    user_id: int,
    new_hash: str,
    actor_id: Optional[int] = None,
    reason: str = "reset_otp",
) -> None:
    current_rows = (
        db.query(PasswordRecord)
        .filter(
            PasswordRecord.user_id == user_id,
            PasswordRecord.superseded_at.is_(None),
        )
        .all()
    )

    now = utcnow()
    for row in current_rows:
        row.superseded_at = now

    db.add(
        PasswordRecord(
            user_id=user_id,
            password_hash=new_hash,
            hash_alg="bcrypt",
            set_at=now,
            set_by=actor_id,
            set_reason=reason,
        )
    )
    db.flush()


def clear_password_fail_state(db: Session, user: User) -> None:
    user.failed_password_attempts = 0
    user.last_failed_password_at = None
    user.force_password_change = 0
    user.force_password_change_at = None
    db.flush()


def register_password_failure(db: Session, user: User) -> Tuple[bool, int]:
    attempts = int(user.failed_password_attempts or 0) + 1
    user.failed_password_attempts = attempts
    user.last_failed_password_at = utcnow()

    locked = False
    if attempts >= PASSWORD_MAX_ATTEMPTS:
        ensure_password_record_seed(db, user)
        user.force_password_change = 1
        user.force_password_change_at = utcnow()
        user.password = hash_password(secrets.token_urlsafe(32))
        locked = True

    db.flush()
    return locked, attempts


def get_cooldown_remaining(db: Session, user_id: int, prefix: str) -> int:
    last = (
        db.query(LoginOtpChallenge)
        .filter(
            LoginOtpChallenge.user_id == user_id,
            LoginOtpChallenge.challenge_id.like(f"{prefix}%"),
            LoginOtpChallenge.used_at.is_(None),
        )
        .order_by(LoginOtpChallenge.created_at.desc())
        .first()
    )
    if not last or not last.last_sent_at:
        return 0

    elapsed = int((utcnow() - last.last_sent_at).total_seconds())
    remaining = OTP_RESEND_COOLDOWN_SECONDS - elapsed
    return remaining if remaining > 0 else 0


def invalidate_open_challenges(db: Session, user_id: int, prefix: str) -> None:
    rows = (
        db.query(LoginOtpChallenge)
        .filter(
            LoginOtpChallenge.user_id == user_id,
            LoginOtpChallenge.challenge_id.like(f"{prefix}%"),
            LoginOtpChallenge.used_at.is_(None),
        )
        .all()
    )
    now = utcnow()
    for row in rows:
        row.used_at = now
    db.flush()


def create_otp_challenge(
    db: Session,
    user_id: int,
    prefix: str,
    ttl_minutes: int,
) -> Tuple[str, str]:
    challenge_id = f"{prefix}{secrets.token_hex(12)}"
    code = generate_otp_code()

    row = LoginOtpChallenge(
        challenge_id=challenge_id,
        user_id=user_id,
        code_hash=hash_password(code),
        expires_at=utcnow() + timedelta(minutes=ttl_minutes),
        attempts=0,
        last_sent_at=utcnow(),
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return challenge_id, code


def validate_challenge(
    db: Session,
    challenge_id: str,
    code: str,
    expected_prefix: str,
):
    if not challenge_id.startswith(expected_prefix):
        return None, "challengeId inválido"

    row = (
        db.query(LoginOtpChallenge)
        .filter(LoginOtpChallenge.challenge_id == challenge_id)
        .first()
    )
    if not row:
        return None, "Código inválido o expirado"

    if row.used_at:
        return None, "Este código ya fue usado"

    if row.expires_at < utcnow():
        return None, "Código expirado"

    if int(row.attempts or 0) >= OTP_MAX_ATTEMPTS:
        return None, "Demasiados intentos. Vuelve a solicitar el código."

    if not verify_password(code, row.code_hash):
        row.attempts = int(row.attempts or 0) + 1
        db.flush()
        return None, "Código incorrecto"

    return row, None


def send_email(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD or not SMTP_FROM:
        print("SMTP no configurado. Simulando envío de correo.")
        print("DESTINO:", to_email)
        print("ASUNTO:", subject)
        print("TEXTO:", text_body)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())


def send_login_code(to_email: str, code: str) -> None:
    subject = "Código de acceso SWAN"
    html_body = f"""
    <html>
      <body>
        <h2>SWAN</h2>
        <p>Tu código de acceso es:</p>
        <h1>{code}</h1>
        <p>Expira en {OTP_TTL_MINUTES} minutos.</p>
      </body>
    </html>
    """
    text_body = f"Tu código de acceso SWAN es: {code}. Expira en {OTP_TTL_MINUTES} minutos."
    send_email(to_email, subject, html_body, text_body)


def send_password_reset_code(to_email: str, code: str) -> None:
    subject = "Código para cambiar tu contraseña en SWAN"
    html_body = f"""
    <html>
      <body>
        <h2>SWAN</h2>
        <p>Tu código para cambio de contraseña es:</p>
        <h1>{code}</h1>
        <p>Expira en {RESET_OTP_TTL_MINUTES} minutos.</p>
      </body>
    </html>
    """
    text_body = (
        f"Tu código para cambiar tu contraseña en SWAN es: {code}. "
        f"Expira en {RESET_OTP_TTL_MINUTES} minutos."
    )
    send_email(to_email, subject, html_body, text_body)


def create_session(
    db: Session,
    user_id: int,
    ip: str = "",
    user_agent: str = "",
    actor_id: Optional[int] = None,
) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hash = sha256_hex(raw_token)
    now = utcnow()

    active_sessions = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .all()
    )

    for item in active_sessions:
        item.revoked_at = now
        item.revoked_by = actor_id or user_id
        item.revoke_reason = "rotation"

    session = AuthSession(
        user_id=user_id,
        token_type="opaque",
        token_hash=token_hash,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
        ip_created=ip or None,
        ip_last=ip or None,
        user_agent_hash=sha256_hex(user_agent[:255]) if user_agent else None,
    )
    db.add(session)
    db.flush()
    return raw_token


def get_session_user(
    db: Session,
    raw_token: str,
    ip: str = "",
    user_agent: str = "",
):
    if not raw_token:
        return None

    token_hash = sha256_hex(raw_token)

    row = (
        db.query(AuthSession, User, Role, HC)
        .join(User, User.id_user == AuthSession.user_id)
        .join(Role, Role.id_rol == User.rol_id)
        .outerjoin(HC, HC.id_doc == User.doc_id)
        .filter(AuthSession.token_hash == token_hash)
        .first()
    )

    if not row:
        return None

    session, user, role, hc = row

    if session.revoked_at is not None:
        return None

    if session.expires_at <= utcnow():
        return None

    if not is_active_user(user):
        return None

    session.last_seen_at = utcnow()
    if ip:
        session.ip_last = ip
    if user_agent:
        session.user_agent_hash = sha256_hex(user_agent[:255])
    db.flush()

    return user_payload(user, hc=hc, role=role)


def revoke_session(
    db: Session,
    raw_token: str,
    reason: str = "logout",
    actor_id: Optional[int] = None,
) -> None:
    if not raw_token:
        return

    token_hash = sha256_hex(raw_token)
    row = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
        )
        .first()
    )
    if row:
        row.revoked_at = utcnow()
        row.revoked_by = actor_id or row.user_id
        row.revoke_reason = reason
        db.flush()


def revoke_all_user_sessions(
    db: Session,
    user_id: int,
    reason: str,
    actor_id: Optional[int] = None,
) -> None:
    rows = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utcnow(),
        )
        .all()
    )
    now = utcnow()
    for row in rows:
        row.revoked_at = now
        row.revoked_by = actor_id or user_id
        row.revoke_reason = reason
    db.flush()


def build_set_cookie_header(raw_token: str) -> str:
    max_age = SESSION_TTL_HOURS * 60 * 60
    return f"{COOKIE_NAME}={raw_token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={max_age}"


def build_clear_cookie_header() -> str:
    return f"{COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


def login_start(
    db: Session,
    email: str,
    password: str,
    ip: str = "",
    user_agent: str = "",
    request_path: str = "/api/auth/login/start",
):
    user = find_user_by_email(db, email)

    if not user:
        log_event(
            db,
            event_category="auth",
            event_type="AUTH_LOGIN_FAIL",
            success=False,
            identifier=email.strip().lower(),
            ip=ip,
            user_agent=user_agent,
            request_method="POST",
            request_path=request_path,
            http_status=401,
            error_code="USER_NOT_FOUND",
        )
        db.commit()
        return {"ok": False, "status": 401, "message": "Credenciales incorrectas"}

    if not is_active_user(user):
        log_event(
            db,
            event_category="auth",
            event_type="AUTH_LOGIN_FAIL",
            success=False,
            user_id=user.id_user,
            identifier=user.email,
            ip=ip,
            user_agent=user_agent,
            request_method="POST",
            request_path=request_path,
            http_status=403,
            error_code="USER_INACTIVE",
            message="Inactive user",
        )
        db.commit()
        return {
            "ok": False,
            "status": 403,
            "message": "Tu cuenta está desactivada. Contacta al administrador.",
        }

    if int(user.force_password_change or 0) == 1:
        log_event(
            db,
            event_category="auth",
            event_type="AUTH_PASSWORD_FORCE_CHANGE",
            success=False,
            user_id=user.id_user,
            identifier=user.email,
            ip=ip,
            user_agent=user_agent,
            request_method="POST",
            request_path=request_path,
            http_status=403,
            error_code="PASSWORD_CHANGE_REQUIRED",
        )
        db.commit()
        return {
            "ok": False,
            "status": 403,
            "code": "PASSWORD_CHANGE_REQUIRED",
            "message": "Por seguridad debes cambiar tu contraseña. Usa '¿Olvidaste tu contraseña?' para continuar.",
        }

    valid = verify_password(password, user.password)
    if not valid:
        locked, attempts = register_password_failure(db, user)

        log_event(
            db,
            event_category="auth",
            event_type="AUTH_PASSWORD_FORCE_CHANGE" if locked else "AUTH_LOGIN_FAIL",
            success=False,
            user_id=user.id_user,
            identifier=user.email,
            ip=ip,
            user_agent=user_agent,
            request_method="POST",
            request_path=request_path,
            http_status=403 if locked else 401,
            error_code="PASSWORD_CHANGE_REQUIRED" if locked else "INVALID_PASSWORD",
            meta={"attempts": attempts, "max": PASSWORD_MAX_ATTEMPTS},
        )
        db.commit()

        if locked:
            return {
                "ok": False,
                "status": 403,
                "code": "PASSWORD_CHANGE_REQUIRED",
                "message": "Superaste el límite de intentos. Debes cambiar la contraseña para continuar.",
            }

        return {"ok": False, "status": 401, "message": "Credenciales incorrectas"}

    if int(user.failed_password_attempts or 0) > 0:
        clear_password_fail_state(db, user)

    ensure_password_record_seed(db, user)

    hc = db.query(HC).filter(HC.id_doc == user.doc_id).first()
    role = db.query(Role).filter(Role.id_rol == user.rol_id).first()

    if OTP_DISABLED:
        token = create_session(db, user.id_user, ip=ip, user_agent=user_agent, actor_id=user.id_user)

        log_event(
            db,
            event_category="auth",
            event_type="AUTH_LOGIN_OK",
            success=True,
            user_id=user.id_user,
            identifier=user.email,
            ip=ip,
            user_agent=user_agent,
            request_method="POST",
            request_path=request_path,
            http_status=200,
        )
        db.commit()

        return {
            "ok": True,
            "status": 200,
            "otp_required": False,
            "token": token,
            "user": user_payload(user, hc=hc, role=role),
        }

    remaining = get_cooldown_remaining(db, user.id_user, LOGIN_PREFIX)
    if remaining > 0:
        db.commit()
        return {
            "ok": False,
            "status": 429,
            "message": f"Espera {remaining}s antes de solicitar otro código.",
        }

    invalidate_open_challenges(db, user.id_user, LOGIN_PREFIX)
    challenge_id, code = create_otp_challenge(db, user.id_user, LOGIN_PREFIX, OTP_TTL_MINUTES)
    db.commit()

    send_login_code(user.email, code)

    return {
        "ok": True,
        "status": 200,
        "otp_required": True,
        "challengeId": challenge_id,
        "expiresMinutes": OTP_TTL_MINUTES,
        "message": f"Te enviamos un código al correo: {mask_email(user.email)}",
    }


def login_verify(
    db: Session,
    challenge_id: str,
    code: str,
    ip: str = "",
    user_agent: str = "",
    request_path: str = "/api/auth/login/verify",
):
    challenge, error = validate_challenge(db, challenge_id, code, LOGIN_PREFIX)
    if error:
        log_event(
            db,
            event_category="auth",
            event_type="AUTH_LOGIN_FAIL",
            success=False,
            ip=ip,
            user_agent=user_agent,
            request_method="POST",
            request_path=request_path,
            http_status=401,
            error_code="INVALID_OTP",
            message=error,
        )
        db.commit()
        return {"ok": False, "status": 401, "message": error}

    user = db.query(User).filter(User.id_user == challenge.user_id).first()
    if not user or not is_active_user(user):
        db.rollback()
        return {
            "ok": False,
            "status": 403,
            "message": "Tu cuenta está desactivada. Contacta al administrador.",
        }

    if int(user.force_password_change or 0) == 1:
        db.rollback()
        return {
            "ok": False,
            "status": 403,
            "code": "PASSWORD_CHANGE_REQUIRED",
            "message": "Por seguridad debes cambiar tu contraseña antes de iniciar sesión.",
        }

    challenge.used_at = utcnow()

    hc = db.query(HC).filter(HC.id_doc == user.doc_id).first()
    role = db.query(Role).filter(Role.id_rol == user.rol_id).first()

    token = create_session(db, user.id_user, ip=ip, user_agent=user_agent, actor_id=user.id_user)

    log_event(
        db,
        event_category="auth",
        event_type="AUTH_LOGIN_OK",
        success=True,
        user_id=user.id_user,
        identifier=user.email,
        ip=ip,
        user_agent=user_agent,
        request_method="POST",
        request_path=request_path,
        http_status=200,
    )
    db.commit()

    return {
        "ok": True,
        "status": 200,
        "token": token,
        "user": user_payload(user, hc=hc, role=role),
    }


def password_reset_start(
    db: Session,
    email: str,
    ip: str = "",
    user_agent: str = "",
    request_path: str = "/api/auth/password-reset/start",
):
    user = find_user_by_email(db, email)

    if not user:
        db.commit()
        return {
            "ok": True,
            "status": 200,
            "message": "Si el correo está registrado, te enviaremos un código para cambiar la contraseña.",
            "expiresMinutes": RESET_OTP_TTL_MINUTES,
        }

    if not is_active_user(user):
        db.commit()
        return {
            "ok": False,
            "status": 403,
            "message": "Tu cuenta está desactivada. Contacta al administrador.",
        }

    remaining = get_cooldown_remaining(db, user.id_user, PWD_PREFIX)
    if remaining > 0:
        db.commit()
        return {
            "ok": False,
            "status": 429,
            "message": f"Espera {remaining}s antes de solicitar otro código.",
        }

    invalidate_open_challenges(db, user.id_user, PWD_PREFIX)
    challenge_id, code = create_otp_challenge(db, user.id_user, PWD_PREFIX, RESET_OTP_TTL_MINUTES)
    db.commit()

    send_password_reset_code(user.email, code)

    log_event(
        db,
        event_category="auth",
        event_type="AUTH_PASSWORD_RESET_START",
        success=True,
        user_id=user.id_user,
        identifier=user.email,
        ip=ip,
        user_agent=user_agent,
        request_method="POST",
        request_path=request_path,
        http_status=200,
    )

    return {
        "ok": True,
        "status": 200,
        "challengeId": challenge_id,
        "expiresMinutes": RESET_OTP_TTL_MINUTES,
        "message": f"Te enviamos un código al correo: {mask_email(user.email)}",
    }


def password_reset_verify(
    db: Session,
    challenge_id: str,
    code: str,
):
    challenge, error = validate_challenge(db, challenge_id, code, PWD_PREFIX)
    if error:
        db.commit()
        return {"ok": False, "status": 401, "message": error}

    user = db.query(User).filter(User.id_user == challenge.user_id).first()
    if not user or not is_active_user(user):
        db.rollback()
        return {
            "ok": False,
            "status": 403,
            "message": "Tu cuenta está desactivada. Contacta al administrador.",
        }

    db.commit()
    return {"ok": True, "status": 200, "message": "Código válido"}


def password_reset_complete(
    db: Session,
    challenge_id: str,
    code: str,
    password: str,
    confirm_password: str,
    ip: str = "",
    user_agent: str = "",
    request_path: str = "/api/auth/password-reset/complete",
):
    challenge, error = validate_challenge(db, challenge_id, code, PWD_PREFIX)
    if error:
        db.commit()
        return {"ok": False, "status": 401, "message": error}

    user = db.query(User).filter(User.id_user == challenge.user_id).first()
    if not user or not is_active_user(user):
        db.rollback()
        return {
            "ok": False,
            "status": 403,
            "message": "Tu cuenta está desactivada. Contacta al administrador.",
        }

    hc = db.query(HC).filter(HC.id_doc == user.doc_id).first()

    ok, errors = password_policy(
        password,
        confirm_password,
        username=hc.nombre_usuario if hc else user.user,
        email=user.email,
    )
    if not ok:
        db.rollback()
        return {
            "ok": False,
            "status": 400,
            "message": "Contraseña inválida",
            "errors": errors,
        }

    ensure_password_record_seed(db, user)

    if int(user.force_password_change or 0) != 1:
        try:
            assert_min_password_age(db, user.id_user)
        except ValueError as exc:
            db.rollback()
            return {"ok": False, "status": 429, "message": str(exc)}

    try:
        assert_not_reused_password(db, user.id_user, password)
    except ValueError as exc:
        db.rollback()
        return {"ok": False, "status": 400, "message": str(exc)}

    new_hash = hash_password(password)
    user.password = new_hash
    clear_password_fail_state(db, user)

    rotate_password_record(
        db,
        user_id=user.id_user,
        new_hash=new_hash,
        actor_id=user.id_user,
        reason="reset_otp",
    )

    revoke_all_user_sessions(
        db,
        user_id=user.id_user,
        reason="password_reset",
        actor_id=user.id_user,
    )

    challenge.used_at = utcnow()

    log_event(
        db,
        event_category="auth",
        event_type="AUTH_PASSWORD_RESET_OK",
        success=True,
        user_id=user.id_user,
        identifier=user.email,
        ip=ip,
        user_agent=user_agent,
        request_method="POST",
        request_path=request_path,
        http_status=200,
    )
    db.commit()

    return {
        "ok": True,
        "status": 200,
        "message": "Contraseña actualizada. Ahora inicia sesión nuevamente.",
    }