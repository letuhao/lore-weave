# Roadmap — `feat/composition-service` branch-debt cleanup (5 cycles)

- **Date:** 2026-06-08 · **Branch:** `feat/composition-service` · **HEAD:** `8f20ed7b`
- **Goal (PO-locked 2026-06-08):** pay off **ALL** debt this branch created, **except K17** (entity-embedding write pipeline — separate net-new track) and **except D-A3-PLANNER-FE** (decompose-planner tree UI — a separate FEATURE track; `D-A3-REPLACE-ORPHAN-ARC-NODES` is coupled to it and rides along).
- **Method:** **batch related items per cycle** (PO 2026-06-08); each cycle is a full 12-phase `/loom` pass with VERIFY + `/review-impl`. Cheap/conclusion-driven items first to empty the ledger, then the substantive cross-service work.
- **No deadline** — order is value/cost-driven.

This continues the prod-readiness campaign (cycles 1–4, LOOM-43/46/44/45, all done). Those cleared the **correctness** debts; this roadmap clears the **residual** ledger so the branch's deferral list reaches zero (minus the two excluded tracks).

---

## Scope ledger (what each item is)

| # | Deferral | Kind | Size | Cycle |
|---|---|---|---|---|
| 1 | `D-COMP-STITCH-PERSCENE-CEILING` | Accepted trade-off | XS (doc) | 5 |
| 2 | b-đúng cross-chapter prose-carry | Deprioritized | XS (doc) | 5 |
| 3 | `D-GROUNDING-C-ADOPT` (064) | Optional SDK adoption | XS (re-scout) | 5 |
| 4 | `D-COMP-TIPTAP-SHAPE-DRIFT` | Manually-verified contract | S (test) | 5 |
| 5 | `D-COMP-M2-XREF-OWNERSHIP` (residual) | Reparent-cycle prevention gap | S (code+test) | 5 |
| 6 | `D-COMP-CHAPTER-INFLIGHT-REAPER` | Orphaned-job lifecycle | S–M | 6 |
| 7 | `D-COMP-POST-WORK-RACE` | Concurrency edge | S | 6 |
| 8 | `D-COMP-TRUNCATION-SURFACING` | Cross-service signal | M | 7 |
| 9 | `D-A2S1B2-LIVE-SMOKE` | Deferred verification | M | 8 |
| 10 | `D-COMP-DECOMPOSE-PLAN-LEDGER-DRIFT` | Quality/eval | S–M (CLARIFY-size) | 8 |
| 11 | FE Assemble sub-tab CSS-hidden refactor | FE architecture rule | M `[FE]` | 9 |

**Excluded (separate tracks):** K17 entity-embedding write pipeline; `D-A3-PLANNER-FE` + `D-A3-REPLACE-ORPHAN-ARC-NODES`.

---

## Cycle 5 — Ledger close-out + contract locks (S/M, BE+docs)

**Goal:** empty the "accepted / optional / manually-verified" rows and close two small latent gaps, so the ledger has no soft entries left.

