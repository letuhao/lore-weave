# SPEC — C3 hybrid defense: auto-reject the egregious (DESIGN PASS)

> Branch: `lore-enrichment/foundation` · Size: **XL** (≈9 files; bundles F-C12-1) · Mode: default v2.2
> Origin: QC ruling C3 — *"hybrid: flag-for-human by default, but AUTO-REJECT the egregiously-unreasonable; define the thresholds per defense; touches F-C12-1 + 050 + 058."*
> **This is the design-pass deliverable — present for PO sign-off before BUILD.**

## CLARIFY (PO-signed-off 2026-06-01)

1. **Auto-reject scope** → injection **+** egregious anachronism (**≥2 distinct markers**) **+** high-severity contradiction. The rest stay advisory (flag-for-human).
2. **F-C12-1 BUNDLED** → wire the real contradiction canon-lookup so contradiction goes live end-to-end (currently `_canon_lookup` returns `[]` → inert).
3. **Persist** auto-rejected proposals as `review_status='rejected'` + `rejected_reason` (auditable; never surfaced to the review queue/wiki).

**H0 framing (locked):** auto-reject is the *conservative* direction — `rejected` is a terminal lifecycle state that never admits canon, only suppresses surfacing. The sole cost is a **false-positive** (rejecting legitimate generated lore → wasted generation, recoverable). Therefore the egregiousness bar is set HIGH (false-positive-averse).

## DESIGN

### A. Egregiousness policy (the auto-reject decision)

A new pure function classifies a `VerifyResult` into an action. Lives in `app/verify/wiring.py` (alongside `_derive_status`), so the verifier (`canon_verify.py`) stays annotation-only and unaware of the action.

```
decide_auto_reject(result) -> RejectDecision | None
  egregious iff ANY of:
    - any INJECTION flag                              (a payload is never legit lore)
    - any CONTRADICTION flag with Severity.HIGH       (direct canon negation)
    - >= 2 DISTINCT anachronism markers               (count distinct evidence terms)
  -> RejectDecision(reason=<concise evidence string>, flags=[...])
  else None  (advisory path unchanged: quarantined / needs_review / degraded / clean)
```

- "≥2 distinct anachronism markers" = ≥2 unique `evidence` strings of `kind==ANACHRONISM` across the result's flags (one fact with both 飞机 and 互联网, or two facts each anachronistic). A single marker stays `needs_review` (058: the marker list is conservative, but one hit is not "egregious").
- A new `VerifyStatus.AUTO_REJECTED` is added; `_derive_status` returns it when `decide_auto_reject` is non-None (highest priority, above `quarantined`). `AnnotatedVerify.is_quarantined` stays True (auto-rejected is *harder* than quarantined — still never canon).

### B. Persistence (runner → store)

The runner already calls `verify_and_annotate` → `stage.verify`. New branch in `runner.run_gap`'s caller (the runner persist block):

- When `stage.verify.status is AUTO_REJECTED`: build the proposal fields as today BUT with `review_status='rejected'` + `rejected_reason=<decision.reason>` (capped length), and emit a new `PROPOSAL_AUTO_REJECTED` event (audit) instead of `PROPOSAL_CREATED`. The proposal is still PERSISTED (full audit of what was rejected + why), `pending_validation=True`, origin enrichment, confidence<1.0 — H0 intact.
- **Insert-as-rejected**: `build_proposal_fields` gains an optional `review_status`/`rejected_reason` override (default 'proposed'). The DB transition trigger fires only on UPDATE (`OLD.review_status IS DISTINCT FROM`), so a direct INSERT at 'rejected' is legal (verified against `migrate.py` trigger — it guards transitions, not the initial insert; the CHECK vocabulary includes 'rejected'). → one write, no proposed→rejected update dance.
- The auto-rejected row is excluded from the review queue + wiki by the EXISTING `review_status='proposed'`/`'promoted'` filters (wiki already filters promoted-only per MED-1; the proposals list filters by status).

### C. F-C12-1 — wire the real contradiction canon-lookup

**The fork (the real "needs design"):** the authored-canon SSOT is the glossary, which is **book-scoped**, but the job path carries only `project_id` (`CreateJobBody` has no `book_id`; `AutoEnrichBody` DOES).

