# Cycle 12: Canon-verify

> RAID cycle brief per RAID_WORKFLOW.md §12.6. Structure asserted by
> `scripts/raid/brief-structure-validator.sh` (10 sections, ≤4000 tokens, ≥3 🔴).

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Add a **consistency verifier** that runs at proposal creation in `lore-enrichment-service`. For each enriched fact produced by C11 it (1) checks for **contradiction** against KG/glossary canon (via the C1 read port), (2) checks for **anachronism** against the work's era/cosmology, and (3) **neutralizes prompt-injection** in any LLM-facing text before/while generating. Flagged proposals are marked, not silently dropped. **M2 verifies CONSISTENCY only — NOT correctness; correctness rests on the human PROMOTE gate (H0).**
- **Acceptance gate:** `scripts/raid/verify-cycle-12.sh` exits 0 (created by this cycle's runner).
- **Top 3 LOCKED decisions consumed:** H0 (enriched≠canon, quarantine never bypassed by a "passing" verify), Q1 (mirror pending_facts injection-defense), Execution-LLM (Qwen 3.6 via provider-registry, never hardcoded).
- **DPS count:** 2
- **Estimated wall time:** 3–4 h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C11
- Files expected to exist (grep-able paths):
  - `services/lore-enrichment-service/app/clients/` (KG/glossary read port, C1)
  - `services/lore-enrichment-service/app/generation/` (schema-gov gen + origin/provenance tagging, C11)
  - `enrichment_proposal` model with `origin`, `provenance_json`, `confidence`, `review_status` columns (C2)

## Scope (IN)
- `app/verify/canon_verify.py` — `CanonVerifier` orchestrating three checks over a generated proposal's facts; returns typed `VerifyResult { passed, flags[] }` where each flag = `{kind: contradiction|anachronism|injection, dimension, evidence, severity}`.
- **Contradiction check** — query KG/glossary canon for the entity + dimension via the C1 read port; detect a generated fact that asserts something incompatible with an existing `source_type='glossary'` (canon) fact. Graceful degradation when the KG-read port is Null/unavailable (C1/Q6): record `verify_degraded=true`, do NOT auto-pass as if verified.
- **Anachronism check** — flag generated content referencing entities/concepts/eras outside the work's locked cosmology/period (商周 / 封神演义 frame). Operates on **Chinese** text (locked: eval/anachronism on Chinese).
- **Injection-defense** — neutralize prompt-injection in corpus/retrieval text and in the entity name/dimension fields before they reach the LLM and in returned proposal text (mirror knowledge-service `pending_facts` defense, Q1): strip/escape instruction-like spans, fence untrusted input, reject control directives. CJK-safe.
- Wire verifier into the proposal-creation path so every new `enrichment_proposal` records its `VerifyResult` (e.g. into `provenance_json` / a `verify_flags_json` field) and sets `review_status` appropriately for downstream C13 review.
- Unit tests: `tests/test_canon_verify.py` — contradictory proposal flagged; anachronistic proposal flagged; injection payload neutralized; KG-unavailable path records `verify_degraded` (no false-green).
- `scripts/raid/verify-cycle-12.sh` — runs the unit suite + asserts the three flag kinds fire.

## Scope (OUT — explicitly)
- NO review/approve/reject/**promote** endpoints or write-back — that is **C13**. Do not canonize, do not write the KG/glossary here.
- NO new DB migration if C2 columns suffice; if a `verify_flags_json` column is genuinely needed, it MUST ship with a clean up/down + idempotency (but prefer reusing `provenance_json`).
- NO new RAG framework, no langchain/llamaindex, no web search — retrieval/embedding reuses knowledge-service `/internal/embed` via the C1 port only.
- NO hardcoded model names — resolve gen/verify model via provider-registry.
- NO edits to `world-service`/`game-server`/`tilemap`, `infra/existing-prod/`, glossary/knowledge-service source, or `tests/quality/` climate/geo eval files.
- NO auto-admission: a "passed" verify NEVER bypasses quarantine or the human promote gate.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `pytest services/lore-enrichment-service/tests/test_canon_verify.py` — all green; covers contradiction-flagged, anachronism-flagged, injection-neutralized, KG-unavailable-no-false-green.
- Lints pass: ruff/mypy on `app/verify/`; `scripts/raid/secret-scan-cycle.sh`; `scripts/raid/prod-isolation-lint.sh` clean.
- Integration smoke: `scripts/raid/verify-cycle-12.sh` exits 0 — feeds a known contradictory + anachronistic + injection-laden proposal through `CanonVerifier`, asserts each flag kind fires and injection text is neutralized.
- **No live-smoke token required** — this cycle is in-service only (verifier + unit tests). Cross-service KG reads are mocked at the C1 port boundary; live KG verification is exercised in C13/C14.

## DPS parallelism plan
- **DPS 1 — verifier core** (return budget 1500 tokens): `app/verify/canon_verify.py` (contradiction + anachronism checks, `VerifyResult` types, graceful-degradation path) + their unit tests. Worktree files: `app/verify/canon_verify.py`, `tests/test_canon_verify.py` (contradiction/anachronism cases).
- **DPS 2 — injection-defense + wiring** (return budget 1500 tokens): injection sanitizer (mirror pending_facts), wire verifier into proposal-creation, `verify-cycle-12.sh`. Worktree files: `app/verify/sanitize.py`, proposal-creation call-site, `scripts/raid/verify-cycle-12.sh`, injection test cases.
- Merge order: DPS 1 then DPS 2 (DPS 2 imports `VerifyResult`).

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **H0 leak:** does a "passed" verify anywhere set `pending_validation=false`, raise `confidence` to 1.0, or change `source_type` toward `glossary`? It MUST NOT — verify only annotates; quarantine + promote gate stay intact.
- **False-green when KG unavailable:** confirm the Null/cached read port (Q6) makes the contradiction check record `verify_degraded`, NOT silently `passed`. Mock-only tests can hide this — check the degradation branch is asserted.
- **Injection bypass:** try payloads in entity name, dimension label, AND retrieved corpus chunk (multi-field). Confirm CJK/全角 control sequences and nested/encoded directives are neutralized, not just ASCII "ignore previous".
- **Anachronism over/under-reach:** confirm it operates on Chinese text and uses the locked 商周/封神 frame, not a hardcoded English wordlist; flags must carry evidence, not be opaque booleans.
- **Hardcoded model names:** grep `app/verify/` for any literal model id — must be registry-resolved.
- **Scope creep:** any approve/promote/write-back logic = C13 leak; flag it.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present: contradiction + anachronism + injection-defense checks; wired into proposal creation; unit tests for all three + degradation; `verify-cycle-12.sh`.
- No OUT items touched: no promote/write-back, no KG/glossary/world-service edits, no climate/geo eval edits, no new RAG dep, no hardcoded model.
- All acceptance criteria met: pytest green, lints + secret-scan + prod-isolation clean, verify-cycle-12.sh exits 0.
- Cross-cycle invariants intact: H0 quarantine never bypassed by a passing verify; depends only on C11 (DONE).

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle map (find C12 row): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- LOCKED decisions (full): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) — H0, Q1, Q2, Q6, Execution (Chinese output, Qwen via registry).
- Plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md) · [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): H0, Q1, Q6, Execution-LLM-via-registry, Output-language-Chinese.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **H0 (CORE):** verify is a CONSISTENCY annotator only — a "passed" verify NEVER lifts quarantine, raises confidence to 1.0, or moves `source_type` to `glossary`. Correctness rests on the human PROMOTE gate (C13), not on this check.
- 🔴 **Q1:** injection-defense MUST mirror knowledge-service `pending_facts` — neutralize injection across entity name + dimension + retrieved corpus text; CJK-safe.
- 🔴 **Execution-LLM:** Qwen 3.6 / verify model resolved via PROVIDER-REGISTRY — zero hardcoded model names; checks operate on Chinese text (商周/封神 frame).
- 🔴 **Acceptance MUST include:** `verify-cycle-12.sh` exits 0 AND the KG-unavailable path asserts `verify_degraded` (no false-green) — easiest to forget.
- 🔴 **Do NOT touch:** no promote/write-back (C13), no KG/glossary/world-service/game-server source, no `tests/quality/` climate/geo eval files, no new RAG dependency.
- 🔴 **Fresh session reminder:** this is a new `/raid 12` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
