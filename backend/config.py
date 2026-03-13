import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT_DIR / ".env")

APP_NAME = os.getenv("APP_NAME", "SWAN").strip()
BASE_PATH = os.getenv("SWAN_BASE_PATH", "/api").rstrip("/")
PORT = int(os.getenv("SWAN_PORT", "8000"))

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "").strip()
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus").strip()
QWEN_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

DB_HOST = os.getenv("DB_HOST", "127.0.0.1").strip()
DB_PORT = os.getenv("DB_PORT", "3306").strip()
DB_NAME = os.getenv("DB_NAME", "bbdd_groupcos_bog_quality_analytics_ai").strip()
DB_USER = os.getenv("DB_USER", "").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "").strip()

COOKIE_NAME = os.getenv("COOKIE_NAME", "access_token").strip()
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "6"))
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "10"))
RESET_OTP_TTL_MINUTES = int(os.getenv("RESET_OTP_TTL_MINUTES", os.getenv("OTP_TTL_MINUTES", "10")))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "30"))
PASSWORD_MAX_ATTEMPTS = int(os.getenv("PASSWORD_MAX_ATTEMPTS", "5"))
PASSWORD_MIN_AGE_HOURS = int(os.getenv("PASSWORD_MIN_AGE_HOURS", "24"))
OTP_DISABLED = os.getenv("OTP_DISABLED", "false").lower() == "true"

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()

FRONTEND_ORIGINS = [
    item.strip()
    for item in os.getenv("FRONTEND_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",")
    if item.strip()
]

INPUT_DIR = BACKEND_DIR / "input"
DATA_DIR = BACKEND_DIR / "data"
ASSETS_DIR = BACKEND_DIR / "assets"
INDEX_FILE = DATA_DIR / "index.json"

INPUT_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 220
TOP_K = 6
TEMPERATURE = 0.15

ROLE_RULES = {
    "admin": {
        "label": "Administrador",
        "focus": "Prioriza administración del sistema, control general, soporte y operación."
    },
    "jefe": {
        "label": "Jefe",
        "focus": "Prioriza visión ejecutiva, decisiones, riesgos, hallazgos clave y seguimiento."
    },
    "lider": {
        "label": "Líder",
        "focus": "Prioriza avances, pendientes, cumplimiento, gestión y estado general."
    },
    "supervisor": {
        "label": "Supervisor",
        "focus": "Prioriza monitoreo, cumplimiento operativo, novedades y validaciones."
    },
    "prompter": {
        "label": "Prompter",
        "focus": "Prioriza instrucciones operativas, uso de flujos, matrices y diligenciamiento."
    },
    "analista": {
        "label": "Analista",
        "focus": "Prioriza detalle, reglas, calidad, evidencia, errores e inconsistencias."
    }
}