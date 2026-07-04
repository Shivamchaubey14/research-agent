"""Unit tests for the agent worker.

These cover the worker's pure-logic modules — text chunking, depth/config
profiles and the agent's structured-output schema — so they run with no Kafka,
Redis, Qdrant or Groq access. Run them from the repo root with

    python -m unittest discover -s worker -p "test_*.py"
"""
