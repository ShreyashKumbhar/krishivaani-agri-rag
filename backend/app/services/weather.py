"""Weather tool: free Open-Meteo forecast with an explicitly labelled demo fallback."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from ..config import settings
from ..utils import iso_now, stable_hash, today_ist

logger = logging.getLogger(__name__)

DISTRICTS: dict[str, tuple[float, float]] = {
    "Nashik": (19.9975, 73.7898),
    "Pune": (18.5204, 73.8567),
    "Nagpur": (21.1458, 79.0882),
    "Amravati": (20.9374, 77.7796),
    "Latur": (18.4088, 76.5604),
    "Kolhapur": (16.7050, 74.2433),
    "Solapur": (17.6599, 75.9064),
    "Jalgaon": (21.0077, 75.5626),
    "Satara": (17.6805, 74.0183),
    "Sangli": (16.8524, 74.5815),
    "Ahmednagar": (19.0948, 74.7480),
    "Akola": (20.7002, 77.0082),
    "Yavatmal": (20.3888, 78.1204),
    "Chhatrapati Sambhajinagar": (19.8762, 75.3433),
    "Aurangabad": (19.8762, 75.3433),
    "Bhandara": (21.1700, 79.6500),
}

ADVISORY = {
    "rain_today": {
        "en": "Rain is likely today. Avoid spraying, and delay irrigation if the field is already wet.",
        "hi": "आज बारिश की संभावना है। छिड़काव टालें और खेत पहले से गीला हो तो सिंचाई रोकें।",
        "mr": "आज पाऊस पडण्याची शक्यता आहे. फवारणी टाळा आणि शेत आधीच ओले असल्यास सिंचन थांबवा.",
    },
    "rain_tomorrow": {
        "en": "Rain may arrive tomorrow. Finish only essential spraying if the label allows enough dry hours.",
        "hi": "कल बारिश हो सकती है। केवल जरूरी छिड़काव पूरा करें यदि लेबल पर्याप्त सूखा समय देता हो।",
        "mr": "उद्या पाऊस येऊ शकतो. लेबल पुरेसा कोरडा कालावधी देत असेल तरच आवश्यक फवारणी पूर्ण करा.",
    },
    "heat": {
        "en": "Heat stress risk is high. Irrigate early morning or evening and avoid midday field work.",
        "hi": "गर्मी से तनाव का खतरा अधिक है। सुबह या शाम सिंचाई करें और दोपहर में खेत का काम टालें।",
        "mr": "उष्णतेच्या ताणाचा धोका जास्त आहे. सकाळी किंवा संध्याकाळी सिंचन करा आणि दुपारी शेतातील काम टाळा.",
    },
    "humid": {
        "en": "High humidity increases fungal disease risk. Keep the canopy open and inspect leaves after the weather clears.",
        "hi": "अधिक आर्द्रता से फफूंद रोग का खतरा बढ़ता है। पौधों के बीच हवा रखें और मौसम साफ होने पर पत्तियाँ जाँचें।",
        "mr": "जास्त आर्द्रतेमुळे बुरशीजन्य रोगाचा धोका वाढतो. वेली/पिकांमध्ये हवा खेळती ठेवा आणि हवामान सुधारल्यावर पाने तपासा.",
    },
    "normal": {
        "en": "Weather is generally suitable for field work. Check the product label and the latest local advisory before spraying.",
        "hi": "मौसम खेत के काम के लिए सामान्यतः ठीक है। छिड़काव से पहले उत्पाद लेबल और ताजा स्थानीय सलाह देखें।",
        "mr": "हवामान शेतातील कामासाठी सर्वसाधारणपणे योग्य आहे. फवारणीपूर्वी उत्पादनाचे लेबल आणि ताजा स्थानिक सल्ला पहा.",
    },
}


class WeatherService:
    def __init__(self) -> None:
        self.provider = settings.weather_provider
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.cache_seconds = 600

    def districts(self) -> list[str]:
        return sorted(name for name in DISTRICTS if name not in {"Aurangabad"})

    def lookup(self, district: str = "Nashik") -> dict[str, Any]:
        district = (district or "Nashik").strip().title()
        cache_key = district.lower()
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < self.cache_seconds:
            return cached[1]
        if self.provider == "demo":
            result = self._demo(district, "WEATHER_PROVIDER=demo")
        else:
            try:
                result = self._live(district)
            except Exception as exc:  # network failure -> clearly labelled fallback
                logger.warning("Live weather lookup failed, using demo fallback: %s", exc)
                result = self._demo(district, f"Open-Meteo request failed: {type(exc).__name__}")
        self._cache[cache_key] = (time.monotonic(), result)
        return result

    def _live(self, district: str) -> dict[str, Any]:
        latitude, longitude = DISTRICTS.get(district, (19.7515, 75.7139))
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
            "timezone": "Asia/Kolkata",
            "forecast_days": 3,
        }
        with httpx.Client(timeout=settings.weather_timeout_seconds) as client:
            response = client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            payload = response.json()
        current = payload.get("current", {})
        daily = payload.get("daily", {})
        rain_today = float((daily.get("precipitation_sum") or [0])[0] or 0)
        rain_tomorrow = float((daily.get("precipitation_sum") or [0, 0])[1] or 0) if len(daily.get("precipitation_sum") or []) > 1 else 0
        temp_max = float((daily.get("temperature_2m_max") or [0])[0] or 0)
        temp_min = float((daily.get("temperature_2m_min") or [0])[0] or 0)
        humidity = float(current.get("relative_humidity_2m") or 0)
        temperature = float(current.get("temperature_2m") or 0)
        wind = float(current.get("wind_speed_10m") or 0)
        advisory_key = self._advisory_key(rain_today, rain_tomorrow, temp_max, humidity)
        forecast_days = []
        for index, day in enumerate(daily.get("time") or []):
            forecast_days.append(
                {
                    "date": day,
                    "rain_mm": float((daily.get("precipitation_sum") or [0] * 3)[index] or 0),
                    "temp_max_c": float((daily.get("temperature_2m_max") or [0] * 3)[index] or 0),
                    "temp_min_c": float((daily.get("temperature_2m_min") or [0] * 3)[index] or 0),
                }
            )
        return self._build_result(
            district=district,
            temperature=temperature,
            humidity=humidity,
            wind=wind,
            rain_today=rain_today,
            rain_tomorrow=rain_tomorrow,
            temp_max=temp_max,
            temp_min=temp_min,
            advisory_key=advisory_key,
            data_mode="live",
            provider="Open-Meteo forecast API",
            provider_url="https://open-meteo.com/",
            data_as_of=current.get("time") or iso_now(),
            fetched_at=iso_now(),
            fallback_reason=None,
            forecast_days=forecast_days,
        )

    def _demo(self, district: str, reason: str) -> dict[str, Any]:
        seed = stable_hash(f"{today_ist()}:{district.lower()}:weather")
        temperature = 27 + (seed % 70) / 10.0
        humidity = 55 + (seed % 30)
        wind = 4 + (seed % 14)
        rain_today = 0.0 if seed % 3 else round(2 + (seed % 80) / 10.0, 1)
        rain_tomorrow = 0.0 if seed % 4 else round(1 + (seed % 50) / 10.0, 1)
        temp_max = temperature + 2.5
        temp_min = temperature - 4.0
        advisory_key = self._advisory_key(rain_today, rain_tomorrow, temp_max, humidity)
        return self._build_result(
            district=district,
            temperature=temperature,
            humidity=humidity,
            wind=wind,
            rain_today=rain_today,
            rain_tomorrow=rain_tomorrow,
            temp_max=temp_max,
            temp_min=temp_min,
            advisory_key=advisory_key,
            data_mode="simulated",
            provider="Demo weather fixture v1",
            provider_url="https://open-meteo.com/",
            data_as_of=today_ist(),
            fetched_at=iso_now(),
            fallback_reason=reason,
            forecast_days=[],
        )

    @staticmethod
    def _advisory_key(rain_today: float, rain_tomorrow: float, temp_max: float, humidity: float) -> str:
        if rain_today >= 4:
            return "rain_today"
        if rain_tomorrow >= 4:
            return "rain_tomorrow"
        if temp_max >= 38:
            return "heat"
        if humidity >= 82:
            return "humid"
        return "normal"

    def _build_result(
        self,
        district: str,
        temperature: float,
        humidity: float,
        wind: float,
        rain_today: float,
        rain_tomorrow: float,
        temp_max: float,
        temp_min: float,
        advisory_key: str,
        data_mode: str,
        provider: str,
        provider_url: str,
        data_as_of: str,
        fetched_at: str,
        fallback_reason: str | None,
        forecast_days: list[dict[str, Any]],
    ) -> dict[str, Any]:
        summaries = {
            "en": f"{district}: {temperature:.0f}°C, humidity {humidity:.0f}%, wind {wind:.0f} km/h. Rain today {rain_today:.1f} mm; tomorrow {rain_tomorrow:.1f} mm. High {temp_max:.0f}°C / low {temp_min:.0f}°C.",
            "hi": f"{district}: {temperature:.0f}°C, आर्द्रता {humidity:.0f}%, हवा {wind:.0f} किमी/घंटा। आज बारिश {rain_today:.1f} मिमी; कल {rain_tomorrow:.1f} मिमी। अधिकतम {temp_max:.0f}°C / न्यूनतम {temp_min:.0f}°C।",
            "mr": f"{district}: {temperature:.0f}°C, आर्द्रता {humidity:.0f}%, वारा {wind:.0f} किमी/तास. आज पाऊस {rain_today:.1f} मिमी; उद्या {rain_tomorrow:.1f} मिमी. कमाल {temp_max:.0f}°C / किमान {temp_min:.0f}°C.",
        }
        advisories = {language: ADVISORY[advisory_key][language] for language in ("en", "hi", "mr")}
        return {
            "found": True,
            "district": district,
            "state": "Maharashtra",
            "temperature_c": round(temperature, 1),
            "humidity_pct": round(humidity, 1),
            "wind_kmh": round(wind, 1),
            "rain_today_mm": round(rain_today, 1),
            "rain_tomorrow_mm": round(rain_tomorrow, 1),
            "temp_max_c": round(temp_max, 1),
            "temp_min_c": round(temp_min, 1),
            "forecast_days": forecast_days,
            "summary": summaries,
            "advisory": advisories,
            "advisory_key": advisory_key,
            "data_mode": data_mode,
            "is_live": data_mode == "live",
            "provider": provider,
            "provider_url": provider_url,
            "source_name": "Open-Meteo (forecast)" if data_mode == "live" else "Simulated demonstration dataset",
            "data_as_of": data_as_of,
            "fetched_at": fetched_at,
            "fallback_reason": fallback_reason,
            "provenance_note": (
                "LIVE forecast from Open-Meteo. This is not an IMD Agromet bulletin; check agromet.imd.gov.in for official district advice."
                if data_mode == "live"
                else "SIMULATED DATA. The live weather provider was unavailable or disabled. This is not a real forecast."
            ),
            "disclaimer": "Forecasts are indicative. For official district agromet advice use the IMD Agromet bulletin.",
        }