**Chosen approach (recommend): glossary `description` + thread `book_id`.**
- Add optional `book_id: UUID | None` to `CreateJobBody` (+ OpenAPI) and thread `book_id` → `build_live_runner(book_id=)` → the `_canon_lookup` closure. `AutoEnrichBody` already has `book_id`; the auto-enrich create path passes it through.
- `_canon_lookup(entity_name, dimension)` (built in `assembly`): resolve the entity by `canonical_name` within `book_id` via `GlossaryClient.list_entities` (cached once per run), and return `[CanonFact(entity_name, dimension, assertion=description, terms=(canonical_name, *coarse_tokens))]` when the entity has a **non-empty authored `description`**; else `[]`.
- **Honest degrade:** when `book_id` is absent (a manual job that didn't supply it) OR no glossary client OR the entity has empty authored canon → `_canon_lookup` returns `[]`. The existing `_check_contradiction` already records `verify_degraded=True` when canon is unreachable/empty (no false-green). So a job without `book_id` simply can't auto-reject on contradiction — it degrades, exactly as today, but is no longer *hardcoded* inert.
- **Precision limit (documented, extends F-C12-3):** CJK prose canon has no clean token boundaries; `terms` from a prose `description` are coarse, so contradiction detection on prose canon is weak — but this makes auto-reject on contradiction CONSERVATIVE (fewer false-positives), which is the safe direction. The win is the check is LIVE + degrades honestly, not inert.

**Rejected alternative:** read canon from the KG (project-scoped, no book_id needed) — but the KG exposes no structured per-entity-per-dimension canon read (only graph-stats + context-build), and the KG layer is *derived*, not the authored SSOT. Contradiction should compare against authored glossary canon.

### D. 050 / 058 disposition
- **058 (anachronism marker breadth)** — orthogonal to the auto-reject decision; the list is data. **Defer** (stays DEFERRED-058) — auto-reject on ≥2 markers works with whatever the list contains.
- **050 (injection denylist coverage: 文言文 / base64 / encoded)** — defense-in-depth on the *detector*, not the *action*. **Defer** (stays DEFERRED-050, C13/C15 consumer-side). C3 acts on whatever injection the existing scanner catches; widening the scanner is separable. **Add one negative-corpus test** noting known-uncovered shapes (cheap, documents the gap).

## Files (XL ≈ 9 + tests)
1. `app/verify/wiring.py` — `VerifyStatus.AUTO_REJECTED`, `RejectDecision`, `decide_auto_reject`, `_derive_status` update.
2. `app/jobs/proposal_store.py` — `build_proposal_fields(review_status=, rejected_reason=)` override; PersistedProposal carries them.
3. `app/jobs/runner.py` — auto-reject branch: persist rejected + reason, emit `PROPOSAL_AUTO_REJECTED`.
4. `app/jobs/events.py` — new `PROPOSAL_AUTO_REJECTED` event type + metric.
5. `app/jobs/assembly.py` — build the REAL `_canon_lookup` (glossary description, cached); thread `book_id`.
6. `app/clients/glossary.py` — (reuse `list_entities`; add a tiny `resolve_entity_canon(book_id, name)` helper if cleaner).
7. `app/api/jobs.py` + `AutoEnrichBody`/`gaps.py` — thread `book_id` into `build_live_runner`.
8. `contracts/api/lore-enrichment/v1/openapi.yaml` — `book_id` on the job create body.
9. `app/db/migrate.py` — (verify only) confirm insert-as-rejected is trigger-legal; no schema change expected.

## BUILD — TDD task outline (RED→GREEN)
- T1 `decide_auto_reject` + `AUTO_REJECTED` status — unit: injection→reject; contradiction HIGH→reject; 1 anachronism→needs_review; 2 distinct→reject; clean→clean.
- T2 `build_proposal_fields` override + insert-as-rejected — unit + DB: row lands `rejected` with reason, trigger doesn't block the insert.
- T3 runner auto-reject branch — unit: an injected/anachronistic stage persists rejected (not proposed), emits auto-reject event, still H0 (conf<1.0, origin enrichment).
- T4 real `_canon_lookup` (assembly) — unit: resolves description→CanonFact; empty desc→[]; no book_id→[] (degrade).
- T5 `book_id` threading (jobs.py/gaps.py/openapi) — contract + api tests.
- T6 negative-corpus injection test (050 doc) + 058 note.
- T7 VERIFY: full suite + live-smoke (auto-reject an injected gap end-to-end; contradiction degrade when no canon).

## Acceptance
- An injection / ≥2-anachronism / HIGH-contradiction proposal lands `review_status='rejected'` + `rejected_reason`, NOT in the review queue/wiki; H0 markers intact; auditable event emitted.
- A single-flag / low-severity proposal still flags for human (advisory unchanged).
- Contradiction check is LIVE (reads glossary canon) and degrades honestly (no false-green) when canon is absent — no longer hardcoded `[]`.
- Suite green; live-smoke proves one auto-reject end-to-end.

## Progress tracker (single source of truth)
- ✅ T1 `decide_auto_reject` + `VerifyStatus.AUTO_REJECTED` (wiring.py) — 12 tests (`test_auto_reject.py`)
- ✅ T2 `build_proposal_fields(review_status=, rejected_reason=)` + `PersistedProposal.rejected_reason` + Pg INSERT col; insert-as-`rejected` legal (trigger is BEFORE-UPDATE, verified)
- ✅ T3 runner auto-reject branch (`decide_auto_reject` → rejected + reason, success+skip) + `PROPOSAL_AUTO_REJECTED` event + `proposals_auto_rejected_total` metric + `outcome.auto_rejected_gaps`; 2 runner tests
- ✅ T4 real `_canon_lookup` — **new** `app/verify/canon_lookup.py` (`extract_canon_terms` CJK+Latin, `make_glossary_canon_lookup` cached + honest-degrade); 9 tests; wired in assembly (replaces hardcoded `[]`)
- ✅ T5 `book_id` threading — `CreateJobBody.book_id` + jobs.py create + gaps.py auto-enrich request + resume_consumer + `build_live_runner(book_id=)` + openapi
- ✅ T6 negative-corpus injection test (`test_injection_negative_corpus.py`: 3 covered pass, 2 known-gap xfail strict → DEFERRED-050); 058 stays data-only
- ✅ T7 VERIFY — Python suite **528 passed / 29 skipped / 2 xfailed** (was 501; +27, 0 regress); glossary Go `TestListEntities_PrefersAuthoredColumnOverEAV` PASS. **Live-smoke:** rebuilt glossary → endpoint returns authored COLUMN canon → client maps `short_description` → `make_glossary_canon_lookup` yields a `CanonFact` (assertion + terms `Transylvania`/`Dracula`) — F-C12-1 contradiction check now genuinely LIVE (was inert `[]`).

**VERIFY-time discovery (live-smoke caught it; PO chose "fix the endpoint"):** the glossary `/internal/books/{id}/entities` endpoint returned `short_description` from an **EAV attribute** (always null), not the authored **column** → F-C12-1 would have stayed inert. Fixed both halves: glossary Go handler `COALESCE(NULLIF(e.short_description,''), short_av.original_value)` (+Go test) AND `GlossaryClient.list_entities` now reads the `short_description` key. The EAV path stays a documented test-harness gap (backfill goroutine not run under test — pre-existing, isolation-confirmed on clean HEAD).

## /review-impl (adversarial pass at POST-REVIEW) — 1 fixed, 2 LOW handled

- ✅ **MED-1 fixed** — `extract_canon_terms` pulled COMMON Latin words (traveling/meet/business) as canon terms; with the negation heuristic a benign fact mentioning a common word + a negation would FALSE-POSITIVE auto-reject (over-fire, contradicting the R2 "under-fires" claim). Fixed: Latin terms restricted to **proper-noun-like Capitalized tokens** (keeps Transylvania/Dracula, drops common words). Guard tests: `test_extract_terms_latin_keeps_proper_nouns_drops_common_words` + an end-to-end `test_common_canon_word_plus_negation_does_not_false_positive_contradict` (rich canon + benign negation → no contradiction → no auto-reject). CJK unchanged (sparse-canon demo; human gate backstop, R2).
- **LOW-1 (coverage)** — added the false-positive e2e above; contradiction→auto-reject is unit-covered (`decide_auto_reject`) and the runner branch is technique-agnostic (proven via the injection e2e). Resume-skips-a-rejected-gap relies on the existing `existing_gap_refs` path (rejected rows are persisted) — accepted as covered-by-composition.
- **LOW-2 (accept)** — an auto-rejected row stores raw (un-neutralized) injection content; it's terminal/never-surfaced and is the forensic record (pre-existing persistence behavior). Documented.
- Suite after fix: **529 passed / 29 skipped / 2 xfailed**.

## Open risks / PO notes
- **R1 (book_id threading)** — adds a field to the job-create contract. Backward-compatible (optional). A job without it can't auto-reject on contradiction (degrades) — acceptable.
- **R2 (CJK contradiction precision)** — coarse prose-token matching → contradiction auto-reject is conservative (under-fires rather than over-fires). Documented; the human gate remains the backstop for subtle contradictions.
- **R3 (false-positive on anachronism ≥2)** — two conservative-list markers in one proposal is a strong egregious signal; risk is low, and a wrongly-rejected proposal is recoverable (re-run). Monitored via the auto-reject event/metric.
