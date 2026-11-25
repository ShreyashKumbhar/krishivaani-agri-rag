"""Rule-based query understanding: language, intent, entities and scope.

The rules are deliberately transparent and auditable. They handle Hindi,
Marathi and English/code-mixed agricultural questions without requiring a GPU
or a hosted classifier. The output is used for routing, metadata filters and
the confidence gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..utils import content_tokens, normalize_text, tokenize
from .glossary import Glossary
from .language import detect_language, normalize_language

INTENT_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "market_price": [
        ("mandi", 3.0), ("market price", 3.0), ("price", 2.0), ("rate", 1.5), ("sell", 1.2),
        ("मंडी", 3.0), ("बाजार", 2.4), ("भाव", 3.0), ("दाम", 2.0), ("कीमत", 2.0), ("बाजारभाव", 3.0),
        ("किंमत", 2.0), ("विक्री", 1.6), ("विकणे", 1.6), ("दर", 1.2),
    ],
    "weather": [
        ("weather", 3.0), ("rain", 2.6), ("forecast", 2.6), ("temperature", 1.8), ("humidity", 1.4),
        ("मौसम", 3.0), ("बारिश", 2.6), ("वर्षा", 2.4), ("तापमान", 1.8), ("हवामान", 3.0), ("पाऊस", 2.6),
        ("अंदाज", 2.0), ("उकाडा", 1.4),
    ],
    "scheme": [
        ("scheme", 3.0), ("subsidy", 2.4), ("government scheme", 3.0), ("pm-kisan", 3.0), ("pm kisan", 3.0),
        ("pmfby", 3.0), ("crop insurance", 2.8), ("kisan credit", 3.0), ("kcc", 2.6), ("soil health card", 3.0),
        ("योजना", 3.0), ("सब्सिडी", 2.4), ("अनुदान", 2.2), ("बीमा", 2.6), ("विमा", 2.6), ("पीएम किसान", 3.0),
        ("पीक विमा", 3.0), ("किसान क्रेडिट", 3.0), ("मृदा स्वास्थ्य", 3.0), ("माती आरोग्य", 3.0),
        ("सरकारी", 1.6), ("योजनेत", 2.0), ("योजनेसाठी", 2.0),
    ],
    "pest_disease": [
        ("pest", 3.0), ("disease", 3.0), ("insect", 2.4), ("yellow", 2.0), ("spot", 1.8), ("wilt", 2.4),
        ("blight", 2.8), ("mildew", 2.8), ("rot", 2.0), ("caterpillar", 2.6), ("bollworm", 2.8),
        ("thrips", 2.8), ("whitefly", 2.8), ("aphid", 2.4), ("termite", 2.4), ("mosaic", 2.6),
        ("scout", 2.4), ("monitor", 2.0),
        ("रोग", 3.0), ("कीट", 2.8), ("कीड़ा", 2.4), ("पीले", 2.2), ("पीली", 2.2), ("धब्बे", 2.0),
        ("मुरझा", 2.2), ("सड़न", 2.2), ("इल्ली", 2.6), ("सुंडी", 2.6), ("मक्खी", 2.2), ("थ्रिप्स", 2.8),
        ("पिवळ", 2.2), ("ठिपके", 2.0), ("करपा", 2.6), ("अळी", 2.6), ("माशी", 2.2), ("बुरशी", 2.6),
        ("मर", 1.4), ("नुकसान", 1.8), ("ओळखावा", 1.6), ("पहचान", 1.6),
        ("कीड", 2.8), ("निरीक्षण", 2.2), ("तपासणी", 1.8),
    ],
    "pesticide_safety": [
        ("pesticide", 3.0), ("insecticide", 2.8), ("fungicide", 2.6), ("spray", 2.2), ("chemical", 2.0),
        ("precaution", 2.6), ("safety", 2.4), ("कीटनाशक", 3.0), ("कीटकनाशक", 3.0), ("छिड़काव", 2.4), ("फवारणी", 2.6),
        ("दवा", 2.0), ("औषध", 2.0), ("सावधानी", 2.6), ("काळजी", 2.6), ("फफूंदनाशक", 2.6),
        ("बुरशीनाशक", 2.6), ("विष", 2.0),
    ],
    "crop_advice": [
        ("crop", 1.8), ("sow", 2.6), ("sowing", 2.6), ("plant", 2.0), ("seed", 2.0),
        ("fertilizer", 2.4), ("fertiliser", 2.4), ("fertilize", 2.4),
        ("irrigation", 2.8), ("irrigate", 2.8), ("water", 1.4), ("harvest", 2.2), ("storage", 2.6), ("soil", 2.2),
        ("urea", 2.2), ("dap", 2.0), ("बुवाई", 2.6), ("बीज", 2.0), ("खाद", 2.4), ("सिंचाई", 2.8),
        ("पानी", 1.4), ("कटाई", 2.2), ("भंडारण", 2.6), ("मिट्टी", 2.2), ("पेरणी", 2.6), ("बियाणे", 2.0),
        ("खत", 2.4), ("सिंचन", 2.8), ("पाणी", 1.4), ("काढणी", 2.2), ("साठवण", 2.6), ("माती", 2.2),
        ("उत्पादन", 1.2), ("पैदावार", 1.2), ("गन्ना", 1.2), ("ऊस", 1.2),
    ],
}

OUT_OF_SCOPE_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions", r"system prompt", r"reveal (the )?prompt",
    r"explosive", r"\bbomb\b", r"recipe for (an? )?(explosive|bomb)", r"\belection\b", r"who will win",
    r"antibiotic", r"medical advice", r"\bjob\b", r"government job", r"lottery", r"stock market",
    r"cricket", r"movie", r"tractor loan", r"loan interest rate", r"how much yield", r"yield will",
    r"production prediction", r"सिस्टम प्रॉम्प्ट", r"नियम भूल", r"प्रॉम्प्ट दिखाओ", r"चुनाव", r"नोकरी",
    r"सोन्याचे भांडार", r"सोने कुठे", r"एंटीबायोटिक", r"जहर", r"विस्फोटक", r"बम", r"लॉटरी",
    r"ब्याज दर", r"व्याज दर", r"उत्पादन कितना", r"किती उत्पादन",
]

DOSE_PATTERNS = [
    r"\b(dose|dosage)\b", r"how much (should i )?(mix|spray|apply|use)",
    r"how many (ml|millilitres?|litres?|grams?|kg)\b", r"per (litre|liter|acre)\b",
    r"\d+(\.\d+)?\s*(ml|millilitres?|litres?|liters?|grams?|gm|kg|g)\b",
    r"मात्रा", r"कितनी मात्रा", r"कितना (छिड़कें|डालें|मिलाएँ)", r"कितना (छिड़काव|घोल)",
    r"प्रति (लीटर|लिटर|एकड़|एकर)", r"मिली|लीटर|लिटर|ग्राम|किलो",
    r"किती मात्रा", r"किती (फवारावे|फवारणी|मिसळावे)", r"प्रति (लिटर|एकर|एकड)", r"मिली|लिटर|ग्रॅम|किलो",
    r"\d+\s*(एमएल|मिली|लीटर|लिटर|ग्राम|किलो|एकड़|एकर|एकड)",
    r"(कौन सा|कौनसा|कोणते|which).{0,30}(जहर|ज़हर|विष|zeher|poison)",
]

CHEMICAL_CONTEXT = [
    "pesticide", "insecticide", "fungicide", "chemical", "spray", "imidacloprid", "monocrotophos",
    "कीटनाशक", "कीटकनाशक", "औषध", "दवा", "छिड़काव", "फवारणी", "फफूंदनाशक", "जहर", "यूरिया", "urea", "dap",
    "fertilizer", "खाद", "खत", "मात्रा", "dose", "dosage",
]

INFORMATIONAL_MARKET = re.compile(
    r"how (do|can|should) i (read|check|understand)|how to (read|check|understand)|price quote|"
    r"read a mandi|बाजारात भाव कसा तपासावा|भाव कैसे देखें|भाव कैसे समझें|मंडी भाव कैसे|बाजार भाव कसा",
    re.IGNORECASE,
)
AGROMET_INFORMATIONAL = re.compile(
    r"(spray|spraying|छिड़काव|फवारणी).*(rain|बारिश|पाऊस)|(rain|बारिश|पाऊस).*(spray|spraying|छिड़काव|फवारणी)|"
    r"irrigat.*(weather|मौसम|हवामान)|(weather|मौसम|हवामान).*irrigat",
    re.IGNORECASE,
)

PRONOUNS = {"it", "this", "that", "these", "those", "इसका", "इसे", "यह", "उसका", "उसे", "वह", "त्याचे", "त्याला", "हे", "हा", "ही"}


@dataclass
class Understanding:
    text: str
    language: str
    intent: str
    intent_confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    normalized_query: str = ""
    retrieval_query: str = ""
    is_chemical_dosage: bool = False
    is_out_of_scope: bool = False
    out_of_scope_reason: str = ""
    is_ambiguous: bool = False
    missing: str | None = None
    market_informational: bool = False
    agromet_informational: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "intent": self.intent,
            "intent_confidence": self.intent_confidence,
            "entities": self.entities,
            "normalized_query": self.normalized_query,
            "is_chemical_dosage": self.is_chemical_dosage,
            "is_out_of_scope": self.is_out_of_scope,
            "out_of_scope_reason": self.out_of_scope_reason,
            "is_ambiguous": self.is_ambiguous,
            "missing": self.missing,
            "market_informational": self.market_informational,
            "agromet_informational": self.agromet_informational,
        }


def _has_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.lower()
    if " " in phrase or "-" in phrase:
        return phrase in text
    # Devanagari is agglutinative: "कापसाची" should match the crop "कापूस"
    # after a light stem match. Latin words allow the common English plural and
    # verb suffixes ("precautions", "spraying"), which keeps keyword matching
    # useful without a full lemmatiser.
    if re.search(r"[\u0900-\u097F]", phrase):
        return phrase in text
    pattern = r"(?<![\w])" + re.escape(phrase) + r"(?:s|es|ing|ed)?(?![\w])"
    return re.search(pattern, text) is not None


def _detect_dosage(text: str) -> bool:
    lowered = text.lower()
    dose_signal = any(re.search(pattern, lowered, re.IGNORECASE) for pattern in DOSE_PATTERNS)
    if not dose_signal:
        return False
    # A pure weather/irrigation question with "litres" is not a chemical dose.
    chemical_context = any(term in lowered for term in CHEMICAL_CONTEXT)
    if "how much water" in lowered or "कितना पानी" in lowered or "किती पाणी" in lowered:
        return False
    return chemical_context or bool(re.search(r"\d+\s*(ml|litre|liter|gram|gm|kg|मिली|लीटर|ग्राम|किलो)", lowered))


def _extract_crop(text: str, glossary: Glossary) -> str | None:
    lowered = text.lower()
    for crop, variants in sorted(glossary.crop_variants().items(), key=lambda item: max(len(v) for v in item[1]), reverse=True):
        for variant in sorted(variants, key=len, reverse=True):
            if variant and _has_phrase(lowered, variant.lower()):
                return crop
    return None


def _extract_district(text: str, glossary: Glossary) -> str | None:
    lowered = text.lower()
    for place, variants in sorted(glossary.place_variants().items(), key=lambda item: max(len(v) for v in item[1]), reverse=True):
        if place == "maharashtra":
            continue
        for variant in sorted(variants, key=len, reverse=True):
            if variant and _has_phrase(lowered, variant.lower()):
                return place.title()
    return None


def _extract_scheme(text: str, glossary: Glossary) -> str | None:
    for entry in glossary.terms("scheme"):
        variants = [entry.get("term_en", ""), entry.get("term_hi", ""), entry.get("term_mr", ""), *entry.get("aliases", [])]
        if any(variant and _has_phrase(text.lower(), variant.lower()) for variant in variants):
            return entry["term_en"]
    return None


def _out_of_scope(text: str) -> tuple[bool, str]:
    lowered = text.lower()
    if "kisan credit" in lowered or "किसान क्रेडिट" in lowered or "kcc" in lowered:
        return False, ""
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return True, "OUT_OF_SCOPE"
    return False, ""


def understand(
    text: str,
    requested_language: str | None = None,
    crop_hint: str | None = None,
    district_hint: str | None = None,
    glossary: Glossary | None = None,
) -> Understanding:
    if glossary is None:
        raise ValueError("Glossary is required")
    text = normalize_text(text)
    language = normalize_language(detect_language(text, requested_language))
    lowered = text.lower()

    is_dosage = _detect_dosage(text)
    out_of_scope, out_reason = _out_of_scope(text)
    market_info = bool(INFORMATIONAL_MARKET.search(text))
    agromet_info = bool(AGROMET_INFORMATIONAL.search(text))

    scores: dict[str, float] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0.0
        for phrase, weight in keywords:
            if _has_phrase(lowered, phrase.lower()):
                score += weight
        scores[intent] = score

    # Disambiguate overlapping vocabulary.
    if is_dosage:
        intent = "chemical_dosage"
        scores[intent] = max(scores.values(), default=0) + 4.0
    elif out_of_scope:
        intent = "other"
        scores[intent] = max(scores.values(), default=0) + 4.0
    elif agromet_info and scores.get("weather", 0) > 0:
        # "Should I spray if rain is expected?" is advisory guidance, not a
        # request for a live forecast; route it to the knowledge base.
        intent = "crop_advice"
    elif market_info and scores.get("market_price", 0) > 0:
        intent = "market_price"
    elif (
        scores.get("scheme", 0) > 0
        and scores.get("crop_advice", 0) > 0
        and any(term in lowered for term in ("fertilizer", "fertiliser", "खाद", "खत", "उर्वरक"))
    ):
        # "How do I use the Soil Health Card for fertilizer advice?" is crop
        # advice even though the card itself is a government scheme.
        intent = "crop_advice"
    elif scores.get("pest_disease", 0) > 0 and scores["pest_disease"] >= max(scores.values()):
        intent = "pest_disease"
    else:
        priority = ["market_price", "weather", "scheme", "pest_disease", "pesticide_safety", "crop_advice"]
        intent = max(priority, key=lambda key: scores.get(key, 0))
        if scores.get(intent, 0) == 0:
            intent = "other"

    top_score = scores.get(intent, 0.0)
    if intent == "other":
        intent_confidence = 0.30
    else:
        sorted_scores = sorted(scores.values(), reverse=True)
        second = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
        margin = max(0.0, top_score - second)
        intent_confidence = min(0.97, 0.45 + 0.07 * top_score + 0.03 * margin)

    crop = crop_hint.lower() if crop_hint else _extract_crop(text, glossary)
    district = district_hint.title() if district_hint else _extract_district(text, glossary)
    scheme = _extract_scheme(text, glossary)
    concepts = glossary.concepts(text)
    content = content_tokens(text)
    pronoun = any(token in PRONOUNS for token in tokenize(text))

    entities: dict[str, Any] = {
        "crop": crop,
        "district": district,
        "commodity": crop,
        "scheme": scheme,
        "concepts": concepts,
        "numbers": re.findall(r"\d+(?:\.\d+)?", text),
        "content_token_count": len(content),
    }

    ambiguous = False
    missing: str | None = None
    if intent == "market_price" and not market_info and not crop:
        missing = "commodity"
    if intent == "weather" and not agromet_info and not district:
        missing = "location"
    if intent not in {"other", "market_price", "weather"} and not crop and (pronoun or len(content) <= 1):
        ambiguous = True
    if intent == "other" and not out_of_scope and (pronoun or len(content) <= 1):
        ambiguous = True
    if intent == "weather" and not district and not agromet_info:
        ambiguous = True

    retrieval_query = glossary.expand_for_retrieval(text)
    normalized = glossary.translate_to_english(text)
    if normalized.lower() != text.lower():
        retrieval_query = f"{retrieval_query} {normalized}"

    return Understanding(
        text=text,
        language=language,
        intent=intent,
        intent_confidence=round(intent_confidence, 3),
        entities=entities,
        normalized_query=normalized,
        retrieval_query=retrieval_query,
        is_chemical_dosage=is_dosage,
        is_out_of_scope=out_of_scope,
        out_of_scope_reason=out_reason,
        is_ambiguous=ambiguous,
        missing=missing,
        market_informational=market_info,
        agromet_informational=agromet_info,
    )
