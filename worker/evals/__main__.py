"""Eval suite entry point.

    python -m worker.evals [results.json]

Runs the agent over the curated question set, scores each report with the LLM
judge, prints a scorecard, optionally writes the full results as JSON, and exits
non-zero if the suite is below the promotion thresholds (so CI can gate on it).
Needs ANTHROPIC_API_KEY (read from the environment or .env).
"""
import json
import sys

from dotenv import load_dotenv

from worker.config import Settings
from worker.evals import dataset, runner
from worker.evals.dataset import MINIMISE, THRESHOLDS
from worker.evals.runner import METRICS


def _case_line(r) -> str:
    if r.error:
        return f"  [{r.id}] ERROR: {r.error[:80]}"
    body = "  ".join(f"{m}={r.scores[m]:.2f}" for m in METRICS)
    return f"  [{r.id}] {body}  (${r.cost_usd:.4f}, {r.latency_seconds}s)"


def _render(results, summary) -> str:
    out = ["", "=" * 72, f"EVAL SCORECARD — suite {summary['suite_version']}", "=" * 72]
    for r in results:
        out.append(_case_line(r))
    out.append("-" * 72)
    out.append("Means vs thresholds:")
    for m in METRICS:
        mean = summary["means"][m]
        op = "<=" if m in MINIMISE else ">="
        mean_s = "n/a" if mean is None else f"{mean:.3f}"
        mark = "PASS" if runner._passes(m, mean) else "FAIL"
        out.append(f"  {m:<20} {mean_s:>6}  ({op} {THRESHOLDS[m]})  {mark}")
    out.append("-" * 72)
    out.append(
        f"scored {summary['scored']}/{summary['cases']}  "
        f"cost ${summary['total_cost_usd']:.4f}  "
        f"avg latency {summary['avg_latency_seconds']}s"
    )
    out.append(f"RESULT: {'PASS' if summary['passed'] else 'FAIL'}")
    return "\n".join(out)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    load_dotenv()
    try:
        settings = Settings.from_env()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Running eval suite {dataset.EVAL_SUITE_VERSION} "
        f"over {len(dataset.QUESTIONS)} questions…",
        file=sys.stderr,
    )
    results = runner.run_suite(settings, on_case=lambda r: print(_case_line(r), file=sys.stderr))
    summary = runner.summarize(results)
    print(_render(results, summary))

    if argv:
        with open(argv[0], "w", encoding="utf-8") as fh:
            json.dump(
                {"summary": summary, "cases": [vars(r) for r in results]}, fh, indent=2
            )
        print(f"\nWrote {argv[0]}", file=sys.stderr)

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
