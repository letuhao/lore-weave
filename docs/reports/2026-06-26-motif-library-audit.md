# Narrative Motif Library — Consolidated Pre-Build Audit

> **Date:** 2026-06-26 · **Inputs:** 8 adversarial sub-agent audits (data · architecture · UX/UI · MCP · security/tenancy · AI-quality/conformance · edge-cases · scenarios) against [`docs/specs/2026-06-26-narrative-motif-library.md`](../specs/2026-06-26-narrative-motif-library.md) (17 sections) + the 2 research POCs + the 8 mockups.
> **Purpose:** the "full evaluation before detail design & plan" gate. This is the authoritative finding set; the spec needs a **revision pass** before PLAN.
> **Verdict:** the **core hypothesis is POC-validated and worth building** (a weak model plans + composes on-beat from an abstract template; tenancy uniqueness is the kinds-bug-correct shape). **But the spec overstates "reuse" three times — two are factual errors about the codebase, one is a category error — and has real tenancy/IDOR + silent-correctness holes.** All are cheapest to fix in DESIGN. The spec is NOT yet PLAN-ready.

---

## §0 The three "reuse" claims that don't hold (highest-confidence — found by ≥2 agents each)

These are the load-bearing credibility failures. Each sits under a crown-jewel feature.

| # | Spec claim | Reality (code-grounded) | Found by | Impact |
|---|---|---|---|---|
| **F-1** | flywheel rides `(:Event)-[:CAUSES\|:HAPPENS_BEFORE]` "**ALREADY PRODUCTION**" (§3.2, §12.4) | **No such edges exist.** knowledge-service events carry only scalar `event_order`/`chronological_order`. I cited the KNOWLEDGE_SERVICE_ARCHITECTURE *design draft* as if it were shipped code. | architecture R1, edge C7 | P3 / arc-reduce / arc-conformance **mis-scoped**; "frequent-subgraph mining" impossible; no Propp-function label to sequence on |
| **F-2** | STITCH pass is "**NEW**" (§17.1/.2/.5) | **`engine/stitch.py` + `worker/operations.py:run_stitch()` already ship** (with canon re-check). The existing pass **no-ops on ≤2-scene chapters** and **elides the middle** via a head+tail char cap — ironic for a "lost-in-the-middle" fix. | architecture R2, AI-quality R6, edge E4 | §17 must be re-written as a *delta* (add repetition signal + dial-respect + fix middle-elision), not greenfield. Shrinks the estimate |
| **F-3** | conformance/eval "**reuse the calibrated judge** (loreweave_eval, F1=0.869)" (§6, §14) | **Category error.** That judge scores *extraction precision/recall* (binary, gold set = human extraction corrections). `motif_conformance`/`plot_density`/freshness are *graded subjective narrative* judgments with **no gold set and none planned**. Calibration math is binary-only. | AI-quality R1/R2 | every quality gate is **unbuilt + uncalibrated**; "≥ A3 on plot_density" is **untestable**; eval-gate can false-pass on noise |

Plus two more "overstated reuse" hits:
- **usage-billing pre-check does NOT exist** in `_execute_generate` (only a local token-budget guard) — yet §13.2 says mining is gated "exactly how generate is gated." Mining's cost-control is **net-new infra**, not reuse. *(MCP R4, security C4 — 2 agents.)*
- **"reuses `reference_source` verbatim"** for retrieval is false: `reference_source` is **single-tenant** (`user_id+project_id`, dozens of rows). Motif retrieval is **tier-merged across a shared, mining-grown system tier** — a different scale + a different correctness regime (→ B-1 below). *(data R1, architecture R5, edge — 3 agents.)*

---

## §1 BLOCKERS — must resolve before BUILD (silent-correctness + tenancy)

### B-1 🔴 Cross-tier embedding-space mismatch — the #1 SILENT bug (4 agents: data R1, arch F5, edge A8/A9/C2)
`_cosine` returns **0.0 on dimension mismatch** (references.py:54) and produces **garbage on same-dim/different-model** vectors. Motif retrieval merges **system (platform-model)** + **user/book (BYOK-model)** vectors. Result: **a user whose embed model ≠ the seed pack's model gets cosine 0.0 against the entire system tier** → the seeded tu-tiên/báo-thù pack (P1's headline deliverable) is **invisible to that user's planner**, silently. Adopt copies the source's stale vector (no re-embed-on-adopt). Dedup (§11) fails *open* (adds duplicates) for the same reason.
→ **Decide before P1:** (a) one fixed **platform embedding model for the whole motif library** (give up per-Work BYOK for motif vectors — simplest, correct), or (b) model-keyed vectors + retrieval filtered to the caller's model + **re-embed-on-adopt/on-miss**. `REAL[]` brute-force vs `pgvector` is a column-type + re-embed migration — decide now, not post-P1.

