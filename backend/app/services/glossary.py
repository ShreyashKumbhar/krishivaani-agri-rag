"""Agriculture-aware glossary and term mapping.

This is the "agricultural terminology" layer: it keeps crop, pest, disease,
input, scheme and place names aligned across English, Hindi and Marathi. It is
used for query expansion, cross-lingual retrieval and glossary-assisted
translation. It is not a general-purpose neural translation model.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import db
from ..config import settings
from ..utils import normalize_text


class Glossary:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.variant_map: dict[str, dict[str, Any]] = {}
        self.by_english: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        entries = db.list_glossary()
        if not entries:
            import json

            seed = json.loads(Path(settings.glossary_seed_path).read_text(encoding="utf-8"))
            db.seed_glossary(seed)
            entries = db.list_glossary()
        self.entries = entries
        self.variant_map = {}
        self.by_english = {}
        for entry in entries:
            self.by_english[entry["term_en"].lower()] = entry
            variants = {
                entry.get("term_en", ""),
                entry.get("term_hi", ""),
                entry.get("term_mr", ""),
                *entry.get("aliases", []),
            }
            for variant in variants:
                variant = normalize_text(variant).lower()
                if variant:
                    self.variant_map[variant] = entry
        # Longest first so "yellow mosaic" wins over "yellow".
        self._variants_sorted = sorted(self.variant_map, key=len, reverse=True)

    def lookup(self, term: str) -> dict[str, Any] | None:
        return self.variant_map.get(normalize_text(term).lower())

    def concepts(self, text: str) -> list[str]:
        """Return canonical English terms mentioned in the text (deduplicated)."""
        lowered = normalize_text(text).lower()
        found: list[str] = []
        for variant in self._variants_sorted:
            if variant and variant in lowered:
                english = self.variant_map[variant]["term_en"]
                if english not in found:
                    found.append(english)
        return found

    def expand_for_retrieval(self, text: str) -> str:
        """Append canonical English concepts to a native-language query."""
        concepts = self.concepts(text)
        if not concepts:
            return text
        return f"{text} {' '.join(concepts)}"

    def translate_to_english(self, text: str) -> str:
        """Glossary-assisted term substitution (not full machine translation)."""
        result = normalize_text(text)
        for variant in self._variants_sorted:
            if len(variant) < 2:
                continue
            pattern = re.compile(
                r"(?<![\w\u0900-\u097F])" + re.escape(variant) + r"(?![\w\u0900-\u097F])",
                re.IGNORECASE,
            )
            result = pattern.sub(self.variant_map[variant]["term_en"], result)
        return result

    def localize(self, term_en: str, language: str) -> str:
        entry = self.by_english.get(term_en.lower())
        if not entry:
            return term_en
        return entry.get(f"term_{language}") or entry["term_en"]

    def terms(self, category: str | None = None) -> list[dict[str, Any]]:
        if not category:
            return self.entries
        return [entry for entry in self.entries if entry.get("category") == category]

    def crop_variants(self) -> dict[str, list[str]]:
        return {
            entry["term_en"].lower(): [
                value for value in (entry["term_en"], entry["term_hi"], entry["term_mr"], *entry.get("aliases", [])) if value
            ]
            for entry in self.entries
            if entry.get("category") == "crop"
        }

    def place_variants(self) -> dict[str, list[str]]:
        return {
            entry["term_en"].lower(): [
                value for value in (entry["term_en"], entry["term_hi"], entry["term_mr"], *entry.get("aliases", [])) if value
            ]
            for entry in self.entries
            if entry.get("category") == "place"
        }

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.get("category", "general")] = counts.get(entry.get("category", "general"), 0) + 1
        return counts
