"""Enrichment quality eval (RAID C15).

EXTENDS the platform eval pattern ADDITIVELY (separate files; NEVER edits
climate/geo eval): weighted sub-scores (schema/canon/anachronism/provenance/
usefulness) over enriched proposals, scored by deterministic rule scorers +
a judge-ENSEMBLE (Fleiss κ + majority + partial-credit, reusing the
knowledge-service tests/quality methodology) for the subjective
cultural-fidelity ``usefulness`` sub-score; versioned baseline + regression
thresholds + baseline-diff; in-service persistence to ``enrichment_eval_runs``;
and a GATE that blocks the higher-cost P2/P3 techniques (C16 fabrication /
C17 re-cook) unless the latest eval clears threshold.

H0: enriched proposals are scored as ``enriched`` data — NEVER as authored
canon (confidence < 1.0 expected; a proposal looking like canon is an H0 leak,
not a high score).
"""
