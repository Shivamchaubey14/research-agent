"""Structured outputs the agent is constrained to produce.

These Pydantic models map directly onto the persisted data model: ``ReportDraft``
becomes a :class:`research.models.Report` (summary + ordered sections) plus its
:class:`research.models.Citation` rows (FR-RPT-1, FR-RPT-2). Only JSON-schema
features supported by structured outputs are used (no length/range constraints).
"""
from pydantic import BaseModel, Field


class Plan(BaseModel):
    """An explicit, ordered decomposition of the question (FR-AGT-1)."""

    sub_questions: list[str] = Field(
        description="Ordered sub-questions to investigate, most foundational first.",
    )


class Section(BaseModel):
    """One ``{heading, content}`` block of the report body."""

    heading: str
    content: str = Field(
        description=(
            "Prose grounded in retrieved sources. Cite sources inline with "
            "bracketed markers like [1], [2] that refer to the citation list."
        ),
    )


class Citation(BaseModel):
    """A resolvable source backing claims in the report (FR-RPT-2)."""

    marker: int = Field(description="Inline citation number, e.g. 1 for [1].")
    kind: str = Field(default="web", description='Either "web" or "document".')
    title: str = ""
    url: str = Field(default="", description="The source URL for a web citation.")
    doc_ref: str = Field(
        default="",
        description='For a document citation, its reference, e.g. "1a2b#3".',
    )
    snippet: str = Field(
        default="", description="Short quote/excerpt that supports the claim."
    )


class ReportDraft(BaseModel):
    """The final structured report (FR-RPT-1)."""

    summary: str = Field(description="A concise executive summary answering the question.")
    sections: list[Section]
    citations: list[Citation]
