"""Farmer assistant, history, feedback, tools and speech endpoints."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse

from .. import db
from ..schemas import FeedbackRequest, QueryRequest, QueryResponse, SynthesisRequest
from ..services.container import AppContainer
from ..services.mandi import COMMODITIES, MARKET_NAMES
from ..services.speech import SpeechUnavailable
from ..services.weather import DISTRICTS
from .deps import get_services

logger = logging.getLogger(__name__)
router = APIRouter(tags=["assistant"])


@router.post("/assistant/query", response_model=QueryResponse)
def query(request: QueryRequest, services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    try:
        return services.pipeline.answer(
            request.text,
            language=request.language,
            crop=request.crop,
            state=request.state,
            district=request.district,
            input_mode=request.input_mode,
            asr_confidence=request.asr_confidence,
            user_id=request.user_id,
            session_id=request.session_id,
        )
    except Exception as exc:  # keep internal details out of the public error
        logger.exception("Query pipeline failed")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {type(exc).__name__}") from exc


@router.get("/history")
def history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    decision: Optional[str] = Query(None, pattern="^(answer|ask_to_repeat|refuse)$"),
    language: Optional[str] = Query(None, pattern="^(hi|mr|en)$"),
    q: str = "",
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    items, total = db.list_queries(limit=limit, offset=offset, decision=decision, language=language, q=q)
    return {"items": items, "total": total, "limit": limit, "offset": offset, "stats": db.query_stats()}


@router.get("/history/{query_id}")
def history_detail(query_id: str, services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    item = db.get_query(query_id)
    if not item:
        raise HTTPException(status_code=404, detail="Query not found")
    return item


@router.post("/feedback")
def feedback(request: FeedbackRequest, services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    if not db.get_query(request.query_id):
        raise HTTPException(status_code=404, detail="Query not found")
    return db.add_feedback(request.query_id, request.rating, request.comment)


@router.get("/tools/mandi")
def mandi_price(
    commodity: str = Query(..., min_length=2, max_length=60),
    market: Optional[str] = Query(None, max_length=80),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    return services.mandi.lookup(commodity, market=market)


@router.get("/tools/weather")
def weather(
    district: str = Query("Nashik", min_length=2, max_length=80),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    return services.weather.lookup(district)


@router.get("/tools/catalog")
def tool_catalog(services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    return {
        "commodities": services.mandi.commodities(),
        "markets": sorted(set(MARKET_NAMES.values())),
        "districts": services.weather.districts(),
        "mandi_mode": "live" if services.mandi.live_enabled else "simulated",
        "weather_mode": "live-with-fallback" if services.weather.provider != "demo" else "simulated",
    }


@router.get("/speech/info")
def speech_info(services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    return services.speech.info()


@router.post("/speech/transcribe")
def transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    data = file.file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file is larger than 15 MB")
    try:
        result = services.speech.transcribe(data, file.filename or "upload.webm", language=language)
        return {**result, "input_mode": "voice_upload"}
    except SpeechUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": "ASR_UNAVAILABLE",
                "message": exc.message,
                "provider": exc.provider,
                "fallback": "Use the browser microphone (Web Speech API) or type the question.",
            },
        )


@router.post("/speech/synthesize")
async def synthesize(request: SynthesisRequest, services: AppContainer = Depends(get_services)) -> Response:
    try:
        result = await services.speech.synthesize(request.text, request.language)
        return Response(
            content=result["audio"],
            media_type=result["mime_type"],
            headers={
                "X-TTS-Provider": result["provider"],
                "X-TTS-Voice": result["voice"],
                "X-TTS-Cached": str(result["cached"]).lower(),
                "Cache-Control": "public, max-age=86400",
            },
        )
    except SpeechUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": "TTS_UNAVAILABLE",
                "message": exc.message,
                "provider": exc.provider,
                "fallback": "Use the browser Play audio button (SpeechSynthesis API).",
            },
        )
