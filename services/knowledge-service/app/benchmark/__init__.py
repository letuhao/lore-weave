"""K17.9 benchmark harness — runtime + on-demand orchestration.

D-EMB-EVAL-PKG-01: the runtime modules (``core``, ``fixture_loader``,
``mode3_query_runner``, ``persist``, ``metrics``) + ``golden_set.yaml``
live here so the production container doesn't have to ship the
``eval/`` directory. ``eval/run_benchmark.py`` is a thin CLI shell
that imports from this package — ``python -m eval.run_benchmark``
remains the authoritative live-stack driver invocation.

``runner.run_project_benchmark`` wraps the same harness so the FE
can trigger a run via ``POST /v1/knowledge/projects/{id}/benchmark-run``
without shelling out.
"""
