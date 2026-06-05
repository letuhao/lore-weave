# Plan — Enrichment Production Hardening (epic LE-PROD-2)

**Date:** 2026-06-05 · **Branch:** lore-enrichment/foundation · **Size:** XL (sliced)
**Origin:** LE-PROD epic shipped the observed fixes; this closes the remaining
production-readiness gaps IN-BRANCH. **Deployment (AWS / load-test / monitoring) is
explicitly OUT — a separate go-live task.**

## Gaps → slices (PO-approved scope)

### P3 — Eval run + gate wiring  `[BE, M-L]`
The eval suite is de-biased (slice D) but never RUN + has no in-container consumer
(`_ensemble_shim` resolves the κ math by path → ImportError inside the isolated
service image; eval only runs in the repo/CI).
- **P3a — vendor Fleiss-κ fallback** in `_ensemble_shim`: keep import-by-path PRIMARY
  (repo/CI, canonical), add a vendored standard-formula fallback so the judge works
  in-container (Fleiss κ is a fixed formula — no drift risk; clearly attributed).
- **P3b — eval-run route**: `POST /internal/eval/{project}/run` (internal-token) →
  load the project's persisted proposals → build `ScorableProposal`s → resolve the
  book profile → `run_eval(profile=…, judges=…)` → persist the scorecard via
  `EvalRunsRepo` → the gate (`/gate-status`) now reflects a real run.
- **P3c — run it** live on the demo → produce a baseline scorecard; if it passes,
  P2/P3 (fabrication/recook) unlock legitimately.

### P2 — Multi-book de-bias proof (live)  `[BE+data, M]`
Multi-book correctness is coded (profiles) but only unit-proven. Prove it live on a
NON-Fengshen book.
- Create a 2nd demo book (English — Arthurian/Camelot) owned by the test user +
  seed its `enrichment_book_profile` (language=en, worldview, markers).
- Ingest a public-domain English chapter (Le Morte d'Arthur, PD) as a curated corpus.
- Run a compose retrieval job on an English NEW target (e.g. Merlin) → PROVE: English
  prompt, English content, grounded on the English corpus, anachronism-off, (eval)
  English judge rubric. Clean up after.

### P1 — Corpus coverage  `[data, L, resumable]`
Retrieval is only rich for the 1 committed chapter (卷012). Ingest ~15–20 key
chapters covering the demo's main entities (姜子牙/哪吒/元始天尊/纣王/妲己/玉虛宮/
碧遊宮…). Fetch verbatim from zh.wikisource (verify each is verbatim, not a summary —
WebFetch is unreliable past ch.12), commit as fixtures, re-seed. Incremental +
committable per batch (resumable).

### P4 — Hardening + QA sweep  `[BE+FE, M]`
- **P4a — grounded-flag safety net**: a small refusal-marker fallback so a
  NON-compliant model (one that ignores the flag + writes "未提及" prose) is still
  treated as ungrounded (defense-in-depth on top of the flag).
- **P4b — QA sweep**: a comprehensive integration/e2e pass over all 5 compose modes +
  edge cases (cap/empty/license-deny/thin-grounding) so coverage isn't one-journey.

## Order (token-aware: bank bounded code slices first; corpus last/resumable)
P3 → P2 → P4 → P1. Each slice: full workflow + `/review-impl` + own commit.

## Invariants held
H0 · no hardcoded secrets/model-names · glossary SSOT · stage only changed files ·
faithful VERIFY (cross-service live-smoke) · NEUTRAL-default de-bias (no Fengshen regression).
