"""Tests for the agent's structured-output schema (worker/agent/schema.py)."""
import unittest

from pydantic import ValidationError

from worker.agent.schema import Citation, Plan, ReportDraft, Section


class CitationTests(unittest.TestCase):
    def test_defaults_to_a_web_citation(self):
        cite = Citation(marker=1)
        self.assertEqual(cite.kind, "web")
        self.assertEqual(cite.url, "")
        self.assertEqual(cite.doc_ref, "")
        self.assertEqual(cite.snippet, "")

    def test_marker_is_required(self):
        with self.assertRaises(ValidationError):
            Citation()

    def test_marker_is_coerced_to_int(self):
        self.assertEqual(Citation(marker="3").marker, 3)


class PlanTests(unittest.TestCase):
    def test_sub_questions_are_required(self):
        with self.assertRaises(ValidationError):
            Plan()

    def test_holds_ordered_sub_questions(self):
        plan = Plan(sub_questions=["what", "why", "how"])
        self.assertEqual(plan.sub_questions, ["what", "why", "how"])


class ReportDraftTests(unittest.TestCase):
    def test_parses_a_full_report(self):
        draft = ReportDraft.model_validate(
            {
                "summary": "In short, yes.",
                "sections": [{"heading": "Background", "content": "Context [1]."}],
                "citations": [
                    {"marker": 1, "kind": "document", "doc_ref": "1a2b#3", "title": "Notes"}
                ],
            }
        )
        self.assertEqual(draft.summary, "In short, yes.")
        self.assertIsInstance(draft.sections[0], Section)
        self.assertEqual(draft.sections[0].heading, "Background")
        self.assertEqual(draft.citations[0].kind, "document")
        self.assertEqual(draft.citations[0].doc_ref, "1a2b#3")

    def test_summary_and_sections_are_required(self):
        with self.assertRaises(ValidationError):
            ReportDraft.model_validate({"summary": "only summary"})

    def test_roundtrips_through_json(self):
        draft = ReportDraft(
            summary="s",
            sections=[Section(heading="h", content="c")],
            citations=[Citation(marker=1, url="https://example.com")],
        )
        restored = ReportDraft.model_validate_json(draft.model_dump_json())
        self.assertEqual(restored.citations[0].url, "https://example.com")


if __name__ == "__main__":
    unittest.main()
