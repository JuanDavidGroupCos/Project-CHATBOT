import json
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from auth_service import (
    COOKIE_NAME,
    build_clear_cookie_header,
    build_set_cookie_header,
    get_session_user,
    login_start,
    login_verify,
    password_reset_complete,
    password_reset_start,
    password_reset_verify,
    revoke_session,
)
from config import APP_NAME, BASE_PATH, FRONTEND_ORIGINS, PORT
from database import SessionLocal
from document_service import build_index, get_document_by_name, list_documents
from qwen_service import ask_qwen


def get_client_ip(handler) -> str:
    xf = handler.headers.get("X-Forwarded-For")
    if xf:
        return xf.split(",")[0].strip()
    return handler.client_address[0] if handler.client_address else ""


class SwanHandler(BaseHTTPRequestHandler):
    server_version = "SWAN/1.0"

    def log_message(self, format, *args):
        return

    def _get_origin(self):
        return self.headers.get("Origin", "")

    def end_headers(self):
        origin = self._get_origin()
        if origin in FRONTEND_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200, extra_headers=None):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def get_cookie_value(self, name: str):
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None

        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get(name)
        return morsel.value if morsel else None

    def get_current_user(self, db):
        raw_token = self.get_cookie_value(COOKIE_NAME)
        if not raw_token:
            return None
        return get_session_user(db, raw_token)

    def require_auth(self, db):
        user = self.get_current_user(db)
        if not user:
            self.send_json(
                {"success": False, "message": "No autenticado", "code": "UNAUTHORIZED"},
                status=401,
            )
            return None
        return user

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        db = SessionLocal()
        try:
            if path == f"{BASE_PATH}/health":
                return self.send_json(
                    {"success": True, "message": f"{APP_NAME} backend activo"},
                    status=200,
                )

            if path == f"{BASE_PATH}/auth/me":
                user = self.require_auth(db)
                if not user:
                    return
                return self.send_json({"success": True, "user": user}, status=200)

            if path == f"{BASE_PATH}/files":
                user = self.require_auth(db)
                if not user:
                    return

                build_index()
                files = list_documents()

                return self.send_json(
                    {
                        "success": True,
                        "count": len(files),
                        "files": files,
                    },
                    status=200,
                )

            if path == f"{BASE_PATH}/document":
                user = self.require_auth(db)
                if not user:
                    return

                filename = (query.get("file", [""])[0] or "").strip()
                if not filename:
                    return self.send_json(
                        {"success": False, "message": "Parámetro file es requerido"},
                        status=400,
                    )

                build_index()
                doc = get_document_by_name(filename)
                if not doc:
                    return self.send_json(
                        {"success": False, "message": "Documento no encontrado"},
                        status=404,
                    )

                return self.send_json(
                    {
                        "success": True,
                        "document": {
                            "file": doc.get("file"),
                            "title": doc.get("title"),
                            "html_content": doc.get("html_content"),
                        },
                    },
                    status=200,
                )

            return self.send_json({"success": False, "message": "Ruta no encontrada"}, status=404)

        except Exception as exc:
            return self.send_json(
                {"success": False, "message": f"Error interno del servidor: {exc}"},
                status=500,
            )
        finally:
            db.close()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        payload = self.read_json()

        db = SessionLocal()
        try:
            if path == f"{BASE_PATH}/auth/login/start":
                email = str(payload.get("email", "")).strip()
                password = str(payload.get("password", "")).strip()

                if not email or not password:
                    return self.send_json(
                        {"success": False, "message": "Email y contraseña son requeridos"},
                        status=400,
                    )

                result = login_start(
                    db,
                    email=email,
                    password=password,
                    ip=get_client_ip(self),
                    user_agent=self.headers.get("User-Agent", ""),
                )

                headers = {}
                if result.get("token"):
                    headers["Set-Cookie"] = build_set_cookie_header(result["token"])

                body = {k: v for k, v in result.items() if k not in ("ok", "status", "token")}
                body["success"] = result["ok"]
                return self.send_json(body, status=result["status"], extra_headers=headers)

            if path == f"{BASE_PATH}/auth/login/verify":
                challenge_id = str(payload.get("challengeId", "")).strip()
                code = str(payload.get("code", "")).strip()

                if not challenge_id or not code:
                    return self.send_json(
                        {"success": False, "message": "challengeId y code son requeridos"},
                        status=400,
                    )

                result = login_verify(
                    db,
                    challenge_id=challenge_id,
                    code=code,
                    ip=get_client_ip(self),
                    user_agent=self.headers.get("User-Agent", ""),
                )

                headers = {}
                if result.get("token"):
                    headers["Set-Cookie"] = build_set_cookie_header(result["token"])

                body = {k: v for k, v in result.items() if k not in ("ok", "status", "token")}
                body["success"] = result["ok"]
                return self.send_json(body, status=result["status"], extra_headers=headers)

            if path == f"{BASE_PATH}/auth/password-reset/start":
                email = str(payload.get("email", "")).strip()
                if not email:
                    return self.send_json(
                        {"success": False, "message": "Email es requerido"},
                        status=400,
                    )

                result = password_reset_start(db, email=email)
                body = {k: v for k, v in result.items() if k not in ("ok", "status")}
                body["success"] = result["ok"]
                return self.send_json(body, status=result["status"])

            if path == f"{BASE_PATH}/auth/password-reset/verify":
                challenge_id = str(payload.get("challengeId", "")).strip()
                code = str(payload.get("code", "")).strip()

                if not challenge_id or not code:
                    return self.send_json(
                        {"success": False, "message": "challengeId y code son requeridos"},
                        status=400,
                    )

                result = password_reset_verify(db, challenge_id=challenge_id, code=code)
                body = {k: v for k, v in result.items() if k not in ("ok", "status")}
                body["success"] = result["ok"]
                return self.send_json(body, status=result["status"])

            if path == f"{BASE_PATH}/auth/password-reset/complete":
                challenge_id = str(payload.get("challengeId", "")).strip()
                code = str(payload.get("code", "")).strip()
                password = str(payload.get("password", "")).strip()
                confirm_password = str(payload.get("confirmPassword", "")).strip()

                if not challenge_id or not code or not password:
                    return self.send_json(
                        {"success": False, "message": "Datos incompletos"},
                        status=400,
                    )

                result = password_reset_complete(
                    db,
                    challenge_id=challenge_id,
                    code=code,
                    password=password,
                    confirm_password=confirm_password,
                )
                body = {k: v for k, v in result.items() if k not in ("ok", "status")}
                body["success"] = result["ok"]
                return self.send_json(body, status=result["status"])

            if path == f"{BASE_PATH}/auth/logout":
                raw_token = self.get_cookie_value(COOKIE_NAME)
                if raw_token:
                    revoke_session(db, raw_token, reason="logout")
                    db.commit()

                return self.send_json(
                    {"success": True, "message": "Logout exitoso"},
                    status=200,
                    extra_headers={"Set-Cookie": build_clear_cookie_header()},
                )

            if path == f"{BASE_PATH}/chat":
                user = self.require_auth(db)
                if not user:
                    return

                question = str(payload.get("question", "")).strip()
                history = payload.get("history", [])
                current_document = str(payload.get("currentDocument", "")).strip()

                if not question:
                    return self.send_json(
                        {"success": False, "message": "La pregunta es requerida"},
                        status=400,
                    )

                result = ask_qwen(
                    question=question,
                    history=history if isinstance(history, list) else [],
                    role_key=user["rol"],
                    current_document=current_document,
                )

                return self.send_json(
                    {
                        "success": True,
                        "answer": result.get("answer", ""),
                        "sources": result.get("sources", []),
                    },
                    status=200,
                )

            return self.send_json({"success": False, "message": "Ruta no encontrada"}, status=404)

        except Exception as exc:
            db.rollback()
            return self.send_json(
                {"success": False, "message": f"Error interno del servidor: {exc}"},
                status=500,
            )
        finally:
            db.close()


if __name__ == "__main__":
    build_index()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), SwanHandler)
    print(f"{APP_NAME} backend ejecutándose en http://127.0.0.1:{PORT}{BASE_PATH}")
    server.serve_forever()