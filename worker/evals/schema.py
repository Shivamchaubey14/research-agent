"""Structured score the LLM judge returns for one report (SRS §11.2).

Each metric is a 0.0-1.0 fraction. No numeric range constraints are declared on
the schema (structured outputs don't support them); the runner clamps to
[0, 1] defensively.
"""
from pydantic import BaseModel, Field


class JudgeScores(BaseModel):
    faithfulness: float = Field(
        description="Fraction (0-1) of the report's claims supported by a cited source."
    )
    citation_validity: float = Field(
        description="Fraction (0-1) of citations that plausibly substantiate their claim."
    )
    answer_relevance: float = Field(
        description="Degree (0-1) to which the report addresses the question."
    )
    hallucination_rate: float = Field(
        description="Fraction (0-1) of claims unsupported by or contradicted by the evidence."
    )
    reasoning: str = Field(description="Brief justification for the scores.")
