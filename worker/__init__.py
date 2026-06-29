"""DeepResearch agent worker.

Runs the autonomous research agent: plan -> search -> verify -> cite
(SRS §5.3, FR-AGT-1..9). The Kafka consumer that feeds it jobs and the Redis
progress fan-out are wired in Phase 3; for now the loop is driven directly via
``python -m worker.main``.
"""
