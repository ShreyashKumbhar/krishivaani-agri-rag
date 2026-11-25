"""Application service container and startup bootstrap."""
from __future__ import annotations

from typing import Any

from .. import db
from ..config import settings
from ..utils import iso_now
from .embeddings import EmbeddingService
from .evaluation import load_dataset
from .generation import GroundedComposer
from .glossary import Glossary
from .ingestion import seed_documents
from .mandi import MandiService
from .pipeline import AssistantPipeline
from .retrieval import HybridRetriever
from .speech import SpeechService
from .weather import WeatherService


class AppContainer:
    def __init__(self) -> None:
        db.init_db()
        self.glossary = Glossary()
        self.embeddings = EmbeddingService(self.glossary)
        self.seed_result = seed_documents(self.glossary, self.embeddings)
        self.retriever = HybridRetriever(self.glossary, self.embeddings)
        self.mandi = MandiService()
        self.weather = WeatherService()
        self.composer = GroundedComposer(self.glossary)
        self.pipeline = AssistantPipeline(
            self.glossary,
            self.embeddings,
            self.retriever,
            self.mandi,
            self.weather,
            self.composer,
        )
        self.speech = SpeechService()
        self.started_at = iso_now()

    def refresh_index(self, reason: str = "manual") -> int:
        return self.retriever.refresh(reason)

    def status(self) -> dict[str, Any]:
        counts = db.get_counts()
        return {
            "app": settings.app_name,
            "version": settings.version,
            "started_at": self.started_at,
            "database": str(settings.db_path),
            "counts": counts,
            "documents": db.document_stats(),
            "retrieval": self.retriever.stats(),
            "generation": {
                "provider": self.composer.llm.name,
                "mode": self.composer.llm.mode,
                "available": self.composer.llm.available,
                "note": (
                    "No LLM credentials configured; answers use the deterministic grounded template composer."
                    if not self.composer.llm.available
                    else "Hosted/local LLM configured; outputs are checked against retrieved evidence."
                ),
            },
            "speech": self.speech.info(),
            "tools": {
                "mandi": {
                    "configured_provider": settings.mandi_provider,
                    "live": self.mandi.live_enabled,
                    "mode": "live" if self.mandi.live_enabled else "simulated",
                    "note": "Set MANDI_PROVIDER=data_gov_in and DATA_GOV_IN_API_KEY to enable the live adapter.",
                },
                "weather": {
                    "configured_provider": settings.weather_provider,
                    "mode": "live-with-fallback" if settings.weather_provider != "demo" else "simulated",
                    "note": "Open-Meteo is a free forecast API; it is not an IMD Agromet bulletin.",
                },
            },
            "evaluation": {
                "dataset": load_dataset().get("version"),
                "cases": len(load_dataset().get("cases", [])),
            },
            "demo_notice": settings.demo_notice,
        }


def create_container() -> AppContainer:
    return AppContainer()
