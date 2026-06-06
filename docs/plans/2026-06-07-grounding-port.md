# Plan — Grounding Port (mui #3), phase G3-SDK

- **Date:** 2026-06-07 · **Branch:** `glossary/ai-pipeline-v2` · **Size:** XL (epic); this cycle = phase 1 (G3-SDK).
- **Spec:** `docs/specs/2026-06-07-grounding-port.md`.

## This cycle's scope (G3-SDK only)
Create the shared package; **no service behavior change**. Adoption phases (LE-migrate, K-adopt, C-adopt) are subsequent `/loom` cycles.

## Build order (TDD; parity-driven)
1. **Read** lore-enrichment `app/retrieval/grounding.py` + `app/verify/canon_verify.py` (full signatures + dataclasses) and their existing tests — the parity baseline.
2. `sdks/python/loreweave_grounding/__init__.py` — exports.
3. `cites.py` — `GroundingCite` model + `compose_cites` (lift `compose_grounding` algorithm, generalized) + adapters (`from_glossary_evidence`/`from_l3_passage`/`from_grounding_ref`).
4. `verify.py` — `CanonVerifier` + `VerifyFlag`/`VerifyResult`/`FlagKind`/`Severity`, with `anachronism_markers` + `canon_lookup` injected (no hardcoded 封神).
5. `ports.py` — `GroundingReadPort` Protocol.
6. Register `loreweave_grounding*` in `sdks/python/pyproject.toml` `[tool.setuptools.packages.find].include`.
7. `sdks/python/tests/test_grounding_*.py` — lift lore-enrichment's grounding + canon-verify tests as parity tests (AC3/AC4).

## VERIFY
- `pip install -e sdks/python` (or the repo's install step) succeeds with the new package (AC1).
- `pytest sdks/python/tests/test_grounding_*.py` green.
- Parity: `compose_cites` + `CanonVerifier` reproduce lore-enrichment's outputs on the lifted fixtures.
- **Single-service (SDK only) this cycle** — no cross-service live-smoke needed until adoption phases; note it.

## Risks (this cycle)
- Parity drift in the lift — mitigated by lifting the existing tests verbatim as the baseline.
- Over-generalizing the verifier — keep the checks identical; only the markers/canon become injected params.
