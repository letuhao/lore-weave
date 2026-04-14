"""K17.9 — golden-set benchmark harness (laptop-friendly scaffold).

Full spec: `docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md`
lines 2145-2210. Real end-to-end wiring depends on K17.2 (LLM extractor)
and K18.3 (Mode 3 selector); this scaffold ships the pure pieces —
fixture schema, metric math, and a `QueryRunner` Protocol so the harness
can be unit-tested with a mock today.
"""
