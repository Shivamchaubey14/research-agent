"""Run the eval suite: agent → judge → aggregate → gate.

For each question the agent produces a report, an independent LLM judge scores
it, and per-case cost/latency are recorded. The suite mean of each metric is
compared against the promotion thresholds (SRS §11.2).
"""
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from worker.agent import ResearchAgent
from worker.agent.llm import LLM
from worker.config import Settings
from worker.evals import dataset, judge
from worker.evals.dataset import MINIMISE, THRESHOLDS

METRICS = ("faithfulness", "citation_validity", "answer_relevance", "hallucination_rate")


@dataclass
class CaseResult:
    id: str
    question: str
    depth: str
    scores: dict = field(default_factory=dict)  # metric -> float in [0, 1]
    tokens: int = 0
    cost_usd: float = 0.0
    latency_seconds: float = 0.0
    error: str = ""


def _clamp(value) -> float:
    return max(0.0, min(1.0, float(value)))


def run_case(settings: Settings, item: dict) -> CaseResult:
    depth = item.get("depth", "standard")
    started = time.monotonic()
    try:
        result = ResearchAgent(settings).run(item["question"], depth=depth)
        # A fresh judge client gives clean per-case judge token/cost accounting.
        judge_llm = LLM(settings.groq_api_key, settings.model)
        scores = judge.judge_report(judge_llm, item["question"], result.report)
        return CaseResult(
            id=item["id"],
            question=item["question"],
            depth=depth,
            scores={m: _clamp(getattr(scores, m)) for m in METRICS},
            tokens=result.usage.total_tokens + judge_llm.usage.total_tokens,
            cost_usd=round(result.cost_usd + judge_llm.usage.cost_usd(settings.model), 6),
            latency_seconds=round(time.monotonic() - started, 2),
        )
    except Exception as exc:  # noqa: BLE001 - record the failure as a case error
        return CaseResult(
            id=item["id"],
            question=item["question"],
            depth=depth,
            latency_seconds=round(time.monotonic() - started, 2),
            error=str(exc),
        )


def run_suite(
    settings: Settings,
    questions: Optional[list] = None,
    on_case: Optional[Callable[[CaseResult], None]] = None,
) -> list:
    questions = questions or dataset.QUESTIONS
    results = []
    for item in questions:
        result = run_case(settings, item)
        if on_case:
            on_case(result)
        results.append(result)
    return results


def _passes(metric: str, mean) -> bool:
    if mean is None:
        return False
    threshold = THRESHOLDS[metric]
    return mean <= threshold if metric in MINIMISE else mean >= threshold


def summarize(results: list) -> dict:
    scored = [r for r in results if not r.error and r.scores]
    means = {}
    for metric in METRICS:
        values = [r.scores[metric] for r in scored if metric in r.scores]
        means[metric] = round(sum(values) / len(values), 4) if values else None

    return {
        "suite_version": dataset.EVAL_SUITE_VERSION,
        "cases": len(results),
        "scored": len(scored),
        "errors": len(results) - len(scored),
        "means": means,
        "thresholds": THRESHOLDS,
        "total_cost_usd": round(sum(r.cost_usd for r in results), 6),
        "avg_latency_seconds": (
            round(sum(r.latency_seconds for r in scored) / len(scored), 2) if scored else None
        ),
        "passed": bool(scored) and all(_passes(m, means[m]) for m in METRICS),
    }
