"""Hybrid retrieval: BM25 + dense embeddings + Reciprocal Rank Fusion + rerank.

The index is rebuilt in memory from approved SQLite chunks at startup and after
an admin approval/upload. It is intentionally small enough for a laptop demo.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..config import settings
from .. import db
from ..utils import clamp, content_tokens, normalize_text, tokenize
from .embeddings import EmbeddingService
from .glossary import Glossary

DEVANAGARI_SUFFIXES = [
    "ांमध्ये", "ांसाठी", "ांनी", "ांना", "ांची", "ांचा", "ांचे", "ाची", "ाचा", "ाचे",
    "ीने", "ीची", "ीचा", "ीचे", "ीं", "ी", "ा", "े", "ों", "ाँ", "ें", "ू", "ु", "ने", "ला", "ली",
]

CATEGORY_BY_INTENT = {
    "pest_disease": "pest_disease",
    "crop_advice": "crop_advice",
    "scheme": "scheme",
    "pesticide_safety": "pesticide_safety",
    "market_price": "market",
    "weather": "weather",
    "chemical_dosage": "pesticide_safety",
}

AUTHORITY_HINTS = ("icar", "government", "ministry", "imd", "nabard", "agmarknet", "e-nam", "official", "central", "department")


def _stem_devanagari(token: str) -> str:
    if not token or not any("\u0900" <= char <= "\u097F" for char in token) or len(token) < 4:
        return token
    for suffix in DEVANAGARI_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def search_tokens(text: str, glossary: Glossary) -> list[str]:
    tokens = tokenize(text)
    expanded = list(tokens)
    for token in tokens:
        stem = _stem_devanagari(token)
        if stem != token:
            expanded.append(stem)
    for concept in glossary.concepts(text):
        expanded.extend(tokenize(concept))
    return expanded


@dataclass
class IndexedChunk:
    id: str
    document_id: str
    chunk_index: int
    language: str
    text: str
    embedding: np.ndarray
    title: str
    title_en: str
    publisher: str
    source_name: str
    source_url: str
    publication_date: str
    source_date_note: str
    licence: str
    category: str
    crops: list[str]
    states: list[str]
    is_demo: bool
    content_note: str
    metadata: dict[str, Any]
    tokens: list[str] = field(default_factory=list)
    term_freq: Counter = field(default_factory=Counter)

    def to_evidence(self) -> dict[str, Any]:
        return {
            "chunk_id": self.id,
            "document_id": self.document_id,
            "title": self.title,
            "title_en": self.title_en,
            "publisher": self.publisher,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "publication_date": self.publication_date,
            "source_date_note": self.source_date_note,
            "licence": self.licence,
            "language": self.language,
            "category": self.category,
            "crops": self.crops,
            "states": self.states,
            "is_demo": self.is_demo,
            "content_note": self.content_note,
            "text": self.text,
            "excerpt": self.text[:420],
        }


class HybridRetriever:
    def __init__(self, glossary: Glossary, embeddings: EmbeddingService) -> None:
        self.glossary = glossary
        self.embeddings = embeddings
        self.chunks: list[IndexedChunk] = []
        self.df: Counter = Counter()
        self.avgdl = 1.0
        self.embedding_matrix: np.ndarray = np.zeros((0, embeddings.dim), dtype=np.float32)
        self.last_rebuild_reason = ""
        self.refresh("startup")

    def refresh(self, reason: str = "manual") -> int:
        rows = db.list_chunks(approved_only=True)
        chunks: list[IndexedChunk] = []
        for row in rows:
            language = row["language"] or "en"
            title = row.get(f"title_{language}") or row.get("title_en") or ""
            embedding = self.embeddings.from_blob(row.get("embedding"), self.embeddings.dim)
            text = row["text"]
            if embedding is None:
                embedding = self.embeddings.embed_text(text)
            token_source = f"{title} {text} {' '.join(row.get('crops') or [])}"
            tokens = search_tokens(token_source, self.glossary)
            chunks.append(
                IndexedChunk(
                    id=row["id"],
                    document_id=row["document_id"],
                    chunk_index=row["chunk_index"],
                    language=language,
                    text=text,
                    embedding=embedding,
                    title=title,
                    title_en=row.get("title_en") or title,
                    publisher=row.get("publisher") or "",
                    source_name=row.get("source_name") or "",
                    source_url=row.get("source_url") or "",
                    publication_date=row.get("publication_date") or "",
                    source_date_note=row.get("source_date_note") or "",
                    licence=row.get("licence") or "",
                    category=row.get("category") or "other",
                    crops=row.get("crops") or [],
                    states=row.get("states") or [],
                    is_demo=bool(row.get("is_demo")),
                    content_note=row.get("content_note") or "",
                    metadata=row.get("metadata") or {},
                    tokens=tokens,
                    term_freq=Counter(tokens),
                )
            )
        self.chunks = chunks
        self.df = Counter(term for chunk in chunks for term in set(chunk.tokens))
        self.avgdl = sum(len(chunk.tokens) for chunk in chunks) / max(1, len(chunks))
        self.embedding_matrix = (
            np.vstack([chunk.embedding for chunk in chunks]).astype(np.float32)
            if chunks
            else np.zeros((0, self.embeddings.dim), dtype=np.float32)
        )
        self.last_rebuild_reason = reason
        return len(chunks)

    def _bm25_scores(self, query_terms: list[str]) -> dict[int, float]:
        n = len(self.chunks)
        if not n:
            return {}
        k1, b = 1.5, 0.75
        scores: dict[int, float] = {}
        for index, chunk in enumerate(self.chunks):
            length = len(chunk.tokens) or 1
            score = 0.0
            for term in set(query_terms):
                freq = chunk.term_freq.get(term, 0)
                if not freq:
                    continue
                df = self.df.get(term, 0)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                denominator = freq + k1 * (1 - b + b * length / max(1.0, self.avgdl))
                score += idf * (freq * (k1 + 1)) / denominator
            if score > 0:
                scores[index] = score
        return scores

    def _dense_scores(self, query_vector: np.ndarray) -> dict[int, float]:
        if not self.chunks:
            return {}
        similarities = self.embedding_matrix @ query_vector
        return {index: float(similarities[index]) for index in range(len(self.chunks))}

    def search(
        self,
        query: str,
        top_k: int = 8,
        language: str | None = None,
        crop: str | None = None,
        state: str | None = None,
        category: str | None = None,
        intent: str | None = None,
        strict_crop: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.chunks:
            return []
        query_terms = search_tokens(query, self.glossary)
        if not query_terms:
            return []
        query_vector = self.embeddings.embed_text(query)
        bm25 = self._bm25_scores(query_terms)
        dense = self._dense_scores(query_vector)

        candidates = list(range(len(self.chunks)))
        if strict_crop and crop:
            filtered = [
                index for index in candidates
                if crop in self.chunks[index].crops or "all" in self.chunks[index].crops
            ]
            if filtered:
                candidates = filtered

        bm25_ranked = sorted(candidates, key=lambda index: bm25.get(index, 0.0), reverse=True)
        dense_ranked = sorted(candidates, key=lambda index: dense.get(index, 0.0), reverse=True)
        rrf: dict[int, float] = defaultdict(float)
        for rank, index in enumerate(bm25_ranked, 1):
            if bm25.get(index, 0.0) > 0:
                rrf[index] += 1.0 / (settings.rrf_k + rank)
        for rank, index in enumerate(dense_ranked, 1):
            if dense.get(index, 0.0) > 0:
                rrf[index] += 1.0 / (settings.rrf_k + rank)
        if not rrf:
            return []

        max_bm25 = max(bm25.values(), default=1.0) or 1.0
        max_rrf = max(rrf.values()) or 1.0
        query_content = set(content_tokens(query))
        for concept in self.glossary.concepts(query):
            query_content.update(content_tokens(concept))
        target_category = category or CATEGORY_BY_INTENT.get(intent or "", None)

        ranked: list[tuple[float, int, dict[str, float]]] = []
        for index in candidates:
            chunk = self.chunks[index]
            if rrf.get(index, 0.0) <= 0:
                continue
            chunk_content = set(content_tokens(chunk.text)) | set(content_tokens(chunk.title))
            for concept in self.glossary.concepts(chunk.text):
                chunk_content.update(content_tokens(concept))
            coverage = len(query_content & chunk_content) / max(1, len(query_content))
            dense_norm = clamp((dense.get(index, 0.0) + 1.0) / 2.0)
            bm25_norm = clamp(bm25.get(index, 0.0) / max_bm25)
            crop_match = 1.0 if crop and (crop in chunk.crops or "all" in chunk.crops) else 0.0
            language_match = 1.0 if language and chunk.language == language else 0.0
            category_match = 1.0 if target_category and chunk.category == target_category else 0.0
            authority = 1.0 if any(hint in (chunk.publisher + " " + chunk.source_name).lower() for hint in AUTHORITY_HINTS) else 0.55
            title_tokens = set(search_tokens(chunk.title, self.glossary))
            title_overlap = len(title_tokens & set(query_terms)) / max(1, len(title_tokens))
            final = (
                0.30 * coverage
                + 0.24 * dense_norm
                + 0.16 * bm25_norm
                + 0.10 * crop_match
                + 0.07 * language_match
                + 0.05 * category_match
                + 0.04 * authority
                + 0.04 * min(1.0, title_overlap)
            )
            # Metadata penalties are soft so cross-lingual and broad questions
            # still retrieve useful evidence.
            if crop and crop not in chunk.crops and "all" not in chunk.crops:
                final *= 0.92
            if state and state not in chunk.states and "all" not in chunk.states:
                final *= 0.96
            signals = {
                "coverage": round(coverage, 4),
                "dense": round(dense_norm, 4),
                "bm25": round(bm25_norm, 4),
                "crop_match": crop_match,
                "language_match": language_match,
                "category_match": category_match,
                "authority": round(authority, 4),
                "title_overlap": round(title_overlap, 4),
                "rrf": round(rrf[index] / max_rrf, 4),
            }
            ranked.append((round(final, 5), index, signals))

        ranked.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        for final, index, signals in ranked[: max(top_k * 3, top_k)]:
            chunk = self.chunks[index]
            evidence = chunk.to_evidence()
            evidence.update(
                {
                    "score": final,
                    "rerank_score": final,
                    "bm25": round(bm25.get(index, 0.0), 4),
                    "dense": round(dense.get(index, 0.0), 4),
                    "rrf": signals["rrf"],
                    "signals": signals,
                }
            )
            results.append(evidence)
        return results[:top_k]

    def select_evidence(self, hits: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
        """Choose at most one passage per document, close to the best score.

        The corpus has parallel English/Hindi/Marathi chunks, so without this
        rule the same document can fill every evidence slot. The relative
        margin also keeps loosely related documents out of a short answer.
        """
        limit = limit or settings.evidence_top_k
        selected: list[dict[str, Any]] = []
        seen_documents: set[str] = set()
        if not hits:
            return selected
        best = float(hits[0].get("score", 0))
        margin = max(0.05, best * 0.78)
        for hit in hits:
            if hit["document_id"] in seen_documents:
                continue
            if selected and float(hit.get("score", 0)) < margin:
                break
            selected.append(hit)
            seen_documents.add(hit["document_id"])
            if len(selected) >= limit:
                break
        return selected

    def top_documents(self, hits: list[dict[str, Any]], limit: int = 5) -> list[str]:
        seen: list[str] = []
        for hit in hits:
            if hit["document_id"] not in seen:
                seen.append(hit["document_id"])
            if len(seen) >= limit:
                break
        return seen

    def stats(self) -> dict[str, Any]:
        languages = Counter(chunk.language for chunk in self.chunks)
        categories = Counter(chunk.category for chunk in self.chunks)
        documents = len({chunk.document_id for chunk in self.chunks})
        return {
            "chunks": len(self.chunks),
            "documents": documents,
            "languages": dict(languages),
            "categories": dict(categories),
            "embedding": self.embeddings.info(),
            "last_rebuild_reason": self.last_rebuild_reason,
        }
