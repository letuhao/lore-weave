---
description: Enter/resume the LOOM track — the lore-grounded co-writer (composition-service) + its Canon Model foundation. Loads track context, enforces the boundary, runs the 12-phase v2.2 human-in-loop workflow at the current milestone.
---

# /loom — Work the LOOM track

**LOOM** = LoreWeave's loom. The **Canon Model** is the *warp* (the fixed threads: *published* canon, in-world/reading order, provenance); the AI **co-writer** weaves the *weft* (new prose) through it. Spoiler-safety = you can only weave with threads already laid down. LOOM turns a book into living canon, then co-writes grounded in it.

Optional argument: a milestone id (e.g. `/loom CM1`, `/loom M4`) to scope to it. No argument → read the **▶ NEXT** block and continue there.

## Track SSOT (read these, in this order, on invoke)
1. **`docs/03_planning/LOOM/SESSION_HANDOFF.md`** — track charter + locked decisions + build order + **▶ NEXT SESSION** block. This is the entry point.
2. The design SSOT for the **current** milestone only:
   - Canon Model (Cycle 0): `docs/specs/2026-06-03-canon-model.md` + `docs/plans/2026-06-03-canon-model-cycle0.md` (**§8 is corrected/authoritative**).
   - Composition (V0): `docs/specs/2026-06-02-composition-design.md` + `docs/plans/2026-06-02-composition-service-v0.md`.
   Read only the section(s) for the milestone you're on — not the whole corpus.

## Hard boundary (NON-NEGOTIABLE)
- LOOM touches: **book-service · worker-infra · knowledge-service · worker-ai · extraction SDK · api-gateway-bff · frontend** + the new **composition-service**.
- LOOM **NEVER touches `services/lore-enrichment-service/`** — it is a sibling track (another agent's work), not a dependency. Primitive 4 (provenance) is *design-aligned* with enrichment's H0, never code-coupled.
- Additive infra only (docker-compose, postgres-init, gateway) — add LOOM blocks, don't edit enrichment's.

## Workflow — 12-phase v2.2 human-in-loop (default)
`CLARIFY → DESIGN → REVIEW → PLAN → BUILD → VERIFY → REVIEW → QC → POST-REVIEW → SESSION → COMMIT → RETRO`
- **PO checkpoints:** end of CLARIFY + POST-REVIEW (STOP and WAIT for the human).
- **`/amaw` opt-in** for these LOOM milestones (cross-service / schema / migration / isolation): **CM1, CM3 (a/b/c), composition M1, M5**. Invoke `/amaw` at the start of those.
- **Proactively suggest `/review-impl`** at POST-REVIEW for: the Canon Model cutover, the worker-ai drainer/retraction, provenance, prose-source concurrency, isolation — anything load-bearing.

## Build order (current → done)
**Cycle 0 — Canon Model (prerequisite):**
`CM1` book editorial lifecycle + `/publish` + migration → `CM3a` revision_id event + internal revision-text endpoint → `CM2` relay confirm (no-op) → `CM3b` knowledge queue + worker-ai coalescing drainer + pinned-revision + retract-before-reextract + B7 fix → `CM3c` passage-ingest + manual-rebuild gating → `CM4` dual-order + backfills → `CM-FE` publish affordance → `CM5` provenance.
**Then Composition V0:** `M0`→`M9` (skeleton → schema → repos → clients/prose-source → packer → isolation → engine+critic → contract+gateway → FE tab → OI-1 publish wiring).

## Process when /loom is invoked
1. **Read** `docs/03_planning/LOOM/SESSION_HANDOFF.md` (the ▶ NEXT block). State the current milestone + its goal in one line.
2. **Classify size** for the milestone: `bash scripts/workflow-gate.sh size <SIZE> <files> <logic> <sideeffects>` (run from repo root only — memory: subdir invocation splits state). Most CM/M milestones are M–XL.
3. **If the milestone is in the `/amaw` list above**, announce and invoke `/amaw` before BUILD.
4. **Enter CLARIFY** (`bash scripts/workflow-gate.sh phase clarify`); recover acceptance criteria from the milestone's plan row; **STOP at CLARIFY end for the PO checkpoint** unless resuming a phase already past it.
5. Proceed through the 12 phases. At VERIFY, since LOOM is cross-service, the evidence string needs a **live-smoke token** (or an explicit `LIVE-SMOKE deferred to D-<NAME>` / `live infra unavailable`).
6. **At POST-REVIEW:** present concise summary, STOP and WAIT. Suggest `/review-impl` if load-bearing.
7. **At SESSION:** overwrite the **▶ NEXT SESSION** block in `docs/03_planning/LOOM/SESSION_HANDOFF.md` (header date/HEAD, NEXT items, Deferred). Land it in the same commit as the code.
8. **COMMIT:** stage only changed files (no `git add -A`); message names the milestone + review fixes + test count.

## Operational notes (LOOM-specific, hard-won)
- **Rebuild BOTH service + worker images** for any service that has one (book/knowledge/worker-ai/composition) — separate tags; use `scripts/build-stack.sh` (stamps the git-SHA freshness label). Stale-image false-greens are a recurring class here.
- Canon Model **CM3b** is the load-bearing risk: coalescing drainer (respect the one-active-job/project unique index — NO job-per-event), pinned-revision fetch, and **retract-before-reextract** (wire `remove_evidence_for_source` + `cleanup_zero_evidence_nodes`, else re-publish drifts canon).
- **canon = published:** never re-introduce extract-on-draft-save. Composition publishes a chapter only when **all its scenes are `status='done'`** (chapter-gate).
- Cache the **glossary `entity_id`** (stable), never the knowledge `canonical_id` (rename-sensitive).

## What /loom does NOT do
- Does NOT change the default workflow for other tracks.
- Does NOT touch lore-enrichment.
- Does NOT skip phases or PO checkpoints.
- Is the LOOM track's entry/resume command — it reads state from the SESSION_HANDOFF, it does not invent the next step.
