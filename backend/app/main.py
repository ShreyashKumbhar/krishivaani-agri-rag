"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, assistant, evaluation, knowledge
from .config import settings
from .services.container import create_container

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

SAMPLE_QUESTIONS = {
    "en": [
        "Why are the leaves of my cotton crop turning yellow?",
        "How can I identify pests affecting soybean?",
        "What is the current onion mandi price?",
        "Which government schemes are available for farmers?",
        "What precautions should I take when using pesticides?",
        "Will it rain in Nashik today?",
    ],
    "hi": [
        "मेरी कपास की पत्तियाँ पीली क्यों हो रही हैं?",
        "सोयाबीन में कीटों की पहचान कैसे करें?",
        "प्याज का आज का मंडी भाव क्या है?",
        "किसानों के लिए कौन सी सरकारी योजनाएँ उपलब्ध हैं?",
        "कीटनाशक का उपयोग करते समय क्या सावधानियाँ बरतें?",
        "नाशिक में आज बारिश होगी?",
    ],
    "mr": [
        "माझ्या कापसाची पाने पिवळी का होत आहेत?",
        "सोयाबीनवरील कीटक कसे ओळखावे?",
        "कांद्याचा आजचा बाजार भाव काय आहे?",
        "शेतकऱ्यांसाठी कोणत्या सरकारी योजना आहेत?",
        "कीटकनाशक वापरताना कोणती काळजी घ्यावी?",
        "नाशिकमध्ये आज पाऊस पडेल का?",
    ],
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.app_name, settings.version)
    services = create_container()
    app.state.services = services
    logger.info(
        "Ready: %s documents, %s chunks, LLM=%s, mandi=%s, weather=%s",
        services.retriever.stats()["documents"],
        services.retriever.stats()["chunks"],
        services.composer.llm.name,
        "live" if services.mandi.live_enabled else "simulated",
        services.weather.provider,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title="KrishiVaani API",
    version=settings.version,
    description=(
        "Voice-first multilingual agricultural assistant for Hindi and Marathi farmers. "
        "The bundled knowledge base is a demonstration corpus, not official ICAR/KVK advice. "
        "Mandi data is simulated unless configured; weather uses Open-Meteo with a labelled fallback."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-TTS-Provider", "X-TTS-Voice", "X-TTS-Cached"],
)

for router in (assistant.router, knowledge.router, admin.router, evaluation.router):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/api/health", tags=["system"])
def health(request: Request) -> dict[str, Any]:
    services = request.app.state.services
    stats = services.retriever.stats()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "documents": stats["documents"],
        "chunks": stats["chunks"],
        "languages": stats["languages"],
        "llm": {
            "provider": services.composer.llm.name,
            "mode": services.composer.llm.mode,
            "available": services.composer.llm.available,
        },
        "embedding": services.embeddings.info(),
        "mandi_mode": "live" if services.mandi.live_enabled else "simulated",
        "weather_mode": "live-with-fallback" if services.weather.provider != "demo" else "simulated",
        "speech": services.speech.info(),
        "demo_notice": settings.demo_notice,
    }


@app.get("/api/config", tags=["system"])
def config(request: Request) -> dict[str, Any]:
    services = request.app.state.services
    return {
        "app": {"name": settings.app_name, "subtitle": settings.app_subtitle, "version": settings.version},
        "languages": [
            {"code": "hi", "name": "हिंदी", "english": "Hindi", "speech": "hi-IN", "voice": settings.edge_voice_hi},
            {"code": "mr", "name": "मराठी", "english": "Marathi", "speech": "mr-IN", "voice": settings.edge_voice_mr},
            {"code": "en", "name": "English", "english": "English", "speech": "en-IN", "voice": settings.edge_voice_en},
        ],
        "sample_questions": SAMPLE_QUESTIONS,
        "crops": ["cotton", "soybean", "onion", "tomato", "grapes", "sugarcane"],
        "districts": services.weather.districts(),
        "providers": {
            "llm": {
                "provider": services.composer.llm.name,
                "mode": services.composer.llm.mode,
                "available": services.composer.llm.available,
                "honesty_note": (
                    "No LLM key is configured. Answers come from the deterministic grounded template composer, not an LLM."
                    if not services.composer.llm.available
                    else "A hosted/local LLM is configured. Every answer reports the provider used."
                ),
            },
            "embedding": services.embeddings.info(),
            "speech": services.speech.info(),
            "mandi": {
                "mode": "live" if services.mandi.live_enabled else "simulated",
                "provider": "data.gov.in Agmarknet adapter" if services.mandi.live_enabled else "Demo mandi fixture v1",
            },
            "weather": {
                "mode": "live-with-fallback" if services.weather.provider != "demo" else "simulated",
                "provider": "Open-Meteo" if services.weather.provider != "demo" else "Demo weather fixture v1",
            },
        },
        "safety": {
            "chemical_dosage_blocked": True,
            "helpline": "1800-180-1551",
            "thresholds": {
                "min_retrieval_score": settings.min_retrieval_score,
                "min_evidence_coverage": settings.min_evidence_coverage,
                "min_answer_confidence": settings.min_answer_confidence,
            },
        },
        "demo_notice": settings.demo_notice,
    }


@app.get("/api/samples", tags=["system"])
def samples(language: str = "en") -> dict[str, Any]:
    return {"language": language, "questions": SAMPLE_QUESTIONS.get(language, SAMPLE_QUESTIONS["en"])}


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Internal error: {type(exc).__name__}"})


# Serve the built React app when it exists. In development, Vite runs on :5173
# and proxies /api to this server.
_dist = Path(settings.frontend_dist)
if _dist.exists() and (_dist / "index.html").exists():
    assets_dir = _dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = _dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root() -> dict[str, Any]:
        return {
            "app": settings.app_name,
            "message": "API is running. The frontend build was not found; run `npm run dev` in frontend/ or build it with `npm run build`.",
            "docs": "/docs",
            "health": "/api/health",
        }
