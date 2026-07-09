"""Tool Liveness Eval (TLE) harness — Track D · WS-D2 · P0.

Proves every MCP tool is callable, correct, and *effectful* when a real LLM drives
it over natural language: model selects it (G1), args are schema-valid (G2), the
call executes incl. the Tier-W confirm round-trip (G3), and the system actually
changed — verified via an independent DB read-back (G4).
"""
