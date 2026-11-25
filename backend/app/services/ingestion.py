"""Document ingestion: seed knowledge, PDF/text uploads, cleaning and chunking."""
from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .. import db
from ..config import settings
from ..utils import chunk_text, normalize_text, stable_hash
from .embeddings import EmbeddingService
from .glossary import Glossary
from .language import detect_language

LANGUAGE_FIELDS = {"en": "content_en", "hi": "content_hi", "mr": "content_mr"}


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return value[:48] or f"doc-{uuid.uuid4().hex[:8]}"


def seed_documents(glossary: Glossary, embeddings: EmbeddingService) -> dict[str, int]:
    payload = json.loads(Path(settings.seed_path).read_text(encoding="utf-8"))
    created = 0
    rebuilt = 0
    for item in payload:
        existing = db.get_document(item["id"], include_chunks=False)
        content = item.get("content", {})
        record = {
            "id": item["id"],
            "title_en": item.get("title_en", ""),
            "title_hi": item.get("title_hi", ""),
            "title_mr": item.get("title_mr", ""),
            "publisher": item.get("publisher", ""),
            "source_name": item.get("source_name", ""),
            "source_url": item.get("source_url", ""),
            "publication_date": item.get("publication_date", ""),
            "source_date_note": item.get("source_date_note", ""),
            "licence": item.get("licence", ""),
            "category": item.get("category", "other"),
            "crops": item.get("crops", []),
            "states": item.get("states", ["Maharashtra"]),
            "version": item.get("version", "1.0"),
            "approval_status": item.get("approval_status", "approved"),
            "is_demo": item.get("is_demo", True),
            "content_note": item.get("content_note", ""),
            "content_en": content.get("en", ""),
            "content_hi": content.get("hi", ""),
            "content_mr": content.get("mr", ""),
        }
        if existing:
            if existing.get("chunk_count", 0) == 0:
                rebuild_chunks(record, glossary, embeddings)
                rebuilt += 1
            continue
        db.insert_document(record)
        rebuild_chunks(record, glossary, embeddings)
        created += 1
    return {"created": created, "rebuilt": rebuilt}


def rebuild_chunks(record: dict[str, Any], glossary: Glossary, embeddings: EmbeddingService) -> int:
    chunks: list[dict[str, Any]] = []
    for language, field in LANGUAGE_FIELDS.items():
        text = normalize_text(record.get(field, "") or "")
        if not text:
            continue
        for index, chunk in enumerate(chunk_text(text)):
            metadata = {
                "document_id": record["id"],
                "title": record.get(f"title_{language}") or record.get("title_en", ""),
                "category": record.get("category", "other"),
                "crops": record.get("crops", []),
                "states": record.get("states", []),
                "language": language,
                "is_demo": record.get("is_demo", True),
                "source_name": record.get("source_name", ""),
                "publication_date": record.get("publication_date", ""),
                "chunk_index": index,
            }
            chunks.append(
                {
                    "id": f"{record['id']}:{language}:{index}",
                    "chunk_index": index,
                    "language": language,
                    "text": chunk,
                    "embedding": EmbeddingService.to_blob(embeddings.embed_text(chunk)),
                    "metadata": metadata,
                }
            )
    return db.replace_chunks(record["id"], chunks)


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip()


def parse_uploaded_file(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(data)
    elif suffix in {".txt", ".md", ".markdown"}:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="ignore")
    else:
        raise ValueError("Unsupported file type. Upload a PDF, TXT or Markdown file.")
    text = normalize_text(text)
    if len(text) < 40:
        raise ValueError("No usable text found. Scanned PDFs need OCR, which is not enabled in this prototype.")
    return text


def ingest_upload(
    filename: str,
    data: bytes,
    metadata: dict[str, Any],
    glossary: Glossary,
    embeddings: EmbeddingService,
) -> dict[str, Any]:
    text = parse_uploaded_file(filename, data)
    content_hash = hashlib.sha256(data).hexdigest()
    duplicate = db.find_document_by_hash(content_hash)
    if duplicate:
        raise ValueError(
            f"Duplicate document content already exists (id={duplicate['id']}, title={duplicate['title_en']}, v{duplicate['version']})."
        )

    language = detect_language(text)
    title = normalize_text(metadata.get("title") or Path(filename).stem.replace("_", " ").title())
    document_id = metadata.get("id") or f"upload-{_slug(title)}-{uuid.uuid4().hex[:6]}"

    parent_id = (metadata.get("parent_id") or "").strip()
    existing_parent = db.get_document(parent_id, include_chunks=False) if parent_id else db.find_latest_by_title(title)
    version = "1.0"
    root_parent_id = ""
    if existing_parent:
        root_parent_id = existing_parent.get("parent_id") or existing_parent["id"]
        versions = db.list_document_versions(root_parent_id)
        max_major = 1
        for ver in versions:
            try:
                max_major = max(max_major, int(str(ver.get("version", "1.0")).split(".")[0]))
            except ValueError:
                pass
        version = f"{max_major + 1}.0"

    crops = metadata.get("crops") or []
    if isinstance(crops, str):
        crops = [item.strip() for item in crops.split(",") if item.strip()]
    states = metadata.get("states") or ["Maharashtra"]
    if isinstance(states, str):
        states = [item.strip() for item in states.split(",") if item.strip()]
    record = {
        "id": document_id,
        "title_en": title if language == "en" else title,
        "title_hi": title if language == "hi" else "",
        "title_mr": title if language == "mr" else "",
        "publisher": metadata.get("publisher", "Admin upload"),
        "source_name": metadata.get("source_name", "Admin upload"),
        "source_url": metadata.get("source_url", ""),
        "publication_date": metadata.get("publication_date", ""),
        "source_date_note": "Uploaded through the admin console; source date must be verified by the reviewer.",
        "licence": metadata.get("licence", "Not specified by uploader"),
        "category": metadata.get("category", "crop_advice"),
        "crops": crops or ["all"],
        "states": states,
        "version": version,
        "parent_id": root_parent_id,
        "is_latest": True,
        "content_hash": content_hash,
        "approval_status": metadata.get("approval_status", "pending"),
        "is_demo": False,
        "content_note": metadata.get("content_note", "Uploaded by an administrator. Approval is required before retrieval."),
        "file_name": filename,
        "mime_type": metadata.get("mime_type", ""),
    }
    for lang, field in LANGUAGE_FIELDS.items():
        record[field] = text if lang == language else ""
    db.insert_document(record)
    rebuild_chunks(record, glossary, embeddings)
    if record["approval_status"] == "approved" and root_parent_id:
        db.supersede_previous_versions(document_id)
    # Keep the original upload for auditability; this is a local prototype store.
    safe_name = f"{document_id}{Path(filename).suffix.lower()}"
    (Path(settings.upload_dir) / safe_name).write_bytes(data)
    db.audit(
        "document_uploaded",
        "document",
        document_id,
        json.dumps({"filename": filename, "language": language, "version": version, "parent_id": root_parent_id}),
    )
    return db.get_document(document_id, include_chunks=False) or record


def reingest_document(document_id: str, glossary: Glossary, embeddings: EmbeddingService) -> int:
    record = db.get_document(document_id, include_chunks=False)
    if not record:
        raise ValueError("Document not found")
    return rebuild_chunks(record, glossary, embeddings)