### B-2 🔴 System-tier write protection is app-code-only; cross-tier read predicate is undefined → IDOR (data R2, security T1/T2/IDOR-1, edge G1/G2)
- "Regular users never write a both-NULL (system) row — enforced in app code" is the **exact phrasing that preceded the original kinds-bug**. composition-service has **no admin identity, no admin-write API, no DB backstop**. The derive-tier-from-absence rule is a **write footgun** (omit both scope fields → system row).
- Cross-tier reads **break the `user_id = caller` invariant every composition repo relies on**. The access predicate for a bare `motif_id` that belongs to no book is **never defined** → `GET /motifs/{id}` / `composition_motif_get` is a textbook IDOR returning other users' private motifs.
→ **Fix:** server-stamp `owner_user_id = JWT.sub` unconditionally + reject both-NULL on the user path; route system seeds through migrate-only (like `structure_template`); add a DB `CHECK`. Define ONE read predicate in the repo SELECT (see §3 Q1 — **resolved below**).

### B-3 🔴 `source_ref` / catalog / `examples[]` leak across the tenant boundary (security IDOR-2/3, C1/C2)
- `source_ref='user:<id>'` on an adopted clone hands the adopter **another tenant's private motif id** → feed to B-2's IDOR to read it. Mined back-links embed the **source book's `chapter_id`s**.
- Catalog `SELECT *` would leak `embedding`, `examples[]` (possibly source prose), provenance. `reference_source` deliberately **excludes `embedding`** from its `_SELECT_COLS` — the catalog must be an explicit allow-list.
- **`import_source` table is named but never defined in the spec** — so "the schema enforces raw-import privacy" (§12.6) is currently fictional. `examples[]` smuggling source prose is guarded only by an LLM post-check (a prompt is not access control).
→ **Fix:** opaque lineage token (not a back-readable foreign id) on any cross-tenant row; allow-list catalog projection; ship the `import_source` schema with scope keys + **no visibility column**; **structurally strip `examples[]` from imported-derived motifs on publish** (DB trigger, not a prompt).

### B-4 🔴 No per-user quotas on publish/adopt/mine; the platform *just added* these for books/chat (security C3/C4)
Instant publish + unbounded adopt (clone 10k public motifs) + unbounded corpus-mining spend — with **no ceilings**. The session log shows `D-MCP-BOOK-CREATE-QUOTA` + `D-MCP-H7-AGGREGATE-CAP` were added days ago for exactly this. Mining has no real billing gate (F-3 corollary).
→ **Fix:** per-user ceilings (publish/adopt/mine-runs); real usage-billing pre-check in the mine/import confirm effect.

---

## §2 HIGH — design-level fixes before PLAN

