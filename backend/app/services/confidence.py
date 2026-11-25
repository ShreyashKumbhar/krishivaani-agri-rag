"""Confidence gate and safety policy.

Decision policy:
- REFUSE for unsafe chemical dosage, out-of-scope/adversarial input, or when
  retrieval evidence is too weak. Refusal is the safe default.
- ASK_TO_REPEAT only when the question is incomplete (missing crop/location/
  commodity), ambiguous, or the ASR confidence is low.
- ANSWER only when retrieval + coverage + intent confidence clear thresholds.
"""
from __future__ import annotations

from typing import Any

from ..config import settings
from ..utils import clamp, content_tokens
from .glossary import Glossary


def evidence_coverage(query: str, evidence: list[dict[str, Any]], glossary: Glossary) -> float:
    query_terms = set(content_tokens(query))
    for concept in glossary.concepts(query):
        query_terms.update(content_tokens(concept))
    if not query_terms:
        return 0.0
    evidence_terms: set[str] = set()
    for item in evidence:
        evidence_terms.update(content_tokens(item.get("text", "")))
        evidence_terms.update(content_tokens(item.get("title", "")))
        for concept in glossary.concepts(item.get("text", "")):
            evidence_terms.update(content_tokens(concept))
    return len(query_terms & evidence_terms) / max(1, len(query_terms))


def gate(
    understanding,
    evidence: list[dict[str, Any]],
    tool_data: dict[str, Any] | None,
    glossary: Glossary,
    asr_confidence: float | None = None,
) -> dict[str, Any]:
    intent = understanding.intent
    coverage = evidence_coverage(understanding.text, evidence, glossary) if evidence else 0.0
    top_score = float(evidence[0].get("score", 0)) if evidence else 0.0
    evidence_count = len(evidence)
    authority_values = [float(item.get("signals", {}).get("authority", 0.55)) for item in evidence]
    source_quality = sum(authority_values) / len(authority_values) if authority_values else 0.0
    language_matches = [float(item.get("signals", {}).get("language_match", 0)) for item in evidence]
    language_match = max(language_matches) if language_matches else 0.0

    if tool_data and tool_data.get("found"):
        tool_confidence = 0.93 if tool_data.get("is_live") else 0.86
        overall = 0.65 * tool_confidence + 0.25 * understanding.intent_confidence + 0.10 * (asr_confidence if asr_confidence is not None else 1.0)
        signals = {
            "tool_confidence": round(tool_confidence, 4),
            "data_mode": tool_data.get("data_mode"),
            "intent_confidence": understanding.intent_confidence,
            "asr_confidence": asr_confidence,
            "retrieval_confidence": None,
            "coverage": None,
            "top_score": None,
            "source_quality": None,
            "evidence_count": 0,
            "language_match": None,
        }
    else:
        retrieval_confidence = (
            0.45 * clamp(top_score)
            + 0.35 * clamp(coverage)
            + 0.15 * min(1.0, evidence_count / 3.0)
            + 0.05 * source_quality
        )
        asr_component = asr_confidence if asr_confidence is not None else 1.0
        overall = 0.58 * retrieval_confidence + 0.27 * understanding.intent_confidence + 0.10 * source_quality + 0.05 * asr_component
        signals = {
            "tool_confidence": None,
            "data_mode": None,
            "intent_confidence": understanding.intent_confidence,
            "asr_confidence": asr_confidence,
            "retrieval_confidence": round(retrieval_confidence, 4),
            "coverage": round(coverage, 4),
            "top_score": round(top_score, 4),
            "source_quality": round(source_quality, 4),
            "evidence_count": evidence_count,
            "language_match": round(language_match, 4),
        }

    overall = round(clamp(overall), 4)
    safety_note_required = intent in {"pesticide_safety", "chemical_dosage"} or any(
        item.get("category") == "pesticide_safety" for item in evidence
    )

    if understanding.is_chemical_dosage:
        return _result("refuse", overall, "CHEMICAL_DOSAGE_BLOCKED",
                       "The request asks for a pesticide or chemical dose. The assistant does not provide dosage numbers; the user is referred to the product label, CIB&RC and KVK/Kisan Call Centre.",
                       signals, safety_note_required=True)
    if understanding.is_out_of_scope:
        return _result("refuse", overall, "OUT_OF_SCOPE",
                       "The request is outside the agricultural advisory scope or is adversarial. The assistant refuses rather than improvising.",
                       signals, safety_note_required=safety_note_required)
    if understanding.missing == "commodity":
        return _result("ask_to_repeat", overall, "MISSING_COMMODITY",
                       "A market-price question was detected but no commodity was specified.",
                       signals, safety_note_required=safety_note_required)
    if understanding.missing == "location":
        return _result("ask_to_repeat", overall, "MISSING_LOCATION",
                       "A weather question was detected but no district was specified.",
                       signals, safety_note_required=safety_note_required)
    if understanding.is_ambiguous:
        return _result("ask_to_repeat", overall, "AMBIGUOUS_QUERY",
                       "The question is too short or lacks the crop/subject needed to retrieve safe evidence.",
                       signals, safety_note_required=safety_note_required)
    if asr_confidence is not None and asr_confidence < 0.45:
        return _result("ask_to_repeat", overall, "LOW_ASR_CONFIDENCE",
                       "Speech recognition confidence is low; the user should repeat or type the question.",
                       signals, safety_note_required=safety_note_required)
    if intent == "other":
        return _result("refuse", overall, "OUT_OF_SCOPE",
                       "No supported agricultural intent was detected.", signals,
                       safety_note_required=safety_note_required)
    if tool_data is not None and not tool_data.get("found"):
        reason = tool_data.get("reason") or "TOOL_DATA_UNAVAILABLE"
        return _result("ask_to_repeat", overall, reason,
                       "The live tool could not return a usable record for the requested commodity or location.",
                       signals, safety_note_required=safety_note_required)
    if not evidence and tool_data is None:
        return _result("refuse", overall, "NO_EVIDENCE",
                       "No approved knowledge-base passage was retrieved.", signals,
                       safety_note_required=safety_note_required)
    if tool_data is None and (top_score < settings.min_retrieval_score or coverage < settings.min_evidence_coverage):
        return _result("refuse", overall, "INSUFFICIENT_EVIDENCE",
                       "The retrieved passages do not cover the question well enough to answer safely.",
                       signals, safety_note_required=safety_note_required)
    if overall < settings.min_answer_confidence:
        return _result("refuse", overall, "LOW_CONFIDENCE",
                       "The combined confidence score is below the answer threshold.", signals,
                       safety_note_required=safety_note_required)
    return _result("answer", overall, "GROUNDED_ANSWER",
                   "The answer is supported by approved retrieved evidence or a labelled live/simulated tool.",
                   signals, safety_note_required=safety_note_required)


def _result(decision: str, confidence: float, reason_code: str, reason_detail: str, signals: dict[str, Any], safety_note_required: bool) -> dict[str, Any]:
    return {
        "decision": decision,
        "confidence": round(confidence, 4),
        "reason_code": reason_code,
        "reason_detail": reason_detail,
        "signals": signals,
        "safety_note_required": safety_note_required,
    }
