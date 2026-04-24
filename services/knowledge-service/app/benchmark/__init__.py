"""On-demand K17.9 benchmark orchestration for the public POST endpoint.

The CLI path (``python -m eval.run_benchmark``) stays the authoritative
live-stack driver. ``runner.run_project_benchmark`` wraps the same
harness so the FE can trigger a run via ``POST /v1/knowledge/projects/
{id}/benchmark-run`` without shelling out.
"""
