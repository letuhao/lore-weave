"""composition batch-job worker (LLM re-arch Phase 3 M4).

The batch generation operations (decompose / generate / selection-edit /
chapter-gen / stitch) used to run their LLM compute INLINE in the request handler.
M4 moves that off the request path: the endpoint resolves all bearer-authenticated
context, persists it in `generation_job.input`, enqueues a trigger on the
composition_jobs Redis stream, and returns 202 + job_id; this worker (a separate
`python -m app.worker` process) runs the pure LLM compute under internal auth and
writes `generation_job.result`; the existing GET /jobs/{id} polls.

Flag-gated by COMPOSITION_WORKER_ENABLED (default off → inline behavior unchanged).
"""