| ID | Finding | Source |
|---|---|---|
| **H-1** | **B≠C span reconciliation has no precedent.** §12.5 cites "the A3 B≠C reconciliation," but A3 `decompose` maps beats onto a **fixed existing chapter list** (no drop, no compress). Compressing a 15-beat / 60-chapter arc → 3 / 8 chapters is **net-new**; and a 3-chapter book gets a huge per-chapter word budget → re-invites lost-in-the-middle. | arch, edge B5/B6 |
| **H-2** | **`motif_link` has no tenancy scope + no cycle guard.** A global, user-writable edge graph (the kinds-bug shape for *edges*); a `precedes` cycle A→B→A makes the planner's succession-walk + "chain-it" non-terminating. | data E3/E4, edge A5, security T4 |
| **H-3** | **`arc_template.layout` references `motif_code` (string, tier-ambiguous) → dangles across publish/adopt.** Pattern/arc member-cloning is hand-waved (§4.2) with no subgraph clone. | data R4/E2, MCP R3 |
| **H-4** | **Swap/re-derive motif AFTER generation has no data-lifecycle.** The ★ `PATCH …/motif` is specced for preview only; after prose exists it orphans `generation_job.result`, extracted events, and opened `narrative_thread` promises. | edge B7, MCP R2 |
| **H-5** | **`motif_application` keying: missing `book_id`, missing FK, user-vs-book scope undecided.** `motif_id` is NOT NULL + no FK + may be deleted (worst combo → use `ON DELETE SET NULL`). User-keying breaks anti-repetition + trace for **collaborators** (kinds-bug class on the *application* table). | data R3/R6, scenarios S3/S14, edge G2 |
| **H-6** | **MCP tier defects:** `_motif_adopt` classified Tier-A but the glossary precedent it cites is **Tier-W confirm-card**; `_motif_bind`'s undo is unhonored (re-derive destroys committed nodes); mining can't run in-process (must be a 202+poll worker job); per-tool IDOR project-scope assertion missing; `_meta.scope` book-vs-user wrong for user-tier tools. | MCP R1/R2/R4, S1-S4 |
| **H-7** | **adopt SQL won't run as written** (`SELECT ...m.*...` copies id/owner/timestamps; one `ON CONFLICT` can't serve both book- and user-targets; user-tier lock = `hash(NULL)` serializes all). | data E1, arch C4 |
| **H-8** | **UX is a separate app, not the composition studio**, with **no empty/loading/error/permission/cost-confirm states**, an **undesigned drag-grid** (0 mobile/touch, 0 keyboard), **0 ARIA / ~0 responsive**, and **no UI at all for §15 intrigue** (the genre the PO writes). Planner-binding (the "★ core value") **dead-ends with no generate screen**. | UX R1-R8 |
| **H-9** | **P1 is really XL, not L.** It silently absorbs `scheme`+`info_asymmetry` (§15), `target_words`+cap/trim (§16), `match_reason` (§11), and the `motif_conformance` judge dim (§14) — schema migration + planner rework + new generate-path dials + a new (uncalibrated) judge. | architecture C6 |

---

## §3 NEW P1 schema decisions that cannot be cleanly retrofitted (from scenarios)

These change the **embedding/dedup/scope keys** — deciding them post-P1 is a migration. Decide in CLARIFY:

- **N-1 Language axis (S4) 🔴-retrofit:** the platform is multilingual to its bones (`original_language`, `reader_language`, per-language glossary/translation rows) — but `motif` has **one `summary`/`embedding`/`language`-less** key. Add **`language TEXT`** (+ optional per-language `name`/`summary`) in P1; retrofitting after embed+dedup re-keys the whole library. **Recommend: add now**, seed English/Vietnamese.
- **N-2 Genre = filter vs prior (S2):** §3.1 makes `genre_tags ∩ book_genres` a **hard filter** — which **suppresses the cross-genre re-skin the POC celebrates** (a tu-tiên motif filtered out of a thriller book). Make genre a **soft re-ranking prior** OR define "cross-genre adopt re-tags." The architecture currently contradicts its own validation.
- **N-3 Derivative inheritance (S5):** the shipped dị bản COW substrate (`source_work_id` + `entity_override`, fresh `project_id`) means a derivative Work inherits **zero** motifs. Decide whether motifs carry into derivatives (a `motif_override` parallel to `entity_override`) or `variant_of` is the mechanism. Don't paint the schema into a corner.
- **N-4 `source_version INT` (S13):** the upstream-diff/sync (§11, P2) needs a version base; `source_ref` is a string with no version pin. Add `source_version` in P1 (cheap) to enable the 3-way diff later.

---

## §4 PO decisions (consolidated) — one ALREADY made

**✅ DECIDED 2026-06-26 — templates are BOOK-INDEPENDENT (PO answer to Q1).**
Motif/arc_template are **User-owned (+ System seed + Public)**; **the Book tier is dropped**. A book deletion does **not** affect templates. The **binding** (`motif_application`) stays per-book/project and dies with the book. This decision **resolves**: cross-book reuse (S1 — no promote path needed, templates are already user-wide), book-delete cascade (edge F2/F4), and **simplifies the §3-Q1 read predicate to:** `visible IFF owner_user_id IS NULL (system) OR visibility='public' OR owner_user_id = caller` — **no book-grant branch → kills IDOR-1's book dimension** and the collaborator-sees-owner-library collision (T6). Tenancy collapses **3-tier → 2-tier + public** (the audits called the 3-tier collapse-into-one-table over-engineered — this is strictly better). *Trade-off accepted: no per-book template *override*; per-book cast customization stays in `motif_application.role_bindings`.* **Spec §2/§4/§12 must be rewritten to 2-tier.**

