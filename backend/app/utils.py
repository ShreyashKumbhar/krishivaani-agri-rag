"""Small text and time utilities shared by the backend services."""
from __future__ import annotations

import json
import math
import re
import unicodedata
import zlib
from datetime import datetime, timedelta, timezone
from typing import Iterable

IST = timezone(timedelta(hours=5, minutes=30))

TOKEN_RE = re.compile(r"[A-Za-z]+|[\u0900-\u097F]+|\d+(?:\.\d+)?")
SENTENCE_RE = re.compile(r"(?<=[।!?\.])\s+|\n+")

EN_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "but", "by", "can", "could", "do", "does",
    "for", "from", "get", "give", "has", "have", "how", "i", "if", "in", "is", "it", "its", "me",
    "my", "of", "on", "or", "our", "please", "should", "so", "tell", "than", "that", "the", "their",
    "them", "there", "these", "this", "to", "was", "we", "what", "when", "where", "which", "who",
    "why", "will", "with", "would", "you", "your", "about", "after", "any", "best", "current",
    "today", "now", "exact", "kind", "much", "many", "need", "want", "know", "use", "using",
}

HI_STOPWORDS = {
    "और", "अथवा", "आज", "आप", "इस", "उस", "एक", "कब", "कर", "करना", "करें", "कहाँ", "का", "कि",
    "कितना", "कितनी", "कितने", "किस", "किसका", "किसकी", "किसे", "की", "कुछ", "के", "को", "कौन",
    "क्या", "क्यों", "कैसे", "जब", "जो", "तक", "तो", "था", "थी", "थे", "दिया", "देना", "नहीं",
    "ने", "पर", "पर्याप्त", "पहले", "फिर", "बताइए", "बताएं", "बारे", "भी", "मुझे", "मेरा", "मेरी",
    "मेरे", "में", "यह", "या", "लिए", "से", "है", "हैं", "हो", "होता", "होती", "होते", "करें",
    "चाहिए", "सकते", "सकता", "सकती", "कोई", "जैसे", "वाला", "वाली", "करने", "किया", "अपनी",
}

MR_STOPWORDS = {
    "आणि", "आहे", "आहेत", "आज", "आपण", "आपल्या", "एक", "कसा", "कसे", "का", "काय", "किती", "कुठे",
    "कोणते", "कोणती", "कोणता", "करा", "करावे", "करावी", "करून", "केले", "किंवा", "कृपया", "जर",
    "ते", "तो", "ती", "था", "होते", "होतो", "होती", "मला", "माझा", "माझी", "माझे", "माझ्या",
    "मध्ये", "नाही", "पण", "पर्यंत", "पाहिजे", "बद्दल", "साठी", "सांगा", "हे", "हा", "ही", "वर",
    "असे", "असते", "असतो", "करत", "करणे", "केली", "गेले", "जाते", "नको", "हवे", "काही", "सर्व",
}

STOPWORDS = EN_STOPWORDS | HI_STOPWORDS | MR_STOPWORDS


def now_ist() -> datetime:
    return datetime.now(IST)


def iso_now() -> str:
    return now_ist().isoformat(timespec="seconds")


def today_ist() -> str:
    return now_ist().date().isoformat()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\u200c", "").replace("\u200d", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(normalize_text(text))]


def content_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS and len(token) > 1]


def split_sentences(text: str) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    parts = [part.strip() for part in SENTENCE_RE.split(text) if part and part.strip()]
    return parts


def stable_hash(value: str) -> int:
    return zlib.crc32(value.encode("utf-8")) & 0xFFFFFFFF


def json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def round_score(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def truncate_words(text: str, limit: int = 90) -> str:
    words = (text or "").split()
    if len(words) <= limit:
        return text.strip()
    return " ".join(words[:limit]).rstrip(",;:") + " …"


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    left, right = set(a), set(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def chunk_text(text: str, target_chars: int = 520, overlap_chars: int = 90) -> list[str]:
    """Split text on sentence/paragraph boundaries with a small overlap.

    The corpus is small, so a simple deterministic chunker is preferable to a
    heavyweight document framework. Chunks never cut a sentence in half unless
    a single sentence is longer than the target size.
    """
    text = normalize_text(text)
    if not text:
        return []
    sentences: list[str] = []
    for paragraph in text.split("\n\n"):
        sentences.extend(split_sentences(paragraph))
    if not sentences:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        if len(sentence) > target_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current, current_len = [], 0
            for start in range(0, len(sentence), target_chars - overlap_chars):
                chunks.append(sentence[start:start + target_chars].strip())
            continue
        if current and current_len + len(sentence) + 1 > target_chars:
            chunks.append(" ".join(current).strip())
            overlap: list[str] = []
            overlap_len = 0
            for previous in reversed(current):
                if overlap_len + len(previous) > overlap_chars:
                    break
                overlap.insert(0, previous)
                overlap_len += len(previous) + 1
            current = overlap
            current_len = overlap_len
        current.append(sentence)
        current_len += len(sentence) + 1
    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]
