"""Curated evaluation set and promotion thresholds (SRS §11.2).

Versioned so a score is always tied to the exact question set that produced it.
Kept small and factual so the suite is cheap to run in CI; expand over time.
"""

EVAL_SUITE_VERSION = "2026.06.1"

# Curated questions. Each is general-knowledge and web-answerable so the run is
# deterministic enough to judge and doesn't depend on a particular user's docs.
QUESTIONS = [
    {
        "id": "kafka-basics",
        "question": "What is Apache Kafka and what are its primary use cases?",
        "depth": "quick",
    },
    {
        "id": "rag-definition",
        "question": "What is retrieval-augmented generation (RAG) and why is it "
        "used with large language models?",
        "depth": "quick",
    },
    {
        "id": "http2-vs-http3",
        "question": "What are the key differences between HTTP/2 and HTTP/3?",
        "depth": "standard",
    },
]

# Promotion gate: the suite fails if the mean of any metric crosses these
# (>= for the maximise metrics, <= for hallucination). Tunable as the bar rises.
THRESHOLDS = {
    "faithfulness": 0.80,        # mean >=
    "citation_validity": 0.80,   # mean >=
    "answer_relevance": 0.80,    # mean >=
    "hallucination_rate": 0.20,  # mean <=
}

# Metrics where lower is better (compared with <= instead of >=).
MINIMISE = frozenset({"hallucination_rate"})
