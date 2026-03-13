from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, BigInteger
from sqlalchemy.orm import relationship
from database import Base


class Role(Base):
    __tablename__ = "roles"

    id_rol = Column(Integer, primary_key=True)
    nombre_rol = Column(String(100), nullable=False)


class HC(Base):
    __tablename__ = "hc"

    id_doc = Column(String(64), primary_key=True)
    nombre_usuario = Column(String(256), nullable=False)
    estado_hc = Column(String(32), nullable=False)
    cargo = Column(String(64), nullable=False)
    site = Column(String(128), nullable=False)
    campana = Column(String(128), nullable=False)
    empresa = Column(String(128), nullable=False)


class User(Base):
    __tablename__ = "users"

    id_user = Column(Integer, primary_key=True, autoincrement=True)
    rol_id = Column(Integer, ForeignKey("roles.id_rol"), nullable=False)
    doc_id = Column(String(64), ForeignKey("hc.id_doc"), nullable=False)
    email = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    estado_user = Column(String(32), nullable=False)
    user = Column(String(100), nullable=False)

    created_at = Column(DateTime)
    created_by = Column(Integer)
    updated_at = Column(DateTime)
    updated_by = Column(Integer)

    failed_password_attempts = Column(Integer)
    last_failed_password_at = Column(DateTime)
    force_password_change = Column(Integer)
    force_password_change_at = Column(DateTime)

    role = relationship("Role")
    hc = relationship("HC")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id_session = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    token_type = Column(String(16), nullable=False)
    token_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)
    revoked_by = Column(Integer)
    revoke_reason = Column(String(64))
    rotated_from = Column(BigInteger)
    ip_created = Column(String(64))
    ip_last = Column(String(64))
    user_agent_hash = Column(String(64))


class LoginOtpChallenge(Base):
    __tablename__ = "login_otp_challenges"

    id_login = Column(Integer, primary_key=True, autoincrement=True)
    challenge_id = Column(String(30), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    code_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer)
    used_at = Column(DateTime)
    last_sent_at = Column(DateTime)
    created_at = Column(DateTime)


class PasswordRecord(Base):
    __tablename__ = "password_record"

    id_password_record = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    password_hash = Column(String(255), nullable=False)
    hash_alg = Column(String(50), nullable=False)
    set_at = Column(DateTime, nullable=False)
    superseded_at = Column(DateTime)
    set_by = Column(Integer)
    set_reason = Column(String(50))


class LogEvent(Base):
    __tablename__ = "log_events"

    id_event = Column(BigInteger, primary_key=True, autoincrement=True)
    event_category = Column(String(32), nullable=False)
    event_type = Column(String(64), nullable=False)
    success = Column(Integer, nullable=False)
    user_id = Column(Integer)
    target_user_id = Column(Integer)
    identifier = Column(String(256))
    ip = Column(String(64))
    user_agent = Column(String(255))
    request_method = Column(String(16))
    request_path = Column(String(255))
    http_status = Column(Integer)
    error_code = Column(String(64))
    message = Column(Text)
    meta_json = Column(Text)
    created_at = Column(DateTime)