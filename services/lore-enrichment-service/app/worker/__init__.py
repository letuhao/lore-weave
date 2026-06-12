"""Background workers for lore-enrichment-service (run as `python -m app.worker`).

Currently: the resume worker (F-C14-1/051) — a Redis Streams consumer that
re-drives cost-cap-paused jobs, skipping already-done gaps (token-safe).
"""
