"""Language identification and small language helpers.

The detector is a transparent lexical heuristic, not a trained language-ID
model. Devanagari script plus Marathi/Hindi function words and agricultural
terms are used. Code-mixed Latin-script input is supported through a small set
of romanised cues; the UI language selector always takes precedence.
"""
from __future__ import annotations

import re

from ..utils import normalize_text, tokenize

DEVANAGARI = re.compile(r"[\u0900-\u097F]")

MARATHI_MARKERS = {
    "आहे", "आहेत", "काय", "कसे", "कसा", "कशी", "कसले", "मध्ये", "साठी", "माझ्या", "माझे", "माझा",
    "मला", "पिक", "पिकाची", "पिकात", "कांदा", "कांद्यावर", "कापूस", "कापसाची", "पाने", "पिवळी",
    "पिवळे", "रोग", "बाजार", "भाव", "हवामान", "पाऊस", "योजना", "फवारणी", "कीटक", "कीटकनाशक",
    "काळजी", "करावे", "करावी", "मिळेल", "नोंदणी", "कागदपत्रे", "ऊस", "द्राक्ष", "सोयाबीन", "तूर",
    "हरभरा", "ज्वारी", "भुईमूग", "आजचा", "सांगा", "तपासावा", "पडेल", "नुकसान", "ओळखावा",
    "शेतकरी", "शेतात", "माती", "खत", "सिंचन", "पाणी", "काढणी", "साठवण", "फवारावे", "घ्यावी",
    "ठिपके", "येतात", "तपकिरी", "पानांवर", "होत", "नाही", "येथे", "कोणत्या", "किती",
}

MARATHI_SUFFIXES = ("च्या", "वर", "्यात", "तील", "साठी", "मुळे", "कडे", "ला", "ने", "तून", "ांचा", "ांची", "ांचे")

HINDI_MARKERS = {
    "है", "हैं", "क्या", "कैसे", "क्यों", "में", "के", "की", "को", "मेरी", "मेरा", "मेरे",
    "मुझे", "फसल", "पत्तियाँ", "पत्ती", "पीली", "पीले", "रोग", "बाजार", "भाव", "मौसम", "बारिश",
    "योजना", "छिड़काव", "कीट", "कीटनाशक", "सावधानी", "करें", "चाहिए", "कपास", "प्याज", "गन्ना",
    "अंगूर", "मृदा", "खाद", "भंडारण", "कटाई", "बुवाई", "बीज", "सिंचाई", "पानी", "मिट्टी", "दस्तावेज",
    "किसान", "सरकारी", "मात्रा", "कितनी", "आज", "होगी", "कैसा", "रहेगा", "करना", "जाँच",
    "रही", "रहे", "होता", "होती", "बताएं", "बताइए", "कौन", "कब",
}

ROMAN_MARATHI = {
    "ahe", "aahe", "ahet", "aahet", "kasa", "kase", "kashi", "kasle", "kay", "kanda", "kapus",
    "pivli", "pivale", "pane", "paus", "havaman", "shetkari", "sheti", "pik", "pika", "aushadh",
    "sanga", "karave", "karavi", "majhya", "maza", "mazi", "aajcha", "madhe", "sathi", "chi",
    "padel", "hot", "favarani", "bhav", "yojana",
}
ROMAN_HINDI = {
    "kya", "kaise", "kyon", "kyu", "hai", "hain", "fasal", "patte", "peele", "peeli", "mausam",
    "barish", "chhidkav", "kitni", "matra", "kheti", "pyaz", "kapas", "sinchai", "beej",
    "khad", "keeda", "dawa", "mitti", "batao", "karna", "chahiye", "mera", "meri", "mere",
    "ke", "mein", "hogi", "rahe", "raha", "bhav", "yojana",
}
ENGLISH_CUES = {"the", "is", "are", "how", "what", "when", "where", "why", "which", "should", "can", "do", "does", "for", "my", "with", "this", "that"}

LANGUAGE_NAMES = {"hi": "Hindi", "mr": "Marathi", "en": "English"}


def detect_language(text: str, requested: str | None = None) -> str:
    if requested in LANGUAGE_NAMES:
        return requested
    text = normalize_text(text)
    tokens = tokenize(text)
    token_set = set(tokens)
    if DEVANAGARI.search(text):
        mr_score = sum(1 for token in tokens if token in MARATHI_MARKERS)
        mr_score += sum(1 for token in tokens if len(token) >= 4 and token.endswith(MARATHI_SUFFIXES))
        hi_score = sum(1 for token in tokens if token in HINDI_MARKERS)
        # Devanagari-only proper nouns are ambiguous; Hindi is the safer default.
        if mr_score > hi_score:
            return "mr"
        if hi_score > mr_score:
            return "hi"
        return "hi"
    if tokens:
        mr_score = len(token_set & ROMAN_MARATHI)
        hi_score = len(token_set & ROMAN_HINDI)
        en_score = len(token_set & ENGLISH_CUES)
        if mr_score > hi_score and mr_score > en_score:
            return "mr"
        if hi_score > mr_score and hi_score > en_score:
            return "hi"
    return "en"


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, "English")


def normalize_language(code: str | None) -> str:
    return code if code in LANGUAGE_NAMES else "en"