1. **`D-COMP-STITCH-PERSCENE-CEILING` → formally close (won't-fix).** Stitch quality is bounded by its per-scene inputs *by design* (one merge pass can't fully remove re-establishment baked into the inputs; chapter mode is the clean path). Document the rationale; move to DEFERRED "Recently cleared".
2. **b-đúng cross-chapter prose-carry → formally close (deprioritized).** The KG timeline/canon lenses already carry cross-chapter state; raw prose-carry helps only fine continuity, not the granularity-bound metric. Document + retire.
3. **`D-GROUNDING-C-ADOPT` (064) re-scout** (per the existing [debt-payoff-roadmap](2026-06-07-debt-payoff-roadmap.md) Item-1): re-read `app/packer/sanitize.py` + the SDK; verdict = no-clean-slice (update rationale + close) OR one small safe slice (spin a separate S cycle). Conclusion only, no build unless a slice is clean AND valuable.
4. **`D-COMP-TIPTAP-SHAPE-DRIFT` → automated cross-lang lock.** Today only a Python-side golden (`test_prose_doc`) + the B4 persist smoke catch drift. Add an automated contract test that pins composition's `text_to_tiptap_doc` output against book-service's `tiptap.go` shape (a committed golden fixture generated from book-service's serializer, or a doc-shape contract asserted in both). Converts "accepted" → "locked".
5. **`D-COMP-M2-XREF-OWNERSHIP` residual → reparent-cycle prevention guard.** `update_node` permits reparenting with no cycle guard ([outline.py:597](../../services/composition-service/app/db/repositories/outline.py#L597) — the recursive CTE uses `UNION` to *tolerate* a cycle, not prevent it). Add a router/repo-layer guard that rejects a reparent that would form a parent cycle (walk-to-root or `WITH RECURSIVE` ancestor check) → 400/409 + a regression test.

**AC:** rows 1–3 closed in DEFERRED with written rationale; tiptap contract test green; reparent-cycle guard rejects a cycle with a test proving it. Single-service. **Verify:** unit suite + the new tests.

---

## Cycle 6 — Job & work lifecycle robustness (M, BE)

**Goal:** finish the concurrency/lifecycle hardening the cycle-2 guard started.

1. **`D-COMP-CHAPTER-INFLIGHT-REAPER`.** The cycle-2 staleness window *prevents* permanent lockout but leaves orphaned `running`/`pending` jobs lingering (inaccurate dashboards, no terminal state). Add a reaper that marks jobs older than the staleness window `running`→`failed` (a `worker-infra` periodic sweep, or an opportunistic mark inside `create_chapter_job_guarded` when it skips a stale job under the lock — cheapest, already holds the lock). Pairs with `chapter_inflight_stale_secs`.
2. **`D-COMP-POST-WORK-RACE`.** The common get-or-create work race is handled (unique-catch + re-get); the residual is the rarer **duplicate-knowledge-project** race ([works.py:138](../../services/composition-service/app/routers/works.py#L138)). Make the knowledge-project creation idempotent / tolerate the duplicate (catch + re-get the existing project) so a concurrent first-POST can't create two.

**AC:** a stale job is marked `failed` (not left `running`); a concurrent same-user work-POST yields exactly one work + one knowledge project. **Verify:** unit + a **live concurrency smoke vs real Postgres** (mirror cycle-2's `_smoke_chapter_inflight.py`).

---

## Cycle 7 — Truncation surfacing (M, FS cross-service — `/amaw` candidate)

**Goal:** close `D-COMP-TRUNCATION-SURFACING` — replace the dropped char-estimate heuristic (cycle 3 MED-1) with the authoritative signal.

- Thread the LLM **`finish_reason`** (`length` = hit the cap) from the provider → gateway → composition's LLM client → the chapter/stitch/cowrite job result + response. A `truncated: true` flag when `finish_reason == "length"`, replacing the informative-only `max_output_tokens` note.
- Verify the gateway actually forwards `finish_reason` (companion to the [gateway-passthrough-must-forward-all-optional-fields](../../../) lesson) — it may need a gateway/SDK field add, which is the cross-service surface.

**AC:** a deliberately under-capped generation surfaces `truncated: true`; a normal one does not (a non-default regression-lock, not a happy-path). **Verify:** unit + **cross-service live-smoke** (composition ↔ gateway ↔ provider — ≥2 services → live-smoke token required). Consider `/amaw` (cross-system contract). `/review-impl` mandatory (new cross-service field).

---

## Cycle 8 — Live-stack verification & plan quality (M, FS)

**Goal:** discharge the one deferred verification + the plan-content quality item; both need the full live stack.

1. **`D-A2S1B2-LIVE-SMOKE`.** Confirm a **real worker LLM** emits `status_effects` from a published death-chapter → `:EntityStatus{gone}`. The bounded `extract-item` path can't (it leaves `event_order=None`, so A2-S1b-1 skips status_effects by design — LOOM-45 finding). Needs the full **publish → worker-ai** chain (P3 threads `chapter_index→event_order`) + the **fresh-book extraction bootstrap** (a fresh book never auto-extracts on publish — run one manual extraction first; see the composition→canon flywheel-bootstrap lesson). Either it PASSES (clear the row) or it surfaces a real producer gap (new cycle).
2. **`D-COMP-DECOMPOSE-PLAN-LEDGER-DRIFT`.** CLARIFY-size first (quality/eval item from the P1 eval — the decompose plan's scene-beat content drifts vs intent). If it's a tuning fix, do it; if it's larger, re-scope. Grouped here because it's exercised by the same live decompose→generate stack.

**AC:** D-A2S1B2 has a definitive PASS or a tracked producer-gap follow-up; plan-ledger-drift fixed or re-scoped with rationale. **Verify:** **cross-service live-smoke** (publish→worker-ai; ≥2 services).

---

## Cycle 9 — FE Assemble sub-tab CSS-hidden refactor (M, `[FE]`)

**Goal:** fix the known FE architecture-rule violation: the Assemble/compose/grounding/canon/quality sub-tabs use ternary/branch rendering, so switching tabs **unmounts** the in-progress chapter/stitch preview and loses hook state (CLAUDE.md: *"Never conditionally unmount stateful components — use CSS `hidden`"*).

- Convert the sub-tab switch from `{cond ? <A/> : <B/>}` to always-mounted panels toggled with CSS `hidden` (or internal branching), so an in-progress generation/preview survives a tab switch. Holistic across the composition panel's sub-tabs (the handoff flags this as its own task).

**AC:** generate a chapter, switch tabs, switch back → the preview + edit state persist. **Verify:** vitest (a visibility-transition regression test — the kind `/review-impl` repeatedly catches) + `tsc`. FE-only.

---

## Tracking

On each cycle's SESSION phase, update `docs/03_planning/LOOM/SESSION_HANDOFF.md` (✅ section + NEXT) and move cleared rows in `docs/deferred/DEFERRED.md` to "Recently cleared". When all 5 cycles land, the branch's composition/LOOM deferral ledger is empty except the two excluded tracks (K17, planner-FE).

**Suggested order:** 5 → 6 → 7 → 8 → 9 (cheap ledger cleanup first, the cross-service M-items in the middle, the FE refactor last). Order is flexible; cycles are independent except none depend on planner-FE.
