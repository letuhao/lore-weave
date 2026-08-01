"""Glossary-build pipeline — deterministic planner/executor world building.

Spec: docs/specs/2026-07-27-glossary-kg-build-workflows.md (POC E1-E4).
Plan: docs/plans/2026-07-27-glossary-build-pipeline.md (RUN-STATE).

The state machine lives HERE, not in the chat agent: the LLM only fills content
inside a bounded step (planner enumerates; executor builds ONE item; the deep
loop steers ONE section per call). Every tool/DB write is made by the platform.
"""
