import html
import json
import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from config import CHUNK_OVERLAP, CHUNK_SIZE, INDEX_FILE, INPUT_DIR, TOP_K


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]

        if end < n:
            last_break = max(chunk.rfind("\n\n"), chunk.rfind(". "), chunk.rfind("\n"))
            if last_break > int(chunk_size * 0.55):
                end = start + last_break + 1
                chunk = text[start:end]

        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)

        if end >= n:
            break

        start = max(end - overlap, start + 1)

    return chunks


def tokenize(text: str):
    return re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9_]+", text.lower())


def term_frequency(tokens):
    tf = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    total = max(len(tokens), 1)
    return {k: v / total for k, v in tf.items()}


def cosine_sparse(v1, v2):
    if not v1 or not v2:
        return 0.0
    common = set(v1.keys()) & set(v2.keys())
    numerator = sum(v1[k] * v2[k] for k in common)
    den1 = math.sqrt(sum(x * x for x in v1.values()))
    den2 = math.sqrt(sum(x * x for x in v2.values()))
    if den1 == 0 or den2 == 0:
        return 0.0
    return numerator / (den1 * den2)


def read_docx_text_and_html(file_path: Path):
    with zipfile.ZipFile(file_path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return "", "<p>Documento vacío.</p>"
        document_xml = zf.read("word/document.xml")

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ET.fromstring(document_xml)
    body = root.find(".//w:body", ns)

    if body is None:
        return "", "<p>Documento vacío.</p>"

    plain_parts = []
    html_parts = []

    for child in list(body):
        tag = child.tag.split("}")[-1]

        if tag == "p":
            runs_html = []
            runs_text = []

            ppr = child.find("./w:pPr", ns)
            align = ""
            if ppr is not None:
                jc = ppr.find("./w:jc", ns)
                if jc is not None:
                    align = jc.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")

            is_heading = False
            if ppr is not None:
                pstyle = ppr.find("./w:pStyle", ns)
                if pstyle is not None:
                    style_val = pstyle.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "")
                    if style_val.lower().startswith("heading"):
                        is_heading = True

            for run in child.findall("./w:r", ns):
                text_nodes = run.findall(".//w:t", ns)
                if not text_nodes:
                    continue

                txt = "".join(node.text or "" for node in text_nodes)
                if not txt.strip():
                    continue

                runs_text.append(txt)
                safe_txt = html.escape(txt)

                rpr = run.find("./w:rPr", ns)
                bold = italic = underline = False

                if rpr is not None:
                    bold = rpr.find("./w:b", ns) is not None
                    italic = rpr.find("./w:i", ns) is not None
                    underline = rpr.find("./w:u", ns) is not None

                if bold:
                    safe_txt = f"<strong>{safe_txt}</strong>"
                if italic:
                    safe_txt = f"<em>{safe_txt}</em>"
                if underline:
                    safe_txt = f"<u>{safe_txt}</u>"

                runs_html.append(safe_txt)

            full_text = "".join(runs_text).strip()
            if not full_text:
                continue

            plain_parts.append(full_text)

            cls = []
            if align == "center":
                cls.append("word-center")
            elif align == "right":
                cls.append("word-right")
            elif align == "both":
                cls.append("word-justify")

            class_attr = f' class="{" ".join(cls)}"' if cls else ""

            if is_heading:
                html_parts.append(f"<h2{class_attr}>{''.join(runs_html)}</h2>")
            else:
                html_parts.append(f"<p{class_attr}>{''.join(runs_html)}</p>")

        elif tag == "tbl":
            rows_html = []
            rows_text = []

            for row in child.findall("./w:tr", ns):
                cell_html = []
                cell_texts = []

                for cell in row.findall("./w:tc", ns):
                    cell_fragments = []
                    cell_plain = []

                    for para in cell.findall(".//w:p", ns):
                        para_runs = []
                        para_text = []

                        for run in para.findall("./w:r", ns):
                            text_nodes = run.findall(".//w:t", ns)
                            if not text_nodes:
                                continue

                            txt = "".join(node.text or "" for node in text_nodes)
                            if not txt.strip():
                                continue

                            para_text.append(txt)
                            safe_txt = html.escape(txt)

                            rpr = run.find("./w:rPr", ns)
                            bold = italic = underline = False

                            if rpr is not None:
                                bold = rpr.find("./w:b", ns) is not None
                                italic = rpr.find("./w:i", ns) is not None
                                underline = rpr.find("./w:u", ns) is not None

                            if bold:
                                safe_txt = f"<strong>{safe_txt}</strong>"
                            if italic:
                                safe_txt = f"<em>{safe_txt}</em>"
                            if underline:
                                safe_txt = f"<u>{safe_txt}</u>"

                            para_runs.append(safe_txt)

                        joined_html = "".join(para_runs).strip()
                        joined_txt = "".join(para_text).strip()

                        if joined_html:
                            cell_fragments.append(f"<div>{joined_html}</div>")
                        if joined_txt:
                            cell_plain.append(joined_txt)

                    final_html = "".join(cell_fragments).strip() or "&nbsp;"
                    final_text = " ".join(cell_plain).strip()

                    cell_html.append(f"<td>{final_html}</td>")
                    cell_texts.append(final_text)

                if cell_html:
                    rows_html.append("<tr>" + "".join(cell_html) + "</tr>")
                if any(cell_texts):
                    rows_text.append(" | ".join(cell_texts))

            if rows_html:
                html_parts.append(
                    '<div class="word-table-wrap"><table class="word-table">'
                    + "".join(rows_html)
                    + "</table></div>"
                )
            if rows_text:
                plain_parts.extend(rows_text)

    plain_text = normalize_text("\n".join(plain_parts))
    html_doc = "".join(html_parts).strip() or "<p>Documento vacío.</p>"
    return plain_text, html_doc


