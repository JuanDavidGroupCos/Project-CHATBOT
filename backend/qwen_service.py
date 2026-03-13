import requests

from config import APP_NAME, QWEN_API_KEY, QWEN_CHAT_URL, QWEN_MODEL, ROLE_RULES, TEMPERATURE, TOP_K
from document_service import search_context


def ask_qwen(question: str, history, role_key: str, current_document: str = ""):
    if not QWEN_API_KEY:
        return {
            "answer": "Falta configurar QWEN_API_KEY antes de usar SWAN.",
            "sources": [],
        }

    role_info = ROLE_RULES.get(role_key, ROLE_RULES["lider"])
    role_label = role_info["label"]
    role_focus = role_info["focus"]

    context_docs = search_context(question, current_document=current_document, top_k=TOP_K)
    context_text = "\n\n".join(
        f"[Archivo: {d['file']} | Fragmento {d['chunk_id']} | Score: {d['score']:.4f}]\n{d['text']}"
        for d in context_docs
    ).strip()

    if not context_text:
        context_text = "No hay documentos indexados o no se encontró contexto suficiente."

    doc_note = f"Documento activo: {current_document}." if current_document else "No hay documento activo."

    messages = [
        {
            "role": "system",
            "content": (
                f"Eres {APP_NAME}, un asistente documental comercial. "
                f"Atiendes al rol '{role_label}'. "
                f"Intereses del rol: {role_focus} "
                "Responde en español. "
                "Usa primero el contexto documental. "
                "No inventes datos. "
                "Si no hay evidencia suficiente, dilo claramente. "
                "Si la pregunta es sobre uso de la app, guía paso a paso dentro de la interfaz."
            ),
        }
    ]

    for item in history[-8:]:
        role = item.get("role", "user")
        content = item.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append(
        {
            "role": "user",
            "content": (
                f"ROL ACTIVO: {role_label}\n"
                f"{doc_note}\n\n"
                f"CONTEXTO DOCUMENTAL:\n{context_text}\n\n"
                f"PREGUNTA DEL USUARIO:\n{question}\n\n"
                "Instrucciones:\n"
                "- Prioriza la información útil para el rol activo.\n"
                "- Si no hay base suficiente, dilo con claridad.\n"
                "- Si usaste documentos, separa 'Respuesta' y 'Fuentes'."
            ),
        }
    )

    payload = {
        "model": QWEN_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
    }

    try:
        resp = requests.post(
            QWEN_CHAT_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {QWEN_API_KEY}",
            },
            json=payload,
            timeout=90,
        )
        resp.raise_for_status()
        result = resp.json()
        answer = result["choices"][0]["message"]["content"]

        return {
            "answer": answer,
            "sources": [
                {
                    "file": d["file"],
                    "title": d["title"],
                    "chunk_id": d["chunk_id"],
                    "score": d["score"],
                }
                for d in context_docs
            ],
        }
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        return {"answer": f"Error al consultar Qwen: {detail}", "sources": []}
    except Exception as exc:
        return {"answer": f"Error al consultar Qwen: {exc}", "sources": []}