"""End-to-end smoke test against a running KrishiVaani API.

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url http://127.0.0.1:8000

The script only reads data and asks normal questions; it does not delete
knowledge documents or glossary entries. It prints a PASS/FAIL line per check
and exits non-zero if any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the running KrishiVaani API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    client = httpx.Client(base_url=base, timeout=60.0)

    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        status = "PASS" if condition else "FAIL"
        print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
        if not condition:
            failures.append(name)

    def query(text: str, language: str | None = None, **extra) -> dict:
        payload = {"text": text, **extra}
        if language:
            payload["language"] = language
        response = client.post("/api/assistant/query", json=payload)
        response.raise_for_status()
        return response.json()

    try:
        health = client.get("/api/health").json()
        check("health", health.get("status") == "ok" and health.get("documents", 0) >= 18, f"{health.get('documents')} docs / {health.get('chunks')} chunks")
        check("default generation is honest", "no LLM" in health.get("llm", {}).get("provider", ""), health.get("llm", {}).get("provider", ""))
        check("mandi is labelled simulated by default", health.get("mandi_mode") == "simulated")

        config = client.get("/api/config").json()
        languages = {item["code"] for item in config.get("languages", [])}
        check("languages hi/mr/en", {"hi", "mr", "en"} <= languages, ",".join(sorted(languages)))
        check("dosage blocking advertised", config.get("safety", {}).get("chemical_dosage_blocked") is True)
        check("helpline advertised", config.get("safety", {}).get("helpline") == "1800-180-1551")

        en = query("Why are the leaves of my cotton crop turning yellow?", "en")
        check("english cotton answer", en.get("decision") == "answer" and bool(en.get("citations")), en.get("reason_code", ""))
        check("english answer cites KB", (en.get("citations") or [{}])[0].get("document_id") == "cotton-yellow-leaves")

        hi = query("मेरी कपास की पत्तियाँ पीली क्यों हो रही हैं?", "hi")
        check("hindi cotton answer", hi.get("decision") == "answer" and hi.get("language") == "hi", hi.get("reason_code", ""))

        mr = query("माझ्या कापसाची पाने पिवळी का होत आहेत?", "mr")
        check("marathi cotton answer", mr.get("decision") == "answer" and mr.get("language") == "mr", mr.get("reason_code", ""))

        dosage = query("What is the exact dose of imidacloprid to spray on cotton?", "en")
        check("chemical dosage refused", dosage.get("decision") == "refuse" and dosage.get("reason_code") == "CHEMICAL_DOSAGE_BLOCKED")
        check("refusal refers to helpline", "1800-180-1551" in dosage.get("answer", ""))

        ambiguous = query("Why is it yellow?", "en")
        check("ambiguous asks to repeat", ambiguous.get("decision") == "ask_to_repeat", ambiguous.get("reason_code", ""))

        off_topic = query("Who will win the next election?", "en")
        check("out-of-scope refused", off_topic.get("decision") == "refuse" and off_topic.get("reason_code") == "OUT_OF_SCOPE")

        mandi = query("What is the current onion mandi price?", "en")
        check("mandi tool answer", mandi.get("decision") == "answer" and mandi.get("intent") == "market_price")
        check("mandi labelled SIMULATED", mandi.get("tool_data", {}).get("data_mode") == "simulated" and "SIMULATED" in mandi.get("answer", ""))

        weather = query("Will it rain in Nashik today?", "en")
        mode = (weather.get("tool_data") or {}).get("data_mode", "")
        check("weather tool answer", weather.get("decision") == "answer" and weather.get("intent") == "weather")
        check("weather labelled live/simulated", mode in {"live", "simulated"} and f"Data status: {mode.upper()}" in weather.get("answer", ""), mode)

        history = client.get("/api/history", params={"q": "cotton"}).json()
        check("history lists queries", isinstance(history.get("items"), list) and bool(history.get("items")))
        if history.get("items"):
            detail = client.get(f"/api/history/{history['items'][0]['id']}").json()
            check("history detail", bool(detail.get("question") or detail.get("text")))

        feedback = client.post("/api/feedback", json={"query_id": en["query_id"], "rating": "up", "comment": "smoke test"})
        check("feedback accepted", feedback.status_code == 200 and feedback.json().get("rating") == "up")

        documents = client.get("/api/knowledge/documents").json()
        check("knowledge documents listed", documents.get("total", 0) >= 18, f"{documents.get('total')} docs")

        overview = client.get("/api/admin/overview").json()
        check("admin overview", "queries" in overview and "documents" in overview)

        glossary = client.get("/api/admin/glossary").json()
        check("glossary loaded", glossary.get("total", 0) >= 60, f"{glossary.get('total')} entries")

        latest = client.get("/api/evaluation/latest").json()
        check("evaluation run available", bool(latest.get("run")), (latest.get("run") or {}).get("id", ""))

        report = client.get("/api/evaluation/report")
        check("evaluation report served", report.status_code == 200 and "Evaluation Report" in report.text)

        speech = client.get("/api/speech/info").json()
        check("browser ASR is honest", speech.get("asr", {}).get("provider") == "browser" and speech.get("asr", {}).get("server_available") is False)
    except httpx.HTTPError as exc:
        print(f"[FAIL] HTTP error: {exc}")
        failures.append("http")
    finally:
        client.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("All smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
