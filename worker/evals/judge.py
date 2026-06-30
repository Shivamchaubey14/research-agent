"""LLM-as-judge: score a finished report against its own evidence.

The judge is deliberately strict and grounded — it bases every score only on
the report text and the source list it is given, not on outside knowledge, so
it measures whether the agent's claims are actually supported by what it cited.
"""
from worker.agent.llm import LLM
from worker.agent.schema import ReportDraft
from worker.evals.schema import JudgeScores

JUDGE_SYSTEM = """\
You are a strict evaluator of AI-generated research reports. You are given a \
question and a report containing a summary, sections with inline bracketed \
citations ([1], [2], ...), and a numbered source list.

Judge ONLY from the report and its sources — do not use outside knowledge to \
fill gaps. Score each metric from 0.0 to 1.0:
- faithfulness: fraction of the report's material claims that are supported by a \
cited source.
- citation_validity: fraction of citations that plausibly substantiate the \
claim they are attached to (well-formed, on-topic, not contradictory).
- answer_relevance: how directly and completely the report answers the question.
- hallucination_rate: fraction of claims that are unsupported by, or contradict, \
the cited evidence (lower is better).

Be calibrated: a thorough, well-cited report scores high; vague or uncited \
claims lower faithfulness and raise hallucination_rate.\
"""


def judge_report(judge_llm: LLM, question: str, report: ReportDraft) -> JudgeScores:
    return judge_llm.parse(
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": _serialize(question, report)}],
        schema=JudgeScores,
        effort="high",
        max_tokens=4000,
    )


def _serialize(question: str, report: ReportDraft) -> str:
    parts = [f"Question:\n{question}\n", f"Report summary:\n{report.summary}\n", "Sections:"]
    for section in report.sections:
        parts.append(f"## {section.heading}\n{section.content}")
    parts.append("\nSources:")
    if report.citations:
        for c in report.citations:
            ref = c.url or c.doc_ref or "(no reference)"
            parts.append(f"[{c.marker}] {c.kind}: {c.title} — {ref}")
    else:
        parts.append("(none)")
    return "\n".join(parts)
