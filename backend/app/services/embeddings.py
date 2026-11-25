"""Multilingual embedding service.

Default: a deterministic, dependency-light hashed embedding that combines
word, character n-gram and glossary-concept features. Glossary concepts map
Hindi/Marathi agricultural terms onto English canonical terms, which gives the
demo useful cross-lingual retrieval without downloading a large neural model.

Optional: set EMBEDDING_PROVIDER=sentence-transformers to use a multilingual
Sentence Transformers model if it is installed locally. If the model cannot be
loaded, the service falls back to the hashed embedder and reports that fact.
"""
from __future__ import annotations

import hashlib
import logging

import numpy as np

from ..config import settings
from ..utils import normalize_text, stable_hash, tokenize
from .glossary import Glossary

logger = logging.getLogger(__name__)


class HashedMultilingualEmbedder:
    name = "hashed-multilingual-v1"

    def __init__(self, glossary: Glossary, dim: int = 384) -> None:
        self.glossary = glossary
        self.dim = dim

    def _features(self, text: str) -> dict[str, float]:
        text = normalize_text(text).lower()
        tokens = tokenize(text)
        features: dict[str, float] = {}
        for token in tokens:
            features[f"w:{token}"] = features.get(f"w:{token}", 0.0) + 1.0
            entry = self.glossary.lookup(token)
            if entry:
                features[f"c:{entry['term_en'].lower()}"] = features.get(f"c:{entry['term_en'].lower()}", 0.0) + 2.2
            if len(token) >= 3:
                padded = f"<{token}>"
                for size in (3, 4):
                    for index in range(0, max(0, len(padded) - size + 1)):
                        gram = padded[index:index + size]
                        features[f"g:{gram}"] = features.get(f"g:{gram}", 0.0) + 0.35
        for first, second in zip(tokens, tokens[1:]):
            features[f"b:{first}_{second}"] = features.get(f"b:{first}_{second}", 0.0) + 0.7
        return features

    def embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for feature, weight in self._features(text).items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little")
            index = value % self.dim
            sign = 1.0 if (value >> 63) & 1 else -1.0
            vector[index] += sign * (1.0 + np.log1p(weight))
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return vector


class SentenceTransformerEmbedder:
    name = "sentence-transformers"

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.model = SentenceTransformer(model_name)
        self.name = f"sentence-transformers:{model_name}"

    def embed(self, text: str) -> np.ndarray:
        vector = self.model.encode([text], normalize_embeddings=True)[0]
        return np.asarray(vector, dtype=np.float32)


class EmbeddingService:
    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary
        self.provider = "hashed"
        self.fallback_reason: str | None = None
        self.embedder = HashedMultilingualEmbedder(glossary, settings.embedding_dim)
        if settings.embedding_provider in {"sentence-transformers", "sentence_transformers", "st"}:
            try:
                self.embedder = SentenceTransformerEmbedder(settings.embedding_model)
                self.provider = self.embedder.name
            except Exception as exc:  # pragma: no cover - depends on optional install/model
                logger.warning("Sentence Transformer unavailable, using hashed embeddings: %s", exc)
                self.fallback_reason = f"sentence-transformers unavailable: {type(exc).__name__}"
                self.provider = "hashed"
        self.dim = len(self.embedder.embed("dimension probe"))

    def embed_text(self, text: str) -> np.ndarray:
        vector = self.embedder.embed(text)
        if vector.shape[0] != self.dim:
            # A model swap should trigger a full re-index; this guard keeps the
            # API from mixing vector sizes silently.
            raise ValueError("Embedding dimension changed; rebuild the index")
        return vector.astype(np.float32)

    def embed_many(self, texts: list[str]) -> list[np.ndarray]:
        return [self.embed_text(text) for text in texts]

    @staticmethod
    def to_blob(vector: np.ndarray) -> bytes:
        return np.asarray(vector, dtype=np.float32).tobytes()

    @staticmethod
    def from_blob(blob: bytes | None, dim: int) -> np.ndarray | None:
        if not blob:
            return None
        vector = np.frombuffer(blob, dtype=np.float32)
        if vector.shape[0] != dim:
            return None
        return vector

    def info(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "dimension": self.dim,
            "fallback_reason": self.fallback_reason,
            "mode": "neural" if self.provider.startswith("sentence-transformers") else "deterministic-hashed",
        }
