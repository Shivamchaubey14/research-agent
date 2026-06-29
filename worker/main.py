"""Worker entrypoint.

In Phase 3 this becomes a Kafka consumer of ``research.jobs`` that updates the
``ResearchRun`` lifecycle (FR-RUN-4) and fans out progress over Redis. For now
it drives one research run from the command line so the agent can be exercised
end to end:

    python -m worker.main "What are the tradeoffs of Kafka vs RabbitMQ?" --depth deep
"""
import argparse
import json
import logging
import sys

from dotenv import load_dotenv

from worker.agent import ResearchAgent
from worker.agent.events import CallbackEmitter, ProgressEvent
from worker.config import DEFAULT_DEPTH, DEPTH_PROFILES, Settings


def _print_event(event: ProgressEvent) -> None:
    extra = ""
    if event.data:
        extra = " " + json.dumps(event.data, default=str)
    print(f"  [{event.kind:<12}] {event.message}{extra}", file=sys.stderr)


def _render_report(result) -> str:
    out = ["", "=" * 72, "SUMMARY", "-" * 72, result.report.summary, ""]
    for section in result.report.sections:
        out += [section.heading, "-" * len(section.heading), section.content, ""]
    out.append("SOURCES")
    out.append("-" * 72)
    for c in result.report.citations:
        out.append(f"[{c.marker}] {c.title} {c.url}".rstrip())
    out += [
        "",
        f"tokens={result.usage.total_tokens}  cost=${result.cost_usd:.4f}  "
        f"policy={result.policy_version}",
    ]
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the DeepResearch agent on a question.")
    parser.add_argument("question", help="The research question.")
    parser.add_argument(
        "--depth",
        choices=sorted(DEPTH_PROFILES),
        default=DEFAULT_DEPTH,
        help="Research depth (FR-RUN-2).",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    try:
        settings = Settings.from_env()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    agent = ResearchAgent(settings, emitter=CallbackEmitter(_print_event))
    result = agent.run(args.question, depth=args.depth)
    print(_render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
