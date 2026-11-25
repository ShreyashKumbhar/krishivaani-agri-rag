"""Mandi price tool with a simulated demo provider and an optional live adapter.

The demo provider is deterministic for a given day and is always labelled
SIMULATED. If DATA_GOV_IN_API_KEY is configured, the Agmarknet resource on
data.gov.in is queried and the result is labelled LIVE with the arrival date.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from ..config import settings
from ..utils import iso_now, stable_hash, today_ist

logger = logging.getLogger(__name__)

COMMODITIES: dict[str, dict[str, Any]] = {
    "onion": {"hi": "प्याज", "mr": "कांदा", "base": 2150, "spread": 420, "market": "Lasalgaon", "market_hi": "लासलगाव", "market_mr": "लासलगाव", "district": "Nashik"},
    "soybean": {"hi": "सोयाबीन", "mr": "सोयाबीन", "base": 4480, "spread": 300, "market": "Latur", "market_hi": "लातूर", "market_mr": "लातूर", "district": "Latur"},
    "cotton": {"hi": "कपास", "mr": "कापूस", "base": 7050, "spread": 380, "market": "Amravati", "market_hi": "अमरावती", "market_mr": "अमरावती", "district": "Amravati"},
    "tomato": {"hi": "टमाटर", "mr": "टोमॅटो", "base": 1850, "spread": 900, "market": "Pune", "market_hi": "पुणे", "market_mr": "पुणे", "district": "Pune"},
    "grapes": {"hi": "अंगूर", "mr": "द्राक्ष", "base": 5600, "spread": 1400, "market": "Nashik", "market_hi": "नाशिक", "market_mr": "नाशिक", "district": "Nashik"},
    "sugarcane": {"hi": "गन्ना", "mr": "ऊस", "base": 3050, "spread": 220, "market": "Kolhapur", "market_hi": "कोल्हापुर", "market_mr": "कोल्हापूर", "district": "Kolhapur"},
    "wheat": {"hi": "गेहूं", "mr": "गहू", "base": 2480, "spread": 260, "market": "Ahmednagar", "market_hi": "अहमदनगर", "market_mr": "अहमदनगर", "district": "Ahmednagar"},
    "rice": {"hi": "धान", "mr": "भात", "base": 2320, "spread": 250, "market": "Bhandara", "market_hi": "भंडारा", "market_mr": "भंडारा", "district": "Bhandara"},
    "tur": {"hi": "अरहर", "mr": "तूर", "base": 7100, "spread": 400, "market": "Latur", "market_hi": "लातूर", "market_mr": "लातूर", "district": "Latur"},
    "gram": {"hi": "चना", "mr": "हरभरा", "base": 5250, "spread": 350, "market": "Solapur", "market_hi": "सोलापुर", "market_mr": "सोलापूर", "district": "Solapur"},
    "groundnut": {"hi": "मूंगफली", "mr": "भुईमूग", "base": 6200, "spread": 420, "market": "Jalgaon", "market_hi": "जलगांव", "market_mr": "जळगाव", "district": "Jalgaon"},
    "jowar": {"hi": "ज्वार", "mr": "ज्वारी", "base": 2900, "spread": 300, "market": "Solapur", "market_hi": "सोलापुर", "market_mr": "सोलापूर", "district": "Solapur"},
}

MARKET_NAMES = {
    "lasalgaon": "Lasalgaon", "pimpalgaon": "Pimpalgaon", "latur": "Latur", "amravati": "Amravati",
    "akola": "Akola", "pune": "Pune", "nashik": "Nashik", "kolhapur": "Kolhapur", "solapur": "Solapur",
    "jalgaon": "Jalgaon", "ahmednagar": "Ahmednagar", "bhandara": "Bhandara",
}


class MandiService:
    def __init__(self) -> None:
        self.provider = settings.mandi_provider
        self.live_enabled = settings.mandi_live

    def commodities(self) -> list[dict[str, str]]:
        return [{"key": key, "en": key.title(), "hi": value["hi"], "mr": value["mr"]} for key, value in COMMODITIES.items()]

    def lookup(self, commodity: str | None = None, market: str | None = None, state: str = "Maharashtra") -> dict[str, Any]:
        commodity_key = (commodity or "").strip().lower()
        if not commodity_key:
            return {"found": False, "reason": "COMMODITY_MISSING", "data_mode": "simulated", "is_live": False}
        if commodity_key not in COMMODITIES:
            return {
                "found": False,
                "reason": "COMMODITY_NOT_IN_DEMO_DATASET",
                "commodity": commodity_key,
                "data_mode": "simulated",
                "is_live": False,
                "provider": "Demo mandi fixture v1",
                "provenance_note": "The bundled demo mandi dataset covers onion, soybean, cotton, tomato, grapes, sugarcane, wheat, rice, tur, gram, groundnut and jowar.",
            }
        if self.live_enabled:
            try:
                return self._lookup_live(commodity_key, market, state)
            except Exception as exc:  # network/credential/parse failure -> labelled fallback
                logger.warning("Live mandi lookup failed, falling back to demo data: %s", exc)
                result = self._lookup_demo(commodity_key, market)
                result["fallback_reason"] = f"Live provider failed: {type(exc).__name__}"
                return result
        return self._lookup_demo(commodity_key, market)

    def _lookup_demo(self, commodity: str, market: str | None) -> dict[str, Any]:
        meta = COMMODITIES[commodity]
        market_name = MARKET_NAMES.get((market or "").strip().lower(), market) or meta["market"]
        seed = stable_hash(f"{today_ist()}:{commodity}:{market_name}")
        swing = (seed % 1000) / 1000.0  # 0..1, deterministic for the day
        modal = int(round(meta["base"] + (swing - 0.5) * meta["spread"]))
        minimum = int(round(modal - meta["spread"] * (0.35 + (seed % 17) / 100)))
        maximum = int(round(modal + meta["spread"] * (0.35 + (seed % 23) / 100)))
        return {
            "found": True,
            "commodity": commodity,
            "commodity_labels": {"en": commodity.title(), "hi": meta["hi"], "mr": meta["mr"]},
            "market": market_name,
            "market_labels": {"en": market_name, "hi": meta["market_hi"], "mr": meta["market_mr"]},
            "district": meta["district"],
            "state": "Maharashtra",
            "min_price_inr_per_quintal": minimum,
            "max_price_inr_per_quintal": maximum,
            "modal_price_inr_per_quintal": modal,
            "unit": "INR per quintal",
            "data_mode": "simulated",
            "is_live": False,
            "provider": "Demo mandi fixture v1",
            "provider_url": "https://agmarknet.gov.in/",
            "source_name": "Simulated demonstration dataset (not Agmarknet)",
            "data_as_of": today_ist(),
            "fetched_at": iso_now(),
            "provenance_note": "SIMULATED DATA. Generated deterministically for this demo; not a live mandi quote. Configure DATA_GOV_IN_API_KEY for the live Agmarknet adapter.",
            "disclaimer": "Prices vary by variety, grade, arrivals and market. Verify with Agmarknet/e-NAM or the local mandi before selling.",
        }

    def _lookup_live(self, commodity: str, market: str | None, state: str) -> dict[str, Any]:
        meta = COMMODITIES[commodity]
        params = {
            "api-key": settings.data_gov_in_api_key,
            "format": "json",
            "limit": 100,
            "filters[state]": state,
            "filters[commodity]": commodity.title(),
        }
        url = f"https://api.data.gov.in/resource/{settings.mandi_resource_id}"
        with httpx.Client(timeout=15) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        records = payload.get("records") or []
        if not records:
            raise ValueError("No records returned by data.gov.in")
        chosen = records[0]
        if market:
            for record in records:
                if market.lower() in str(record.get("market", "")).lower():
                    chosen = record
                    break
        def number(key: str) -> int:
            try:
                return int(float(str(chosen.get(key, "0")).replace(",", "")))
            except (TypeError, ValueError):
                return 0
        return {
            "found": True,
            "commodity": commodity,
            "commodity_labels": {"en": commodity.title(), "hi": meta["hi"], "mr": meta["mr"]},
            "market": chosen.get("market") or meta["market"],
            "market_labels": {"en": chosen.get("market") or meta["market"], "hi": chosen.get("market") or meta["market"], "mr": chosen.get("market") or meta["market"]},
            "district": chosen.get("district") or meta["district"],
            "state": chosen.get("state") or state,
            "variety": chosen.get("variety", ""),
            "grade": chosen.get("grade", ""),
            "min_price_inr_per_quintal": number("min_price"),
            "max_price_inr_per_quintal": number("max_price"),
            "modal_price_inr_per_quintal": number("modal_price"),
            "unit": "INR per quintal",
            "data_mode": "live",
            "is_live": True,
            "provider": "data.gov.in Agmarknet resource",
            "provider_url": "https://agmarknet.gov.in/",
            "source_name": "Agmarknet via data.gov.in",
            "data_as_of": chosen.get("arrival_date") or today_ist(),
            "fetched_at": iso_now(),
            "provenance_note": "Live record returned by the data.gov.in Agmarknet resource. Verify grade, variety and arrival date before selling.",
            "disclaimer": "Prices vary by variety, grade, arrivals and market. Verify with Agmarknet/e-NAM or the local mandi before selling.",
        }


def _format_inr(value: int) -> str:
    return f"₹{value:,}"
