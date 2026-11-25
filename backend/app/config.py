"""Central configuration for the KrishiVaani backend.

All external integrations are optional. The defaults run fully offline on a
normal laptop using a deterministic grounded composer, local hashed
embeddings, simulated mandi data and (when the network is available) the
free Open-Meteo forecast API.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _path(name: str, default: Path) -> Path:
    """Resolve a configured path against the project root, not the shell CWD."""
    raw = os.getenv(name)
    if not raw:
        return default
    candidate = Path(raw).expanduser()
    return candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()


@dataclass(frozen=True)
class Settings:
    app_name: str = "KrishiVaani"
    app_subtitle: str = "Voice-First Multilingual Agricultural Assistant"
    version: str = "1.0.0"
    api_prefix: str = "/api"

    data_dir: Path = field(default_factory=lambda: BACKEND_ROOT / "data")
    db_path: Path = field(default_factory=lambda: _path("AGRI_DB_PATH", BACKEND_ROOT / "data" / "agrivaani.db"))
    seed_path: Path = field(default_factory=lambda: BACKEND_ROOT / "data" / "seed_documents.json")
    glossary_seed_path: Path = field(default_factory=lambda: BACKEND_ROOT / "data" / "glossary_seed.json")
    eval_path: Path = field(default_factory=lambda: BACKEND_ROOT / "data" / "eval" / "evaluation_cases.json")
    docs_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "docs")
    frontend_dist: Path = field(default_factory=lambda: PROJECT_ROOT / "frontend" / "dist")
    tts_cache_dir: Path = field(default_factory=lambda: BACKEND_ROOT / "data" / "tts_cache")
    upload_dir: Path = field(default_factory=lambda: BACKEND_ROOT / "data" / "uploads")

    # Generation
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "template").strip().lower())
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "").strip())
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip())
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip())
    llm_timeout_seconds: int = field(default_factory=lambda: _int("LLM_TIMEOUT_SECONDS", 45))

    # Embeddings
    embedding_provider: str = field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "hashed").strip().lower())
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    embedding_dim: int = field(default_factory=lambda: _int("EMBEDDING_DIM", 384))

    # Speech
    tts_provider: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER", "edge").strip().lower())
    edge_voice_hi: str = field(default_factory=lambda: os.getenv("EDGE_VOICE_HI", "hi-IN-SwaraNeural"))
    edge_voice_mr: str = field(default_factory=lambda: os.getenv("EDGE_VOICE_MR", "mr-IN-AarohiNeural"))
    edge_voice_en: str = field(default_factory=lambda: os.getenv("EDGE_VOICE_EN", "en-IN-NeerjaNeural"))
    asr_provider: str = field(default_factory=lambda: os.getenv("ASR_PROVIDER", "browser").strip().lower())
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "small"))
    whisper_device: str = field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8"))

    # Tools
    mandi_provider: str = field(default_factory=lambda: os.getenv("MANDI_PROVIDER", "demo").strip().lower())
    data_gov_in_api_key: str = field(default_factory=lambda: os.getenv("DATA_GOV_IN_API_KEY", "").strip())
    mandi_resource_id: str = field(default_factory=lambda: os.getenv("MANDI_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070").strip())
    weather_provider: str = field(default_factory=lambda: os.getenv("WEATHER_PROVIDER", "open-meteo").strip().lower())
    weather_timeout_seconds: int = field(default_factory=lambda: _int("WEATHER_TIMEOUT_SECONDS", 12))

    # Retrieval / confidence
    retrieval_top_k: int = field(default_factory=lambda: _int("RETRIEVAL_TOP_K", 8))
    evidence_top_k: int = field(default_factory=lambda: _int("EVIDENCE_TOP_K", 4))
    rrf_k: int = field(default_factory=lambda: _int("RRF_K", 60))
    min_retrieval_score: float = field(default_factory=lambda: _float("MIN_RETRIEVAL_SCORE", 0.30))
    min_evidence_coverage: float = field(default_factory=lambda: _float("MIN_EVIDENCE_COVERAGE", 0.22))
    min_answer_confidence: float = field(default_factory=lambda: _float("MIN_ANSWER_CONFIDENCE", 0.52))

    # Platform
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip()
            for item in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000",
            ).split(",")
            if item.strip()
        )
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    admin_username: str = field(default_factory=lambda: os.getenv("ADMIN_USERNAME", "admin").strip())
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "krishivaani-admin").strip())
    admin_token: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN", "").strip())
    demo_notice: str = (
        "Demonstration system. The bundled knowledge base contains curated demo summaries, "
        "not official ICAR/KVK advisories. Mandi data is simulated unless a data.gov.in key is configured. "
        "Weather is a live Open-Meteo forecast when the network is available."
    )

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.tts_cache_dir, self.upload_dir, self.db_path.parent):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def llm_mode(self) -> str:
        if self.llm_provider in {"openai", "openai-compatible"} and self.openai_api_key:
            return "hosted-llm"
        if self.llm_provider == "ollama":
            return "local-llm"
        return "deterministic-fallback"

    @property
    def mandi_live(self) -> bool:
        return self.mandi_provider in {"data_gov_in", "agmarknet"} and bool(self.data_gov_in_api_key)


settings = Settings()
settings.ensure_dirs()
