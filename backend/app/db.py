"""SQLite persistence layer.

The application deliberately uses SQLite rather than PostgreSQL/Redis so that
the full demo runs on an ordinary laptop. All connections are short lived and
WAL mode is enabled, which is sufficient for this single-process prototype.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import settings
from .utils import iso_now, json_dumps, json_loads

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title_en TEXT NOT NULL,
    title_hi TEXT NOT NULL DEFAULT '',
    title_mr TEXT NOT NULL DEFAULT '',
    publisher TEXT NOT NULL DEFAULT '',
    source_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    publication_date TEXT NOT NULL DEFAULT '',
    source_date_note TEXT NOT NULL DEFAULT '',
    licence TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    crops TEXT NOT NULL DEFAULT '[]',
    states TEXT NOT NULL DEFAULT '[]',
    version TEXT NOT NULL DEFAULT '1.0',
    parent_id TEXT NOT NULL DEFAULT '',
    is_latest INTEGER NOT NULL DEFAULT 1,
    content_hash TEXT NOT NULL DEFAULT '',
    approval_status TEXT NOT NULL DEFAULT 'pending',
    is_demo INTEGER NOT NULL DEFAULT 1,
    content_note TEXT NOT NULL DEFAULT '',
    content_en TEXT NOT NULL DEFAULT '',
    content_hi TEXT NOT NULL DEFAULT '',
    content_mr TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_by TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL DEFAULT '',
    chunk_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    text TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    embedding BLOB,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_language ON chunks(language);

CREATE TABLE IF NOT EXISTS queries (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    detected_language TEXT NOT NULL DEFAULT 'en',
    intent TEXT NOT NULL DEFAULT 'other',
    intent_confidence REAL NOT NULL DEFAULT 0,
    entities TEXT NOT NULL DEFAULT '{}',
    decision TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    reason_code TEXT NOT NULL DEFAULT '',
    reason_detail TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '[]',
    tool_data TEXT NOT NULL DEFAULT '{}',
    signals TEXT NOT NULL DEFAULT '{}',
    latency_ms REAL NOT NULL DEFAULT 0,
    generation_provider TEXT NOT NULL DEFAULT '',
    input_mode TEXT NOT NULL DEFAULT 'text',
    asr_confidence REAL,
    crop TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    district TEXT NOT NULL DEFAULT '',
    simulated INTEGER NOT NULL DEFAULT 0,
    data_mode TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    review_note TEXT NOT NULL DEFAULT '',
    corrected_answer TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_queries_created ON queries(created_at);
CREATE INDEX IF NOT EXISTS idx_queries_decision ON queries(decision);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    rating TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'new',
    reviewed_at TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_feedback_query ON feedback(query_id);

CREATE TABLE IF NOT EXISTS glossary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_en TEXT NOT NULL UNIQUE,
    term_hi TEXT NOT NULL DEFAULT '',
    term_mr TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    aliases TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    dataset_version TEXT NOT NULL DEFAULT '',
    metrics TEXT NOT NULL DEFAULT '{}',
    cases TEXT NOT NULL DEFAULT '[]',
    duration_ms REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
        migrations = [
            ("parent_id", "TEXT NOT NULL DEFAULT ''"),
            ("is_latest", "INTEGER NOT NULL DEFAULT 1"),
            ("content_hash", "TEXT NOT NULL DEFAULT ''"),
        ]
        for col, col_def in migrations:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {col} {col_def}")


def audit(action: str, entity_type: str = "", entity_id: str = "", detail: str = "", actor: str = "system") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (created_at, actor, action, entity_type, entity_id, detail) VALUES (?,?,?,?,?,?)",
            (iso_now(), actor, action, entity_type, entity_id, detail),
        )


def _document_from_row(row: sqlite3.Row, include_content: bool = True) -> dict[str, Any]:
    doc = dict(row)
    doc["crops"] = json_loads(doc.get("crops"), []) or []
    doc["states"] = json_loads(doc.get("states"), []) or []
    doc["is_demo"] = bool(doc.get("is_demo"))
    doc["is_latest"] = bool(doc.get("is_latest", 1))
    if not include_content:
        for key in ("content_en", "content_hi", "content_mr"):
            doc.pop(key, None)
    return doc


def insert_document(doc: dict[str, Any]) -> str:
    now = iso_now()
    document_id = doc.get("id") or f"doc_{uuid.uuid4().hex[:12]}"
    values = {
        "id": document_id,
        "title_en": doc.get("title_en", ""),
        "title_hi": doc.get("title_hi", ""),
        "title_mr": doc.get("title_mr", ""),
        "publisher": doc.get("publisher", ""),
        "source_name": doc.get("source_name", ""),
        "source_url": doc.get("source_url", ""),
        "publication_date": doc.get("publication_date", ""),
        "source_date_note": doc.get("source_date_note", ""),
        "licence": doc.get("licence", ""),
        "category": doc.get("category", "other"),
        "crops": json_dumps(doc.get("crops", [])),
        "states": json_dumps(doc.get("states", ["Maharashtra"])),
        "version": doc.get("version", "1.0"),
        "parent_id": doc.get("parent_id", ""),
        "is_latest": int(bool(doc.get("is_latest", True))),
        "content_hash": doc.get("content_hash", ""),
        "approval_status": doc.get("approval_status", "pending"),
        "is_demo": int(bool(doc.get("is_demo", True))),
        "content_note": doc.get("content_note", ""),
        "content_en": doc.get("content_en", ""),
        "content_hi": doc.get("content_hi", ""),
        "content_mr": doc.get("content_mr", ""),
        "file_name": doc.get("file_name", ""),
        "mime_type": doc.get("mime_type", ""),
        "created_at": doc.get("created_at", now),
        "updated_at": now,
        "reviewed_by": doc.get("reviewed_by", ""),
        "review_note": doc.get("review_note", ""),
        "reviewed_at": doc.get("reviewed_at", ""),
        "chunk_count": int(doc.get("chunk_count", 0)),
    }
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with get_conn() as conn:
        conn.execute(f"INSERT OR REPLACE INTO documents ({columns}) VALUES ({placeholders})", tuple(values.values()))
    return document_id


def update_document(document_id: str, fields: dict[str, Any]) -> bool:
    allowed = {
        "title_en", "title_hi", "title_mr", "publisher", "source_name", "source_url", "publication_date",
        "source_date_note", "licence", "category", "crops", "states", "version", "approval_status",
        "is_demo", "content_note", "content_en", "content_hi", "content_mr", "file_name", "mime_type",
        "chunk_count", "reviewed_by", "review_note", "reviewed_at",
    }
    fields = {key: value for key, value in fields.items() if key in allowed}
    if not fields:
        return False
    fields["updated_at"] = iso_now()
    for key in ("crops", "states"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json_dumps(fields[key])
    if "is_demo" in fields:
        fields["is_demo"] = int(bool(fields["is_demo"]))
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE documents SET {assignments} WHERE id = ?",
            (*fields.values(), document_id),
        )
        return cursor.rowcount > 0


def replace_chunks(document_id: str, chunks: Iterable[dict[str, Any]]) -> int:
    chunks = list(chunks)
    with get_conn() as conn:
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        conn.executemany(
            "INSERT INTO chunks (id, document_id, chunk_index, language, text, char_count, embedding, metadata) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    chunk["id"],
                    document_id,
                    chunk["chunk_index"],
                    chunk["language"],
                    chunk["text"],
                    len(chunk["text"]),
                    chunk.get("embedding"),
                    json_dumps(chunk.get("metadata", {})),
                )
                for chunk in chunks
            ],
        )
        conn.execute("UPDATE documents SET chunk_count = ?, updated_at = ? WHERE id = ?", (len(chunks), iso_now(), document_id))
    return len(chunks)


def list_documents(
    q: str = "",
    status: str | None = None,
    category: str | None = None,
    crop: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if q:
        clauses.append("(lower(title_en) LIKE ? OR lower(source_name) LIKE ? OR lower(content_en) LIKE ?)")
        like = f"%{q.lower()}%"
        params.extend([like, like, like])
    if status:
        clauses.append("approval_status = ?")
        params.append(status)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if crop:
        clauses.append("(crops LIKE ? OR crops LIKE '%all%')")
        params.append(f'%"{crop}"%')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM documents {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM documents {where} ORDER BY created_at DESC, title_en ASC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    return [_document_from_row(row, include_content=False) for row in rows], total


def get_document(document_id: str, include_chunks: bool = False) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            return None
        doc = _document_from_row(row)
        if include_chunks:
            chunk_rows = conn.execute(
                "SELECT id, chunk_index, language, text, char_count, metadata FROM chunks "
                "WHERE document_id = ? ORDER BY language, chunk_index",
                (document_id,),
            ).fetchall()
            doc["chunks"] = [
                {
                    **dict(chunk),
                    "metadata": json_loads(chunk["metadata"], {}),
                }
                for chunk in chunk_rows
            ]
            doc["versions"] = list_document_versions(document_id)
        return doc


def find_document_by_hash(content_hash: str) -> dict[str, Any] | None:
    if not content_hash:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE content_hash = ? AND approval_status != 'rejected' LIMIT 1",
            (content_hash,),
        ).fetchone()
    return _document_from_row(row, include_content=False) if row else None


def find_latest_by_title(title_en: str) -> dict[str, Any] | None:
    if not title_en:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE lower(title_en) = lower(?) ORDER BY is_latest DESC, created_at DESC LIMIT 1",
            (title_en.strip(),),
        ).fetchone()
    return _document_from_row(row, include_content=False) if row else None


def list_document_versions(document_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        target = conn.execute("SELECT id, parent_id FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not target:
            return []
        root_id = target["parent_id"] or target["id"]
        rows = conn.execute(
            "SELECT id, title_en, version, parent_id, is_latest, approval_status, created_at, updated_at, chunk_count "
            "FROM documents WHERE id = ? OR parent_id = ? ORDER BY created_at DESC",
            (root_id, root_id),
        ).fetchall()
    return [
        {
            **dict(row),
            "is_latest": bool(row["is_latest"]),
        }
        for row in rows
    ]


def supersede_previous_versions(document_id: str) -> int:
    with get_conn() as conn:
        target = conn.execute("SELECT id, parent_id FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not target:
            return 0
        root_id = target["parent_id"] or target["id"]
        cursor = conn.execute(
            "UPDATE documents SET is_latest = 0, "
            "approval_status = CASE WHEN approval_status = 'approved' THEN 'superseded' ELSE approval_status END, "
            "updated_at = ? "
            "WHERE (id = ? OR parent_id = ?) AND id != ?",
            (iso_now(), root_id, root_id, document_id),
        )
        conn.execute("UPDATE documents SET is_latest = 1 WHERE id = ?", (document_id,))
        return cursor.rowcount


def set_document_status(document_id: str, status: str, reviewer: str = "admin", note: str = "") -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE documents SET approval_status = ?, reviewed_by = ?, review_note = ?, reviewed_at = ?, updated_at = ? WHERE id = ?",
            (status, reviewer, note, iso_now(), iso_now(), document_id),
        )
        changed = cursor.rowcount > 0
    if changed:
        if status == "approved":
            supersede_previous_versions(document_id)
        audit("document_status_changed", "document", document_id, json_dumps({"status": status, "reviewer": reviewer, "note": note}), reviewer)
    return changed


def delete_document(document_id: str) -> bool:
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        changed = cursor.rowcount > 0
    if changed:
        audit("document_deleted", "document", document_id)
    return changed


def list_chunks(approved_only: bool = True, document_id: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if approved_only:
        clauses.append("d.approval_status = 'approved'")
    if document_id:
        clauses.append("c.document_id = ?")
        params.append(document_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.document_id, c.chunk_index, c.language, c.text, c.embedding, c.metadata,
                   d.title_en, d.title_hi, d.title_mr, d.publisher, d.source_name, d.source_url,
                   d.publication_date, d.source_date_note, d.licence, d.category, d.crops, d.states,
                   d.approval_status, d.is_demo, d.content_note, d.version
            FROM chunks c JOIN documents d ON d.id = c.document_id
            {where}
            ORDER BY c.document_id, c.language, c.chunk_index
            """,
            params,
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json_loads(item.get("metadata"), {})
        item["crops"] = json_loads(item.get("crops"), [])
        item["states"] = json_loads(item.get("states"), [])
        item["is_demo"] = bool(item.get("is_demo"))
        result.append(item)
    return result


