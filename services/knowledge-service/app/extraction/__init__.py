"""K15 — pattern-based extraction (Pass 1, quarantine).

Pure-function extractors that run synchronously in the knowledge-
service event consumer. Zero LLM cost; output is intentionally
low-confidence (`pending_validation=true`) and gets promoted or
contradicted by the K17 LLM extractor (Pass 2).

Per KSA §5.1: pattern extraction is dumb — regex cannot distinguish
intent from fact, hypothetical from reality, reported speech from
direct observation. The quarantine mechanism is the safety net, not
pattern precision. Do not over-tune these modules.
"""
