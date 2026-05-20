"""K17.9 — standalone CLI shell + dev helpers for the golden-set benchmark.

D-EMB-EVAL-PKG-01: the runtime portion of the harness (fixture schema,
metric math, ``QueryRunner`` protocol, fixture loader, Mode-3 query
runner, persist, plus ``golden_set.yaml``) moved to ``app/benchmark/``
so it ships with the service. The production Docker image does NOT
include this directory — anyone running ``docker exec ... python -m
eval.run_benchmark`` inside the prod container will get
``ModuleNotFoundError`` by design. The CLI is intended to run from
the host against the compose stack.

What lives here:
  - ``run_benchmark.py`` — the standalone CLI shell that imports
    runtime symbols from ``app.benchmark.*`` and orchestrates load →
    run → persist against the live compose stack. Invoked as
    ``python -m eval.run_benchmark --project-id=... --embedding-model=...``.
  - ``register_lm_studio_models.sql`` — dev helper for the LM Studio
    BYOK calibration walkthrough.
  - ``QUALITY_EVAL_BASELINES.md`` — pre/post baselines for the
    extraction-quality eval track.

Full spec: ``docs/03_planning/KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md``
lines 2145-2210.
"""
