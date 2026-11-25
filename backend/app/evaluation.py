"""CLI evaluation runner.

Usage:
    cd backend
    python -m app.evaluation

This writes docs/EVALUATION_REPORT.md and docs/evaluation_latest.json with
actual measured results from this machine.
"""
from __future__ import annotations

import json

from .services.container import create_container
from .services.evaluation import run_evaluation


def main() -> None:
    container = create_container()
    run = run_evaluation(container.pipeline, save=True, write_report=True)
    metrics = run["metrics"]
    print(json.dumps(
        {
            "run_id": run["id"],
            "cases": metrics["cases"],
            "recall_at_5": metrics["recall_at_5"],
            "precision_at_5": metrics["precision_at_5"],
            "faithfulness": metrics["faithfulness"],
            "correct_refusal_rate": metrics["correct_refusal_rate"],
            "decision_accuracy": metrics["decision_accuracy"],
            "intent_accuracy": metrics["intent_accuracy"],
            "latency_ms_mean": metrics["latency_ms_mean"],
            "latency_ms_p95": metrics["latency_ms_p95"],
            "target_status": metrics["target_status"],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
