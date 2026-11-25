"""Admin console, expert review, feedback and glossary endpoints."""
from __future__ import annotations

from typing import Any, Optional

import hmac

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..config import settings
from ..schemas import AdminLoginRequest, GlossaryEntryRequest, ReviewRequest
from ..services.container import AppContainer
from .deps import create_admin_token, get_services, optional_admin, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login")
def login(request: AdminLoginRequest) -> dict[str, Any]:
    if request.token and settings.admin_token and hmac.compare_digest(request.token, settings.admin_token):
        return {"authenticated": True, "token": create_admin_token(settings.admin_username), "username": settings.admin_username}
    if hmac.compare_digest(request.username, settings.admin_username) and hmac.compare_digest(request.password, settings.admin_password):
        token = create_admin_token(settings.admin_username)
        return {"authenticated": True, "token": token, "username": settings.admin_username}
    raise HTTPException(status_code=401, detail="Invalid admin credentials")


@router.get("/auth/status")
def auth_status(admin_user: str | None = Depends(optional_admin)) -> dict[str, Any]:
    return {"auth_required": True, "authenticated": bool(admin_user), "username": admin_user}


@router.get("/overview")
def overview(services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    runs = db.list_eval_runs(limit=1)
    return {
        "queries": db.query_stats(),
        "documents": db.document_stats(),
        "retrieval": services.retriever.stats(),
        "latest_evaluation": runs[0] if runs else None,
        "recent_feedback": db.list_feedback(limit=5),
        "recent_refusals": db.list_queries(limit=5, decision="refuse")[0],
        "recent_audit": db.list_audit(limit=8),
        "demo_notice": settings.demo_notice,
    }


@router.get("/queries")
def queries(
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    decision: Optional[str] = Query(None, pattern="^(answer|ask_to_repeat|refuse)$"),
    language: Optional[str] = Query(None, pattern="^(hi|mr|en)$"),
    q: str = "",
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    items, total = db.list_queries(limit=limit, offset=offset, decision=decision, language=language, q=q)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/refusals")
def refusals(
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    items, total = db.list_queries(limit=limit, offset=offset, decision="refuse")
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/queries/{query_id}/review")
def review_query(
    query_id: str,
    request: ReviewRequest,
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    if not db.get_query(query_id):
        raise HTTPException(status_code=404, detail="Query not found")
    if not db.mark_query_review(query_id, request.status, request.note, request.corrected_answer, request.reviewer or admin_user):
        raise HTTPException(status_code=400, detail="Review update failed")
    return db.get_query(query_id) or {}


@router.get("/feedback")
def feedback(
    limit: int = Query(100, ge=1, le=300),
    rating: Optional[str] = Query(None, pattern="^(up|down)$"),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    return {"items": db.list_feedback(limit=limit, rating=rating)}


@router.post("/feedback/{feedback_id}/review")
def review_feedback(
    feedback_id: str,
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    if not db.mark_feedback_review(feedback_id):
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"reviewed": True, "id": feedback_id}


@router.get("/glossary")
def glossary(services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    return {"items": db.list_glossary(), "counts": services.glossary.counts(), "total": len(services.glossary.entries)}


@router.post("/glossary")
def upsert_glossary(
    request: GlossaryEntryRequest,
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    item = db.upsert_glossary(request.model_dump())
    services.glossary.reload()
    services.refresh_index("glossary_updated")
    return item


@router.delete("/glossary/{glossary_id}")
def delete_glossary(
    glossary_id: int,
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    if not db.delete_glossary(glossary_id):
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    services.glossary.reload()
    services.refresh_index("glossary_deleted")
    return {"deleted": True, "id": glossary_id}


@router.get("/audit")
def audit(limit: int = Query(100, ge=1, le=500), services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    return {"items": db.list_audit(limit=limit)}


@router.get("/system")
def system(services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    return services.status()


@router.get("/safety")
def safety() -> dict[str, Any]:
    return {
        "decision_policy": {
            "refuse": [
                "chemical dosage or pesticide dose request",
                "out-of-scope or adversarial request",
                "no approved evidence",
                "retrieval score or evidence coverage below threshold",
                "combined confidence below answer threshold",
            ],
            "ask_to_repeat": [
                "missing commodity for a market-price question",
                "missing district for a weather question",
                "ambiguous question with no crop/subject",
                "low ASR confidence",
            ],
            "answer": ["approved evidence passes retrieval, coverage and confidence thresholds", "labelled live/simulated tool result"],
        },
        "thresholds": {
            "min_retrieval_score": settings.min_retrieval_score,
            "min_evidence_coverage": settings.min_evidence_coverage,
            "min_answer_confidence": settings.min_answer_confidence,
            "rrf_k": settings.rrf_k,
            "retrieval_top_k": settings.retrieval_top_k,
            "evidence_top_k": settings.evidence_top_k,
        },
        "chemical_dosage_policy": "Blocked. The assistant never gives a pesticide or chemical dose number; it refers to the product label, CIB&RC and KVK/Kisan Call Centre.",
        "helplines": {"kisan_call_centre": "1800-180-1551", "kvk_portal": "https://kvk.icar.gov.in/"},
        "disclaimer": "Informational guidance only; not a substitute for a certified agronomist or official bulletin.",
    }


@router.get("/sources")
def sources(limit: int = Query(200, ge=1, le=300), services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    items, total = db.list_documents(limit=limit)
    return {
        "items": [
            {
                "id": item["id"],
                "title": item["title_en"],
                "publisher": item["publisher"],
                "source_name": item["source_name"],
                "source_url": item["source_url"],
                "publication_date": item["publication_date"],
                "licence": item["licence"],
                "is_demo": item["is_demo"],
                "approval_status": item["approval_status"],
                "content_note": item["content_note"],
            }
            for item in items
        ],
        "total": total,
    }