def document_stats() -> dict[str, Any]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        approved = conn.execute("SELECT COUNT(*) FROM documents WHERE approval_status = 'approved'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM documents WHERE approval_status = 'pending'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM documents WHERE approval_status = 'rejected'").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        demo = conn.execute("SELECT COUNT(*) FROM documents WHERE is_demo = 1").fetchone()[0]
        categories = conn.execute("SELECT category, COUNT(*) as count FROM documents GROUP BY category").fetchall()
    return {
        "documents": total,
        "approved": approved,
        "pending": pending,
        "rejected": rejected,
        "chunks": chunks,
        "demo_documents": demo,
        "categories": [dict(row) for row in categories],
    }


def log_query(payload: dict[str, Any]) -> str:
    # The pipeline exposes the identifier as "query_id"; accept both names so
    # history, feedback and review all refer to the same row.
    query_id = payload.get("id") or payload.get("query_id") or f"qry_{uuid.uuid4().hex[:14]}"
    now = payload.get("created_at") or iso_now()
    values = {
        "id": query_id,
        "created_at": now,
        "text": payload.get("text", ""),
        "language": payload.get("language", "en"),
        "detected_language": payload.get("detected_language", "en"),
        "intent": payload.get("intent", "other"),
        "intent_confidence": float(payload.get("intent_confidence", 0)),
        "entities": json_dumps(payload.get("entities", {})),
        "decision": payload.get("decision", "refuse"),
        "confidence": float(payload.get("confidence", 0)),
        "reason_code": payload.get("reason_code", ""),
        "reason_detail": payload.get("reason_detail", ""),
        "answer": payload.get("answer", ""),
        "evidence": json_dumps(payload.get("evidence", [])),
        "tool_data": json_dumps(payload.get("tool_data", {})),
        "signals": json_dumps(payload.get("signals", {})),
        "latency_ms": float(payload.get("latency_ms", 0)),
        "generation_provider": payload.get("generation_provider", ""),
        "input_mode": payload.get("input_mode", "text"),
        "asr_confidence": payload.get("asr_confidence"),
        "crop": payload.get("crop", ""),
        "state": payload.get("state", "Maharashtra"),
        "district": payload.get("district", ""),
        "simulated": int(bool(payload.get("simulated", False))),
        "data_mode": payload.get("data_mode", ""),
        "user_id": payload.get("user_id", ""),
        "session_id": payload.get("session_id", ""),
    }
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with get_conn() as conn:
        conn.execute(f"INSERT INTO queries ({columns}) VALUES ({placeholders})", tuple(values.values()))
    return query_id