def build_index():
    documents = []
    docx_files = sorted(INPUT_DIR.glob("*.docx"))

    for file_path in docx_files:
        try:
            full_text, html_doc = read_docx_text_and_html(file_path)
            raw_chunks = chunk_text(full_text)

            documents.append(
                {
                    "file": file_path.name,
                    "title": file_path.name,
                    "full_text": full_text,
                    "html_content": html_doc,
                    "chunks": [
                        {
                            "chunk_id": i,
                            "text": chunk,
                            "vector": {},
                        }
                        for i, chunk in enumerate(raw_chunks)
                    ],
                }
            )
        except Exception as exc:
            documents.append(
                {
                    "file": file_path.name,
                    "title": file_path.name,
                    "full_text": f"ERROR AL LEER DOCUMENTO: {exc}",
                    "html_content": f"<p>Error al leer documento: {html.escape(str(exc))}</p>",
                    "chunks": [],
                }
            )

    df = {}
    valid_chunk_count = 0

    for doc in documents:
        for chunk in doc["chunks"]:
            tokens = tokenize(chunk["text"])
            chunk["tokens"] = tokens
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
            valid_chunk_count += 1

    n = max(valid_chunk_count, 1)

    for doc in documents:
        for chunk in doc["chunks"]:
            tf = term_frequency(chunk.get("tokens", []))
            vec = {}
            for term, freq in tf.items():
                idf = math.log((n + 1) / (df.get(term, 0) + 1)) + 1.0
                vec[term] = freq * idf
            chunk["vector"] = vec
            chunk.pop("tokens", None)

    data = {"documents": documents}
    INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_index():
    if not INDEX_FILE.exists():
        return {"documents": []}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"documents": []}


def list_documents():
    data = load_index()
    return [
        {
            "file": doc.get("file"),
            "title": doc.get("title"),
        }
        for doc in data.get("documents", [])
    ]


def get_document_by_name(filename: str):
    data = load_index()
    for doc in data.get("documents", []):
        if doc.get("file") == filename:
            return doc
    return None


def build_query_vector(question: str, candidate_chunks):
    tokens = tokenize(question)
    tf = term_frequency(tokens)

    df = {}
    n = max(len(candidate_chunks), 1)

    for chunk in candidate_chunks:
        for term in chunk.get("vector", {}).keys():
            df[term] = df.get(term, 0) + 1

    qvec = {}
    for term, freq in tf.items():
        idf = math.log((n + 1) / (df.get(term, 0) + 1)) + 1.0
        qvec[term] = freq * idf
    return qvec


def search_context(question: str, current_document: str = "", top_k: int = TOP_K):
    data = load_index()
    docs = data.get("documents", [])
    candidate_chunks = []

    for doc in docs:
        if current_document and doc.get("file") != current_document:
            continue
        for chunk in doc.get("chunks", []):
            candidate_chunks.append(
                {
                    "file": doc["file"],
                    "title": doc.get("title", doc["file"]),
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "vector": chunk.get("vector", {}),
                }
            )

    if not candidate_chunks and current_document:
        for doc in docs:
            for chunk in doc.get("chunks", []):
                candidate_chunks.append(
                    {
                        "file": doc["file"],
                        "title": doc.get("title", doc["file"]),
                        "chunk_id": chunk["chunk_id"],
                        "text": chunk["text"],
                        "vector": chunk.get("vector", {}),
                    }
                )

    if not candidate_chunks:
        return []

    qvec = build_query_vector(question, candidate_chunks)
    scored = []

    for chunk in candidate_chunks:
        score = cosine_sparse(qvec, chunk["vector"])
        scored.append(
            {
                "file": chunk["file"],
                "title": chunk["title"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "score": score,
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]