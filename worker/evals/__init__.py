"""Agent evaluation harness (SRS §11.2).

Because the agent is probabilistic, correctness can't be asserted with fixed
equality. This suite runs the agent over a curated question set and scores each
report with an LLM-as-judge on faithfulness, citation validity, answer relevance
and hallucination rate, alongside cost/latency. It gates promotion in CI.

Run with: ``python -m worker.evals``
"""
