"""End-to-end assistant pipeline."""
from __future__ import annotations

import time
import uuid
from typing import Any

from .. import db
from ..config import settings
from ..utils import clamp, iso_now, normalize_text
from .confidence import gate
from .embeddings import EmbeddingService
from .generation import (
    GroundedComposer,
    clarify_message,
    disclaimer,
    followups,
    refusal_message,
    safety_note,
)
from .glossary import Glossary
from .language import language_name
from .mandi import COMMODITIES, MARKET_NAMES, MandiService
from .query_understanding import understand
from .retrieval import CATEGORY_BY_INTENT, HybridRetriever
from .weather import WeatherService


class AssistantPipeline:
    def __init__(
        self,
        glossary: Glossary,
        embeddings: EmbeddingService,
        retriever: HybridRetriever,
        mandi: MandiService,
        weather: WeatherService,
        composer: GroundedComposer,
    ) -> None:
        self.glossary = glossary
        self.embeddings = embeddings
        self.retriever = retriever
        self.mandi = mandi
        self.weather = weather
        self.composer = composer

    def answer(
        self,
        text: str,
        language: str | None = None,
        crop: str | None = None,
        state: str = "Maharashtra",
        district: str | None = None,
        input_mode: str = "text",
        asr_confidence: float | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        log: bool = True,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        text = normalize_text(text)
        understanding = understand(
            text,
            requested_language=language,
            crop_hint=crop,
            district_hint=district,
            glossary=self.glossary,
        )
        lang = understanding.language
        intent = understanding.intent
        entities = understanding.entities
        resolved_crop = (entities.get("crop") or crop or "").lower() or None
        resolved_district = entities.get("district") or district

        evidence: list[dict[str, Any]] = []
        tool_data: dict[str, Any] | None = None
        tool_name: str | None = None
        retrieval_meta: dict[str, Any] = {}

        needs_retrieval = (
            not understanding.is_chemical_dosage
            and not understanding.is_out_of_scope
            and intent not in {"other"}
            and understanding.missing is None
            and not understanding.is_ambiguous
        )
        if needs_retrieval and intent == "market_price" and not understanding.market_informational:
            commodity = resolved_crop
            if not commodity:
                for key in COMMODITIES:
                    if key in text.lower() or self.glossary.localize(key, lang).lower() in text.lower():
                        commodity = key
                        break
            market = None
            for key, value in MARKET_NAMES.items():
                if key in text.lower():
                    market = value
                    break
            tool_name = "mandi"
            tool_data = self.mandi.lookup(commodity, market=market, state=state)
        elif needs_retrieval and intent == "weather" and not understanding.agromet_informational:
            tool_name = "weather"
            tool_data = self.weather.lookup(resolved_district or "Nashik")
        elif needs_retrieval:
            category = CATEGORY_BY_INTENT.get(intent)
            if intent == "crop_advice":
                # Spray/irrigation questions conditioned on rain are agromet
                # guidance, so prefer the weather category while still allowing
                # other crop-advice documents to compete.
                category = "weather" if understanding.agromet_informational else None
            hits = self.retriever.search(
                understanding.retrieval_query,
                top_k=settings.retrieval_top_k,
                language=lang,
                crop=resolved_crop,
                state=state,
                category=category,
                intent=intent,
            )
            evidence = self.retriever.select_evidence(hits, settings.evidence_top_k)
            retrieval_meta = {
                "query": understanding.retrieval_query,
                "hits_considered": len(hits),
                "top_score": evidence[0]["score"] if evidence else 0,
                "top_documents": self.retriever.top_documents(hits, 5),
                "embedding_provider": self.embeddings.provider,
            }

        gate_result = gate(
            understanding,
            evidence,
            tool_data,
            self.glossary,
            asr_confidence=asr_confidence,
        )
        decision = gate_result["decision"]
        reason_code = gate_result["reason_code"]
        generation: dict[str, Any] = {
            "answer": "",
            "generation_provider": "none",
            "generation_mode": "none",
            "grounding_score": 0.0,
            "llm_fallback_reason": None,
            "citations": [],
            "safety_note": None,
        }

        if decision == "answer":
            generation = self.composer.compose(
                text,
                lang,
                understanding,
                evidence,
                tool_data=tool_data,
                tool_name=tool_name,
                safety_note_required=gate_result["safety_note_required"],
            )
        elif decision == "ask_to_repeat":
            generation["answer"] = clarify_message(reason_code, lang)
            generation["generation_provider"] = "policy-message-v1"
            generation["generation_mode"] = "deterministic"
        else:
            generation["answer"] = refusal_message(reason_code, lang)
            generation["generation_provider"] = "policy-message-v1"
            generation["generation_mode"] = "deterministic"
            if gate_result["safety_note_required"]:
                generation["safety_note"] = safety_note(lang)

        if tool_data is not None and tool_data.get("found"):
            # Citations for live tools are provenance records, not document citations.
            generation["citations"] = [
                {
                    "document_id": f"tool:{tool_name}",
                    "title": f"{tool_name.title()} data record",
                    "publisher": tool_data.get("provider"),
                    "source_name": tool_data.get("source_name"),
                    "source_url": tool_data.get("provider_url"),
                    "publication_date": tool_data.get("data_as_of"),
                    "source_date_note": tool_data.get("provenance_note"),
                    "licence": "Provider terms apply",
                    "excerpt": tool_data.get("provenance_note"),
                    "is_demo": not bool(tool_data.get("is_live")),
                    "category": tool_name,
                }
            ]

        simulated = bool(tool_data and tool_data.get("data_mode") == "simulated")
        demo_knowledge = any(item.get("is_demo") for item in evidence) if evidence else False
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        query_id = f"qry_{uuid.uuid4().hex[:14]}"
        created_at = iso_now()
        provenance = {
            "answer_source": "tool" if tool_data is not None else ("knowledge_base" if evidence else "policy"),
            "knowledge_mode": "demonstration_curated" if demo_knowledge else ("admin_uploaded" if evidence else "none"),
            "demo_knowledge": demo_knowledge,
            "tool_mode": tool_data.get("data_mode") if tool_data else None,
            "tool_provider": tool_data.get("provider") if tool_data else None,
            "generation_mode": generation["generation_mode"],
            "generation_provider": generation["generation_provider"],
            "embedding_provider": self.embeddings.provider,
            "retrieval": retrieval_meta,
            "llm_fallback_reason": generation.get("llm_fallback_reason"),
        }

        response = {
            "query_id": query_id,
            "created_at": created_at,
            "text": text,
            "decision": decision,
            "answer": generation["answer"],
            "language": lang,
            "detected_language": understanding.language,
            "language_name": language_name(lang),
            "intent": intent,
            "intent_confidence": understanding.intent_confidence,
            "entities": entities,
            "confidence": gate_result["confidence"],
            "reason_code": reason_code,
            "reason_detail": gate_result["reason_detail"],
            "signals": gate_result["signals"],
            "evidence": evidence,
            "citations": generation["citations"],
            "tool_data": tool_data,
            "data_as_of": tool_data.get("data_as_of") if tool_data else None,
            "simulated": simulated,
            "demo_knowledge": demo_knowledge,
            "generation_provider": generation["generation_provider"],
            "generation_mode": generation["generation_mode"],
            "grounding_score": generation["grounding_score"],
            "llm_fallback_reason": generation.get("llm_fallback_reason"),
            "safety_note": generation.get("safety_note"),
            "disclaimer": disclaimer(lang),
            "provenance": provenance,
            "suggested_followups": followups(intent, lang),
            "latency_ms": latency_ms,
            "input_mode": input_mode,
            "asr_confidence": asr_confidence,
            "crop": resolved_crop or "",
            "state": state,
            "district": resolved_district or "",
            "review_status": "unreviewed",
        }
        if log:
            db.log_query(response)
        return response

    def refresh(self, reason: str = "manual") -> int:
        return self.retriever.refresh(reason)