**Still open (ranked):**
1. **(B-1)** Embedding model strategy: one platform model for all motif vectors, or model-keyed + re-embed-on-adopt? *(blocks P1 schema.)*
2. **(N-1)** Add `language` to `motif` in P1? *(Recommend yes — retrofit is a migration.)*
3. **(H-5/S3)** `motif_application` scope: per-user or per-book/project? *(Collaboration + anti-repetition + trace correctness ride on this; kinds-bug lesson argues per-book.)*
4. **(N-2)** Genre as hard filter or soft prior? *(POC's cross-genre value vs current §3.1.)*
5. **(F-3)** Who builds the narrative gold set, and when? Or do conformance/plot_density ship as **uncalibrated advisory** (and say so in the UI)? *(Every quality gate depends on this.)*
6. **(H-6)** `_motif_adopt` Tier-A or Tier-W? Does `_motif_bind` spend LLM tokens (→ Tier-W)?
7. **(F-1)** Fund causal-edge extraction in knowledge-service, or re-base mining on scalar-order + the new `motif_beat` extractor? *(Decides whether P3 is reachable.)*
8. **(N-3)** Derivative motif inheritance: carry + `motif_override`, or start empty?
9. **Non-goals to state explicitly:** branching/interactive-fiction (different product), MMO quests (emergent-play), non-fiction (plot-centric schema). *(Prevents reading linearity as an oversight.)*

---

## §5 Re-phasing recommendation

- **P1 is XL** (H-9). Re-scope honestly: schema (2-tier, +`language`, +`source_version`) · planner select+bind · `target_words` dial · **binary** `motif_conformance` (calibrate against a 30-50 scene PO-labeled gold set — the make-or-break for any gate) · the seed pack · **the embedding-model decision (B-1)**. Defer `scheme`/§15 intrigue to **P1.5** unless the PO's cung-đấu genre forces it (then it needs its own mockup first — H-8).
- **Reorder P3 vs P4:** import/deconstruct (P4) is **self-contained text analysis**, does **not** depend on the missing causal-event graph (F-1), and bootstraps the library immediately. Graph-mining (P3) is blocked on F-1. → **do import before mine.**
- **§17 STITCH** is an S/M enhancement of an existing pass (F-2), not a P2 greenfield build.
- **Conformance arc extract-diff** (§14.4) is P4+ (rides F-1 + full re-extraction cost); ship the **coarse chapter_id** signal only near-term.

---

## §6 What the audit CONFIRMED is sound

Not everything is a hole — the foundation holds:
- The **core thesis** (control-layer prompt → weak model plans + composes on-beat, transfers across re-skins) — POC-validated, all 8 agents accept it.
- **Service placement** (extend composition-service, in-DB FK to `outline_node`) — correct (architecture R6).
- **Tenancy uniqueness shape** (`UNIQUE(scope, code)` partials) — the kinds-bug-correct constraint (its *enforcement* is the gap, B-2).
- **MCP-first / provider-invariant intent** — correct (embed via provider-registry; agentic tools as MCP, planner consumption as exempt pipeline).
- **conditions = free-text NL** (§11) — the right v1 call.
- **Manual-authoring-is-baseline** (§3.5) + **advisory-not-gate conformance** (§14.6) — sound principles (the *actuator* for drift is the gap, AI-quality R3).

---

## §7 Next steps
1. **Spec revision pass** — correct F-1/F-2/F-3 (stop claiming reuse that isn't there); rewrite §2/§4/§12 to 2-tier (Q1 decided); fold B-1…B-4 fixes + N-1…N-4 into the schema; re-size P1 as XL; reorder P3/P4.
2. **PO answers §4 open decisions** (esp. B-1 embedding, N-1 language, H-5 application scope — the three P1-schema blockers).
3. **THEN** detailed design + plan per phase. Not before.

**Bottom line:** the idea is validated and worth building; the *spec* needs a correction pass and four blocker decisions before it's PLAN-ready. The audit did its job — it caught two factual errors, one category error, the silent embedding bug, and the tenancy/IDOR holes **in DESIGN, before a line of service code.**
