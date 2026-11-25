"""Grounded answer generation.

Default provider: a deterministic, extractive "grounded template composer". It
is explicitly NOT a large language model. It selects sentences from approved
evidence and adds a source citation and a demo/safety note.

Optional providers: an OpenAI-compatible chat endpoint (set LLM_PROVIDER=openai
and OPENAI_API_KEY) or a local Ollama server (LLM_PROVIDER=ollama). LLM output
is checked against the evidence and falls back to the template composer if the
grounding check fails. The API always reports which provider produced an answer.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ..config import settings
from ..utils import content_tokens, normalize_text, split_sentences
from .glossary import Glossary

logger = logging.getLogger(__name__)

SAFETY_NOTE = {
    "en": "Safety note: use pesticides only as per the product label or a written recommendation from a qualified agronomist/KVK. Never guess a dose. For help call Kisan Call Centre 1800-180-1551.",
    "hi": "सुरक्षा सूचना: कीटनाशक केवल उत्पाद लेबल या योग्य कृषि विशेषज्ञ/केवीके की लिखित सलाह के अनुसार ही उपयोग करें। मात्रा का अनुमान कभी न लगाएँ। सहायता के लिए किसान कॉल सेंटर 1800-180-1551 पर कॉल करें।",
    "mr": "सुरक्षा सूचना: कीटकनाशक केवळ उत्पादनाचे लेबल किंवा पात्र कृषी तज्ज्ञ/केव्हीकेच्या लिखित सल्ल्यानुसारच वापरा. मात्रेचा अंदाज कधीही लावू नका. मदतीसाठी शेतकरी कॉल सेंटर 1800-180-1551 वर कॉल करा.",
}

DEMO_NOTE = {
    "en": "Demonstration knowledge base: verify this summary against the linked official source before acting.",
    "hi": "प्रदर्शन ज्ञानकोश: कार्रवाई से पहले इस सारांश को दिए गए आधिकारिक स्रोत से जाँचें।",
    "mr": "प्रात्यक्षिक ज्ञानकोश: कृतीपूर्वी हा सारांश दिलेल्या अधिकृत स्रोताशी तपासा.",
}

DISCLAIMER = {
    "en": "Informational guidance only; not a substitute for a certified agronomist or the official scheme/weather bulletin.",
    "hi": "यह केवल जानकारी है; प्रमाणित कृषि विशेषज्ञ या आधिकारिक योजना/मौसम बुलेटिन का विकल्प नहीं।",
    "mr": "ही केवळ माहिती आहे; प्रमाणित कृषी तज्ज्ञ किंवा अधिकृत योजना/हवामान बुलेटिनचा पर्याय नाही.",
}

REFUSAL = {
    "CHEMICAL_DOSAGE_BLOCKED": {
        "en": "I cannot give a pesticide or chemical dosage. An incorrect dose can damage your crop, leave illegal residues or harm you. Please read the product label or get a written recommendation from your KVK. For immediate help call the Kisan Call Centre on 1800-180-1551.",
        "hi": "मैं कीटनाशक या रसायन की मात्रा नहीं बता सकता। गलत मात्रा फसल को नुकसान पहुँचा सकती है, अवैध अवशेष छोड़ सकती है या आपको हानि पहुँचा सकती है। कृपया उत्पाद का लेबल पढ़ें या अपने कृषि विज्ञान केंद्र से लिखित सलाह लें। तुरंत सहायता के लिए किसान कॉल सेंटर 1800-180-1551 पर कॉल करें।",
        "mr": "मी कीटकनाशक किंवा रसायनाची मात्रा सांगू शकत नाही. चुकीच्या मात्रेमुळे पिकाचे नुकसान होऊ शकते, बेकायदेशीर अवशेष राहू शकतात किंवा तुम्हाला इजा होऊ शकते. कृपया उत्पादनाचे लेबल वाचा किंवा तुमच्या कृषी विज्ञान केंद्राकडून लिखित सल्ला घ्या. तातडीच्या मदतीसाठी शेतकरी कॉल सेंटर 1800-180-1551 वर कॉल करा.",
    },
    "OUT_OF_SCOPE": {
        "en": "I can only help with crop advice, pest and disease questions, government schemes, mandi prices and weather for farmers. I will not guess an answer outside that scope. For agricultural help call the Kisan Call Centre on 1800-180-1551.",
        "hi": "मैं केवल फसल सलाह, कीट-रोग, सरकारी योजनाओं, मंडी भाव और मौसम से जुड़े किसान सवालों में मदद कर सकता हूँ। इस दायरे से बाहर अनुमान नहीं लगाऊँगा। कृषि सहायता के लिए किसान कॉल सेंटर 1800-180-1551 पर कॉल करें।",
        "mr": "मी केवळ पीक सल्ला, कीड-रोग, सरकारी योजना, बाजार भाव आणि हवामान या शेतकरी प्रश्नांमध्ये मदत करू शकतो. या व्याप्तीबाहेर अंदाज लावणार नाही. कृषी मदतीसाठी शेतकरी कॉल सेंटर 1800-180-1551 वर कॉल करा.",
    },
    "INSUFFICIENT_EVIDENCE": {
        "en": "I do not have enough verified evidence to answer this safely, so I will not guess. Please contact your local KVK or call the Kisan Call Centre on 1800-180-1551.",
        "hi": "इसका सुरक्षित उत्तर देने के लिए मेरे पास पर्याप्त सत्यापित प्रमाण नहीं हैं, इसलिए मैं अनुमान नहीं लगाऊँगा। कृपया अपने स्थानीय कृषि विज्ञान केंद्र से संपर्क करें या किसान कॉल सेंटर 1800-180-1551 पर कॉल करें।",
        "mr": "सुरक्षित उत्तर देण्यासाठी माझ्याकडे पुरेसे पडताळलेले पुरावे नाहीत, म्हणून मी अंदाज लावणार नाही. कृपया तुमच्या स्थानिक कृषी विज्ञान केंद्राशी संपर्क करा किंवा शेतकरी कॉल सेंटर 1800-180-1551 वर कॉल करा.",
    },
    "NO_EVIDENCE": {
        "en": "I could not find an approved agricultural source for this question, so I will not guess. Please contact your local KVK or the Kisan Call Centre on 1800-180-1551.",
        "hi": "इस सवाल के लिए मुझे कोई स्वीकृत कृषि स्रोत नहीं मिला, इसलिए मैं अनुमान नहीं लगाऊँगा। कृपया स्थानीय कृषि विज्ञान केंद्र या किसान कॉल सेंटर 1800-180-1551 से संपर्क करें।",
        "mr": "या प्रश्नासाठी मला मंजूर कृषी स्रोत सापडला नाही, म्हणून मी अंदाज लावणार नाही. कृपया स्थानिक कृषी विज्ञान केंद्र किंवा शेतकरी कॉल सेंटर 1800-180-1551 शी संपर्क करा.",
    },
    "LOW_CONFIDENCE": {
        "en": "I am not confident enough in the available evidence to answer safely. Please ask a more specific question or contact your local KVK / Kisan Call Centre on 1800-180-1551.",
        "hi": "उपलब्ध प्रमाणों पर मेरा भरोसा सुरक्षित उत्तर देने के लिए पर्याप्त नहीं है। कृपया अधिक स्पष्ट सवाल पूछें या स्थानीय कृषि विज्ञान केंद्र / किसान कॉल सेंटर 1800-180-1551 से संपर्क करें।",
        "mr": "उपलब्ध पुराव्यांवर मला सुरक्षित उत्तर देण्याइतका विश्वास नाही. कृपया अधिक स्पष्ट प्रश्न विचारा किंवा स्थानिक कृषी विज्ञान केंद्र / शेतकरी कॉल सेंटर 1800-180-1551 शी संपर्क करा.",
    },
}

CLARIFY = {
    "MISSING_COMMODITY": {
        "en": "Which commodity do you want the mandi price for? For example onion, soybean, cotton, tomato or grapes.",
        "hi": "आप किस फसल का मंडी भाव जानना चाहते हैं? जैसे प्याज, सोयाबीन, कपास, टमाटर या अंगूर।",
        "mr": "तुम्हाला कोणत्या पिकाचा बाजार भाव हवा आहे? उदाहरणार्थ कांदा, सोयाबीन, कापूस, टोमॅटो किंवा द्राक्ष.",
    },
    "MISSING_LOCATION": {
        "en": "Which district should I check the weather for? For example Nashik, Pune, Nagpur or Latur.",
        "hi": "मैं किस जिले का मौसम देखूँ? जैसे नाशिक, पुणे, नागपुर या लातूर।",
        "mr": "मी कोणत्या जिल्ह्याचे हवामान पाहू? उदाहरणार्थ नाशिक, पुणे, नागपूर किंवा लातूर.",
    },
    "AMBIGUOUS_QUERY": {
        "en": "Please tell me the crop and what you see, for example: cotton leaves are turning yellow, or soybean pods have holes.",
        "hi": "कृपया फसल और लक्षण बताएँ, जैसे: कपास की पत्तियाँ पीली हो रही हैं, या सोयाबीन की फलियों में छेद हैं।",
        "mr": "कृपया पीक आणि लक्षणे सांगा, उदाहरणार्थ: कापसाची पाने पिवळी होत आहेत, किंवा सोयाबीनच्या शेंगांना छिद्रे आहेत.",
    },
    "LOW_ASR_CONFIDENCE": {
        "en": "I could not hear the question clearly. Please repeat it or type it.",
        "hi": "मैं सवाल स्पष्ट नहीं सुन पाया। कृपया दोबारा बोलें या लिखें।",
        "mr": "मला प्रश्न स्पष्ट ऐकू आला नाही. कृपया पुन्हा बोला किंवा लिहा.",
    },
}

FOLLOWUPS = {
    "pest_disease": {
        "en": ["What should I check first?", "Is this a pest or a nutrient problem?", "When should I contact the KVK?"],
        "hi": ["पहले क्या जाँचें?", "यह कीट है या पोषक तत्व की कमी?", "कृषि विज्ञान केंद्र से कब संपर्क करें?"],
        "mr": ["आधी काय तपासावे?", "हा कीड आहे की पोषक तत्वांची कमतरता?", "कृषी विज्ञान केंद्राशी कधी संपर्क करावा?"],
    },
    "scheme": {
        "en": ["What documents are needed?", "How do I check my application status?", "Where is the official portal?"],
        "hi": ["कौन से दस्तावेज चाहिए?", "आवेदन की स्थिति कैसे देखें?", "आधिकारिक पोर्टल कहाँ है?"],
        "mr": ["कोणती कागदपत्रे लागतात?", "अर्जाची स्थिती कशी पाहू?", "अधिकृत पोर्टल कुठे आहे?"],
    },
    "crop_advice": {
        "en": ["What should I do this week?", "How do I check soil moisture?", "Which practice is safest?"],
        "hi": ["इस हफ्ते क्या करें?", "मिट्टी की नमी कैसे जाँचें?", "कौन सा तरीका सबसे सुरक्षित है?"],
        "mr": ["या आठवड्यात काय करावे?", "मातीतील ओलावा कसा तपासावा?", "कोणती पद्धत सर्वात सुरक्षित आहे?"],
    },
    "pesticide_safety": {
        "en": ["What protective equipment do I need?", "What is the waiting period?", "Where can I get the label checked?"],
        "hi": ["कौन सा सुरक्षा सामान चाहिए?", "प्रतीक्षा अवधि कितनी है?", "लेबल कहाँ जाँचें?"],
        "mr": ["कोणती सुरक्षा सामग्री लागते?", "प्रतीक्षा कालावधी किती आहे?", "लेबल कुठे तपासावे?"],
    },
    "market_price": {
        "en": ["Compare nearby mandis", "Check the arrival date", "What is the modal price?"],
        "hi": ["आसपास की मंडियों की तुलना करें", "आवक की तारीख देखें", "मॉडल भाव क्या है?"],
        "mr": ["जवळच्या बाजारांची तुलना करा", "आवकीची तारीख पहा", "मॉडेल भाव काय आहे?"],
    },
    "weather": {
        "en": ["Will it rain tomorrow?", "Is it safe to spray today?", "What is the humidity?"],
        "hi": ["कल बारिश होगी?", "आज छिड़काव सुरक्षित है?", "आर्द्रता कितनी है?"],
        "mr": ["उद्या पाऊस पडेल का?", "आज फवारणी सुरक्षित आहे का?", "आर्द्रता किती आहे?"],
    },
}


class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.mode = settings.llm_mode
        self.available = self.mode in {"hosted-llm", "local-llm"}
        self.name = self._name()

    def _name(self) -> str:
        if self.mode == "hosted-llm":
            return f"openai-compatible:{settings.openai_model}"
        if self.mode == "local-llm":
            return f"ollama:{settings.ollama_model}"
        return "template-grounded-v1 (no LLM)"

    def complete(self, system: str, user: str) -> str:
        if not self.available:
            raise RuntimeError("No LLM provider configured")
        if self.mode == "hosted-llm":
            payload = {
                "model": settings.openai_model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": 0.1,
                "max_tokens": 420,
            }
            headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
            with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
                response = client.post(f"{settings.openai_base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        payload = {
            "model": settings.ollama_model,
            "stream": False,
            "options": {"temperature": 0.1},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return (data.get("message") or {}).get("content", "").strip()


class GroundedComposer:
    def __init__(self, glossary: Glossary) -> None:
        self.glossary = glossary
        self.llm = LLMClient()

    def compose(
        self,
        query: str,
        language: str,
        understanding,
        evidence: list[dict[str, Any]],
        tool_data: dict[str, Any] | None = None,
        tool_name: str | None = None,
        safety_note_required: bool = False,
    ) -> dict[str, Any]:
        language = language if language in {"en", "hi", "mr"} else "en"
        if tool_data is not None:
            answer = self._tool_answer(tool_name or "tool", tool_data, language)
            return {
                "answer": answer,
                "generation_provider": "structured-tool-formatter-v1",
                "generation_mode": "deterministic",
                "grounding_score": 1.0,
                "llm_fallback_reason": None,
                "citations": [],
                "safety_note": SAFETY_NOTE[language] if safety_note_required else None,
            }

        localized = self._prefer_language(evidence, language)
        template_answer = self._template_answer(query, language, localized)
        citations = self._citations(localized)
        provider = "template-grounded-v1 (no LLM)"
        mode = "deterministic-fallback"
        fallback_reason = None
        answer = template_answer
        grounding = self._grounding_score(template_answer, localized)

        if self.llm.available and localized:
            try:
                llm_answer = self._llm_answer(query, language, localized)
                llm_grounding = self._grounding_score(llm_answer, localized)
                if llm_answer and llm_grounding >= 0.45 and not self._looks_unsafe(llm_answer):
                    answer = self._add_citation_line(llm_answer, language, localized)
                    grounding = llm_grounding
                    provider = self.llm.name
                    mode = "hosted-llm" if self.llm.mode == "hosted-llm" else "local-llm"
                else:
                    fallback_reason = "LLM output failed the grounding or safety check"
            except Exception as exc:  # pragma: no cover - optional integration
                logger.warning("LLM generation failed, using template composer: %s", exc)
                fallback_reason = f"LLM unavailable: {type(exc).__name__}"

        if safety_note_required:
            answer = answer.rstrip() + " " + SAFETY_NOTE[language]
        return {
            "answer": answer,
            "generation_provider": provider,
            "generation_mode": mode,
            "grounding_score": round(grounding, 4),
            "llm_fallback_reason": fallback_reason,
            "citations": citations,
            "safety_note": SAFETY_NOTE[language] if safety_note_required else None,
        }

    @staticmethod
    def _prefer_language(evidence: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
        # Keep the best passage per document, preferring the answer language.
        best_by_doc: dict[str, dict[str, Any]] = {}
        for item in evidence:
            current = best_by_doc.get(item["document_id"])
            if current is None:
                best_by_doc[item["document_id"]] = item
                continue
            current_match = current.get("language") == language
            new_match = item.get("language") == language
            if new_match and not current_match:
                best_by_doc[item["document_id"]] = item
        ordered = sorted(best_by_doc.values(), key=lambda item: (item.get("language") == language, item.get("score", 0)), reverse=True)
        return ordered[:3]

    def _template_answer(self, query: str, language: str, evidence: list[dict[str, Any]]) -> str:
        if not evidence:
            return REFUSAL["NO_EVIDENCE"][language]
        body_parts: list[str] = []
        used_sources: list[str] = []
        for item in evidence[:2]:
            sentences = split_sentences(item.get("text", ""))
            if not sentences:
                continue
            take = sentences[:3]
            text = " ".join(take)
            if len(text) > 520:
                text = text[:520].rsplit(" ", 1)[0] + "…"
            body_parts.append(text)
            if item.get("source_name") and item["source_name"] not in used_sources:
                used_sources.append(item["source_name"])
        body = " ".join(body_parts).strip()
        source_text = "; ".join(used_sources[:2])
        if language == "hi":
            answer = f"स्वीकृत संदर्भ के अनुसार: {body} स्रोत: {source_text}। {DEMO_NOTE['hi']}"
        elif language == "mr":
            answer = f"मंजूर संदर्भानुसार: {body} स्रोत: {source_text}. {DEMO_NOTE['mr']}"
        else:
            answer = f"According to the approved reference: {body} Source: {source_text}. {DEMO_NOTE['en']}"
        return normalize_text(answer)

    def _citations(self, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations = []
        seen: set[str] = set()
        for item in evidence:
            if item["document_id"] in seen:
                continue
            seen.add(item["document_id"])
            citations.append(
                {
                    "document_id": item["document_id"],
                    "title": item.get("title") or item.get("title_en"),
                    "publisher": item.get("publisher"),
                    "source_name": item.get("source_name"),
                    "source_url": item.get("source_url"),
                    "publication_date": item.get("publication_date"),
                    "source_date_note": item.get("source_date_note"),
                    "licence": item.get("licence"),
                    "excerpt": item.get("excerpt") or item.get("text", "")[:260],
                    "is_demo": item.get("is_demo", True),
                    "category": item.get("category"),
                }
            )
        return citations

    def _tool_answer(self, tool_name: str, data: dict[str, Any], language: str) -> str:
        if tool_name == "mandi":
            labels = data.get("commodity_labels", {})
            market = data.get("market_labels", {}).get(language) or data.get("market")
            commodity = labels.get(language) or labels.get("en") or data.get("commodity")
            modal = data.get("modal_price_inr_per_quintal", 0)
            minimum = data.get("min_price_inr_per_quintal", 0)
            maximum = data.get("max_price_inr_per_quintal", 0)
            mode = "SIMULATED" if data.get("data_mode") == "simulated" else "LIVE"
            as_of = data.get("data_as_of")
            if language == "hi":
                return (
                    f"{market} मंडी में {commodity} का मॉडल भाव ₹{modal:,} प्रति क्विंटल है "
                    f"(न्यूनतम ₹{minimum:,}, अधिकतम ₹{maximum:,})। डेटा तिथि: {as_of}। "
                    f"डेटा स्थिति: {mode} — {'यह लाइव भाव नहीं है।' if mode == 'SIMULATED' else 'यह लाइव रिकॉर्ड है।'} "
                    f"स्रोत: {data.get('source_name')}। बेचने से पहले अगमार्कनेट/ई-नाम या स्थानीय मंडी से पुष्टि करें।"
                )
            if language == "mr":
                return (
                    f"{market} बाजारात {commodity}चा मॉडेल भाव ₹{modal:,} प्रति क्विंटल आहे "
                    f"(किमान ₹{minimum:,}, कमाल ₹{maximum:,}). डेटा तारीख: {as_of}. "
                    f"डेटा स्थिती: {mode} — {'हा थेट भाव नाही.' if mode == 'SIMULATED' else 'ही थेट नोंद आहे.'} "
                    f"स्रोत: {data.get('source_name')}. विकण्यापूर्वी अगमार्कनेट/ई-नाम किंवा स्थानिक बाजारात खात्री करा."
                )
            return (
                f"{commodity} at {market} mandi: modal ₹{modal:,} per quintal "
                f"(min ₹{minimum:,}, max ₹{maximum:,}). Data date: {as_of}. "
                f"Data status: {mode} — {'this is not a live quote.' if mode == 'SIMULATED' else 'this is a live record.'} "
                f"Source: {data.get('source_name')}. Verify with Agmarknet/e-NAM or the local mandi before selling."
            )
        if tool_name == "weather":
            summary = (data.get("summary") or {}).get(language) or (data.get("summary") or {}).get("en", "")
            advisory = (data.get("advisory") or {}).get(language) or (data.get("advisory") or {}).get("en", "")
            mode = "SIMULATED" if data.get("data_mode") == "simulated" else "LIVE"
            if language == "hi":
                return f"{summary} {advisory} डेटा स्थिति: {mode}। स्रोत: {data.get('provider')}। आधिकारिक जिला सलाह के लिए आईएमडी कृषि मौसम बुलेटिन देखें।"
            if language == "mr":
                return f"{summary} {advisory} डेटा स्थिती: {mode}. स्रोत: {data.get('provider')}. अधिकृत जिल्हा सल्ल्यासाठी आयएमडी कृषी हवामान बुलेटिन पहा."
            return f"{summary} {advisory} Data status: {mode}. Source: {data.get('provider')}. For official district advice, check the IMD Agromet bulletin."
        return str(data)

    def _llm_answer(self, query: str, language: str, evidence: list[dict[str, Any]]) -> str:
        language_name = {"hi": "Hindi", "mr": "Marathi", "en": "English"}[language]
        passages = "\n\n".join(
            f"[{index + 1}] {item.get('source_name')} | {item.get('title')}\n{item.get('text')}"
            for index, item in enumerate(evidence)
        )
        system = (
            "You are a careful agricultural extension assistant for Indian farmers. "
            "Answer ONLY from the supplied passages. Do not add facts, pesticide doses, scheme rules or numbers that are not in the passages. "
            "If the passages are insufficient, say so. Keep the answer short and spoken-style (under 120 words), with simple sentences. "
            "Do not invent source names. The application adds citations after your answer."
        )
        user = (
            f"Farmer question: {query}\n\nAnswer language: {language_name}\n\n"
            f"Approved passages:\n{passages}\n\nWrite only the short answer body in {language_name}. "
            "Do not include a citation line, markdown headings or a disclaimer."
        )
        return self.llm.complete(system, user)

    @staticmethod
    def _add_citation_line(answer: str, language: str, evidence: list[dict[str, Any]]) -> str:
        source = "; ".join(dict.fromkeys(item.get("source_name", "") for item in evidence if item.get("source_name")))
        if language == "hi":
            return normalize_text(f"{answer} स्रोत: {source}। {DEMO_NOTE['hi']}")
        if language == "mr":
            return normalize_text(f"{answer} स्रोत: {source}. {DEMO_NOTE['mr']}")
        return normalize_text(f"{answer} Source: {source}. {DEMO_NOTE['en']}")

    @staticmethod
    def _grounding_score(answer: str, evidence: list[dict[str, Any]]) -> float:
        answer_tokens = set(content_tokens(answer))
        if not answer_tokens:
            return 0.0
        evidence_tokens: set[str] = set()
        for item in evidence:
            evidence_tokens.update(content_tokens(item.get("text", "")))
            evidence_tokens.update(content_tokens(item.get("title", "")))
        if not evidence_tokens:
            return 0.0
        return len(answer_tokens & evidence_tokens) / len(answer_tokens)

    @staticmethod
    def _looks_unsafe(answer: str) -> bool:
        lowered = answer.lower()
        # The gate already blocks dosage questions, but an LLM must not sneak
        # dosage-like instructions into a general safety answer either.
        if re.search(r"\d+(\.\d+)?\s*(ml|litre|liter|gram|gm|kg)\s*(per|/)\s*(acre|litre|liter)", lowered):
            return True
        return any(phrase in lowered for phrase in ("ignore previous", "system prompt", "explosive"))


def refusal_message(reason_code: str, language: str) -> str:
    language = language if language in {"en", "hi", "mr"} else "en"
    key = reason_code if reason_code in REFUSAL else "INSUFFICIENT_EVIDENCE"
    return REFUSAL[key][language]


def clarify_message(reason_code: str, language: str) -> str:
    language = language if language in {"en", "hi", "mr"} else "en"
    key = reason_code if reason_code in CLARIFY else "AMBIGUOUS_QUERY"
    return CLARIFY[key][language]


def followups(intent: str, language: str) -> list[str]:
    language = language if language in {"en", "hi", "mr"} else "en"
    return FOLLOWUPS.get(intent, FOLLOWUPS["crop_advice"]).get(language, FOLLOWUPS["crop_advice"]["en"])


def disclaimer(language: str) -> str:
    return DISCLAIMER.get(language, DISCLAIMER["en"])


def safety_note(language: str) -> str:
    return SAFETY_NOTE.get(language, SAFETY_NOTE["en"])