def _query_from_row(row: sqlite3.Row, include_answer: bool = True) -> dict[str, Any]:
    item = dict(row)
    for key in ("entities", "evidence", "tool_data", "signals"):
        item[key] = json_loads(item.get(key), {} if key in {"entities", "tool_data", "signals"} else [])
    item["simulated"] = bool(item.get("simulated"))
    if not include_answer:
        item.pop("answer", None)
        item.pop("evidence", None)
    return item


def list_queries(
    limit: int = 50,
    offset: int = 0,
    decision: str | None = None,
    language: str | None = None,
    q: str = "",
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    params: list[Any] = []
    if decision:
        clauses.append("decision = ?")
        params.append(decision)
    if language:
        clauses.append("language = ?")
        params.append(language)
    if q:
        clauses.append("(lower(text) LIKE ? OR lower(answer) LIKE ?)")
        like = f"%{q.lower()}%"
        params.extend([like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM queries {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM queries {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    return [_query_from_row(row, include_answer=False) for row in rows], total


def get_query(query_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM queries WHERE id = ?", (query_id,)).fetchone()
        if not row:
            return None
        query = _query_from_row(row)
        feedback_rows = conn.execute(
            "SELECT * FROM feedback WHERE query_id = ? ORDER BY created_at DESC", (query_id,)
        ).fetchall()
        query["feedback"] = [dict(item) for item in feedback_rows]
        return query


def mark_query_review(query_id: str, status: str, note: str = "", corrected_answer: str = "", reviewer: str = "admin") -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE queries SET review_status = ?, review_note = ?, corrected_answer = ?, reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (status, note, corrected_answer, iso_now(), reviewer, query_id),
        )
        changed = cursor.rowcount > 0
    if changed:
        audit("query_reviewed", "query", query_id, json_dumps({"status": status, "note": note, "reviewer": reviewer}), reviewer)
    return changed


def add_feedback(query_id: str, rating: str, comment: str = "") -> dict[str, Any]:
    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
    created = iso_now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO feedback (id, query_id, rating, comment, created_at) VALUES (?,?,?,?,?)",
            (feedback_id, query_id, rating, comment, created),
        )
    audit("feedback_received", "query", query_id, json_dumps({"rating": rating}))
    return {"id": feedback_id, "query_id": query_id, "rating": rating, "comment": comment, "created_at": created, "review_status": "new"}


def list_feedback(limit: int = 100, rating: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if rating:
        clauses.append("f.rating = ?")
        params.append(rating)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT f.*, q.text as query_text, q.answer as query_answer, q.language as query_language,
                   q.decision as query_decision
            FROM feedback f LEFT JOIN queries q ON q.id = f.query_id
            {where} ORDER BY f.created_at DESC LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_feedback_review(feedback_id: str, reviewer: str = "admin") -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE feedback SET review_status = 'reviewed', reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (iso_now(), reviewer, feedback_id),
        )
        return cursor.rowcount > 0


def query_stats() -> dict[str, Any]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
        answered = conn.execute("SELECT COUNT(*) FROM queries WHERE decision = 'answer'").fetchone()[0]
        refused = conn.execute("SELECT COUNT(*) FROM queries WHERE decision = 'refuse'").fetchone()[0]
        asked = conn.execute("SELECT COUNT(*) FROM queries WHERE decision = 'ask_to_repeat'").fetchone()[0]
        avg_latency = conn.execute("SELECT AVG(latency_ms) FROM queries").fetchone()[0] or 0
        feedback_up = conn.execute("SELECT COUNT(*) FROM feedback WHERE rating = 'up'").fetchone()[0]
        feedback_down = conn.execute("SELECT COUNT(*) FROM feedback WHERE rating = 'down'").fetchone()[0]
        unreviewed = conn.execute("SELECT COUNT(*) FROM queries WHERE decision = 'refuse' AND review_status = 'unreviewed'").fetchone()[0]
        last = conn.execute("SELECT created_at FROM queries ORDER BY created_at DESC LIMIT 1").fetchone()
        by_language = conn.execute("SELECT language, COUNT(*) as count FROM queries GROUP BY language").fetchall()
    return {
        "total_queries": total,
        "answered": answered,
        "refused": refused,
        "ask_to_repeat": asked,
        "avg_latency_ms": round(avg_latency, 1),
        "feedback_up": feedback_up,
        "feedback_down": feedback_down,
        "unreviewed_refusals": unreviewed,
        "last_query_at": last[0] if last else None,
        "by_language": [dict(row) for row in by_language],
    }


def list_glossary() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM glossary ORDER BY category, term_en").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["aliases"] = json_loads(item.get("aliases"), [])
        result.append(item)
    return result


def seed_glossary(entries: list[dict[str, Any]]) -> int:
    now = iso_now()
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
        if count:
            return 0
        conn.executemany(
            "INSERT INTO glossary (term_en, term_hi, term_mr, category, aliases, notes, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    entry["term_en"],
                    entry.get("term_hi", ""),
                    entry.get("term_mr", ""),
                    entry.get("category", "general"),
                    json_dumps(entry.get("aliases", [])),
                    entry.get("notes", ""),
                    now,
                    now,
                )
                for entry in entries
            ],
        )
    return len(entries)


def upsert_glossary(entry: dict[str, Any]) -> dict[str, Any]:
    now = iso_now()
    aliases = entry.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [item.strip() for item in aliases.split(",") if item.strip()]
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM glossary WHERE term_en = ?", (entry["term_en"],)).fetchone()
        if existing:
            conn.execute(
                "UPDATE glossary SET term_hi = ?, term_mr = ?, category = ?, aliases = ?, notes = ?, updated_at = ? WHERE id = ?",
                (
                    entry.get("term_hi", ""),
                    entry.get("term_mr", ""),
                    entry.get("category", "general"),
                    json_dumps(aliases),
                    entry.get("notes", ""),
                    now,
                    existing["id"],
                ),
            )
            glossary_id = existing["id"]
        else:
            cursor = conn.execute(
                "INSERT INTO glossary (term_en, term_hi, term_mr, category, aliases, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    entry["term_en"],
                    entry.get("term_hi", ""),
                    entry.get("term_mr", ""),
                    entry.get("category", "general"),
                    json_dumps(aliases),
                    entry.get("notes", ""),
                    now,
                    now,
                ),
            )
            glossary_id = cursor.lastrowid
    audit("glossary_upserted", "glossary", str(glossary_id), entry["term_en"])
    return {"id": glossary_id, **entry, "aliases": aliases, "created_at": now, "updated_at": now}


def delete_glossary(glossary_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM glossary WHERE id = ?", (glossary_id,))
        changed = cursor.rowcount > 0
    if changed:
        audit("glossary_deleted", "glossary", str(glossary_id))
    return changed


def save_eval_run(run: dict[str, Any]) -> str:
    run_id = run.get("id") or f"eval_{uuid.uuid4().hex[:12]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO eval_runs (id, created_at, dataset_version, metrics, cases, duration_ms, status, notes) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                run.get("created_at", iso_now()),
                run.get("dataset_version", ""),
                json_dumps(run.get("metrics", {})),
                json_dumps(run.get("cases", [])),
                float(run.get("duration_ms", 0)),
                run.get("status", "completed"),
                run.get("notes", ""),
            ),
        )
    return run_id


def list_eval_runs(limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, created_at, dataset_version, metrics, duration_ms, status, notes FROM eval_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **dict(row),
            "metrics": json_loads(row["metrics"], {}),
        }
        for row in rows
    ]


def get_eval_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    return {
        **dict(row),
        "metrics": json_loads(row["metrics"], {}),
        "cases": json_loads(row["cases"], []),
    }


def list_audit(limit: int = 100) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def get_counts() -> dict[str, int]:
    with get_conn() as conn:
        return {
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "queries": conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0],
            "feedback": conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0],
            "eval_runs": conn.execute("SELECT COUNT(*) FROM eval_runs").fetchone()[0],
        }
