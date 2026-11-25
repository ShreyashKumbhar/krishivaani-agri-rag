"""Knowledge-base management endpoints (documents, upload, approval)."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from .. import db
from ..schemas import DocumentStatusRequest
from ..services.container import AppContainer
from ..services.ingestion import ingest_upload
from .deps import get_services, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/documents")
def documents(
    q: str = "",
    status: Optional[str] = Query(None, pattern="^(approved|pending|rejected|superseded)$"),
    category: Optional[str] = None,
    crop: Optional[str] = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    items, total = db.list_documents(q=q, status=status, category=category, crop=crop, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset, "stats": db.document_stats()}


@router.get("/stats")
def stats(services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    return {"documents": db.document_stats(), "retrieval": services.retriever.stats()}


@router.get("/documents/{document_id}")
def document(document_id: str, services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    item = db.get_document(document_id, include_chunks=True)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return item


@router.get("/documents/{document_id}/versions")
def document_versions(document_id: str, services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    item = db.get_document(document_id, include_chunks=False)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document_id": document_id, "versions": db.list_document_versions(document_id)}


@router.post("/upload")
def upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    publisher: str = Form("Admin upload"),
    source_name: str = Form("Admin upload"),
    source_url: str = Form(""),
    publication_date: str = Form(""),
    licence: str = Form("Not specified by uploader"),
    category: str = Form("crop_advice"),
    crops: str = Form("all"),
    states: str = Form("Maharashtra"),
    content_note: str = Form("Uploaded by an administrator. Approval is required before retrieval."),
    approval_status: str = Form("pending"),
    parent_id: str = Form(""),
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    data = file.file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File is larger than 20 MB")
    if approval_status not in {"pending", "approved"}:
        approval_status = "pending"
    metadata = {
        "title": title,
        "publisher": publisher,
        "source_name": source_name,
        "source_url": source_url,
        "publication_date": publication_date,
        "licence": licence,
        "category": category,
        "crops": crops,
        "states": states,
        "content_note": content_note,
        "approval_status": approval_status,
        "parent_id": parent_id,
        "mime_type": file.content_type or "",
    }
    try:
        item = ingest_upload(file.filename or "upload.txt", data, metadata, services.glossary, services.embeddings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"Upload failed: {type(exc).__name__}") from exc
    if approval_status == "approved":
        services.refresh_index("document_uploaded_approved")
    db.audit("document_uploaded", "document", item["id"], f"status={approval_status}; version={item.get('version')}; file={file.filename}", actor=admin_user)
    return item


@router.post("/documents/{document_id}/status")
def set_status(
    document_id: str,
    request: DocumentStatusRequest,
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    item = db.get_document(document_id, include_chunks=False)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    reviewer = request.reviewer or admin_user
    if not db.set_document_status(document_id, request.status, reviewer, request.note):
        raise HTTPException(status_code=400, detail="Status update failed")
    services.refresh_index(f"document_{request.status}")
    return db.get_document(document_id, include_chunks=False) or {}


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    item = db.get_document(document_id, include_chunks=False)
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    if not db.delete_document(document_id):
        raise HTTPException(status_code=400, detail="Delete failed")
    services.refresh_index("document_deleted")
    return {"deleted": True, "id": document_id}


@router.post("/reindex")
def reindex(
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    count = services.refresh_index("admin_reindex")
    return {"reindexed": True, "chunks": count, "stats": services.retriever.stats()}
