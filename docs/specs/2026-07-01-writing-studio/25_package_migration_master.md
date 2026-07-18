# 25 · Package Migration Master — the one ordered, reversible re-key

> **Status:** 📐 SEALED (multi-agent authored + adversarially reviewed 2026-07-10; PO ratified all product decisions same day — see 00B §6) — buildable
> **Scope:** `composition-service` (Python) DDL + backfills + re-key order + access-layer cutover; the `book-service` slice of [`22`](22_scene_model_and_crud.md) A1 is sequenced here but its DDL is owned by `22`.
> **Owns:** ALL migration DDL, backfills, and re-key ordering for the package structure. [`23`](23_book_architecture.md) (Phase 0 + migration phases 1–5), [`22`](22_scene_model_and_crud.md) (B0/B1/A1), `24`, `26`, `27`, `28` reference "25 Phase M*" — they must not restate it. **✅ Task 1b's supersession stamps LANDED 2026-07-10:** [`23`](23_book_architecture.md) carries the ⚠ blocks (migration → this file's M0–M5; its P0.0 pre-flight explicitly replaced by M0.1's derivative-exempt query), 00A §9 carries the ✏️ refinements (PM-3/PM-4/PM-10), and the 22-side pointers are in place. The conflict-precedence clause is retired — the files now agree.
> **Binding law:** [`00A_BOOK_PACKAGE_STRUCTURE.md`](00A_BOOK_PACKAGE_STRUCTURE.md) §7 (DA-1..14) + §9 (BPS-1..21). Two BPS rows require a *refinement forced by shipped code* (PM-4, PM-10) — recorded below with evidence, never silently deviated from.
> Follows [`docs/standards/scope-separation.md`](../../standards/scope-separation.md), [`docs/standards/settings-and-config.md`](../../standards/settings-and-config.md), CLAUDE.md tenancy tiers.

---

## Why

Every table inside `<book>/` (00A §2) still carries the **legacy per-user scope**: `(user_id, project_id)` predicates on 12 tables, a per-user `composition_work` resolution, and an MCP gate that checks *row ownership before the book grant*. The consequence is the exact bug class BPS-1 closes: two collaborators on one book get **two private spec forks** instead of one shared plan — a team that cannot share its `main.tf`. PlanForge already demonstrates the failure live (F5: an EDIT-grantee silently forks an unbackfillable pending Work).

This file is the single ordered plan that turns today's schema into the package structure: BPS-1 (the 12-table re-key), BPS-2 (`composition_work` one-manifest-per-book), BPS-4 (beat removal), BPS-5 (template renames), BPS-6 (`decompose_commit` re-key), plus every repository/gate change those imply. One plan, because piecemeal would mean migrating twice (BPS-1's own rationale).

---

## Investigation findings

Everything below was read from source on 2026-07-10, not from prior docs.

### F1 — the blast radius, counted

Counting `user_id = $1` predicates (the M5 isolation rule, stated verbatim in [`works.py:3-5`](../../../services/composition-service/app/db/repositories/works.py#L3-L5)): **129 exact matches across 20 repository files** (156 counting `$N`-positional variants across 21). The heavy files:

| Table | Repo file | `user_id=$1` sites | Notes |
|---|---|---|---|
| `outline_node` | [`outline.py`](../../../services/composition-service/app/db/repositories/outline.py) | 36 | ~24 methods; every WHERE is `user_id = $1 AND project_id = $2` |
| `generation_job` | [`generation_jobs.py`](../../../services/composition-service/app/db/repositories/generation_jobs.py) | 18 | plus joins from `outline.py:726-816` |
| `composition_work` | [`works.py`](../../../services/composition-service/app/db/repositories/works.py) | 7 | the root everything inherits from |
| `canon_rule` / `style+voice` / `scene_link` / `reference_source` | `canon_rules.py` / `style_voice.py` / `scene_links.py` / `references.py` | 6/6/5/5 | |
| `narrative_thread` / `generation_correction` / `motif_application` | 4 each | | `motif_application` already carries `book_id NOT NULL` |
| `divergence_spec`+`entity_override` / `scene_grounding_pins` | `derivatives.py` 3 / `grounding_pins.py` 2 | | |

Consumers above the repos: [`app/mcp/server.py`](../../../services/composition-service/app/mcp/server.py) hosts **56 tools** with **24 `_work_or_deny` call sites** (+ the helper's own definition at [`:146`](../../../services/composition-service/app/mcp/server.py#L146)) and ~130 `user_id`/`project_id` tokens; ~787 occurrences across 24 router files. Raw SQL escapes the repo layer in exactly one router: [`conformance.py:97-145`](../../../services/composition-service/app/routers/conformance.py#L97-L145) (two joins that double-filter `a.user_id=$1 … o.user_id=$1` — the kinds-bug rule applied to both sides).

### F2 — the MCP gate checks ownership BEFORE the grant, so a grantee can never win

[`server.py:146-161`](../../../services/composition-service/app/mcp/server.py#L146-L161): every project-scoped tool runs `_work_or_deny(works, tc, pid)` → `WorksRepo.get(tc.user_id, project_id)` (per-user SQL, `None` → H13 uniform error) **and only then** `_gate(tc, work.book_id, GrantLevel.…)`. A collaborator holding a full EDIT grant on the book is denied at the *first* step because the Work row belongs to the owner — **the book grant never gets a chance to widen access.** BPS-8's `_book_or_deny` inverts this ordering.

### F3 — the decision being superseded is written down, in code

[`grant_deps.py:14-18`](../../../services/composition-service/app/grant_deps.py#L14-L18): *"composition_work stays PER-USER (caller-keyed) — the book grant gates ACCESS, not the work row's ownership (PO decision, mirrors E0-4a settings-per-user)."* BPS-1/2/8 overturn this recorded decision. The migration must **rewrite that docstring** in the same commit — a stale recorded decision is how the next agent reverts the re-key "back to spec".

### F4 — knowledge-service is ALREADY per-book (the BPS-2 risk check, run)

The BPS-2 register row demanded: *"Verify before migrating that knowledge-service does not assume a per-user project."* Verified — it does not; it models exactly the target shape:

- **Resolve-to-owner is knowledge's whole access layer.** [`grant_deps.py:1-18`](../../../services/knowledge-service/app/auth/grant_deps.py#L1-L18): routes authorize the caller via the *book grant*, then hand the repo the **owner's** user_id. The module states the invariant: *"for a book-bound project `project.user_id == book.owner_user_id` (project creation is book-owner-only)."*
- **Creation is owner-only at the route.** [`routers/public/projects.py:428-429`](../../../services/knowledge-service/app/routers/public/projects.py#L428-L429): `body.book_id is not None and resolve_grant(...) != GrantLevel.OWNER` → uniform 404.
- **Book-level reads are already un-user-scoped.** [`projects.py:454-466`](../../../services/knowledge-service/app/db/repositories/projects.py#L454-L466) `project_meta` (ids only, anti-oracle) and [`:468-487`](../../../services/knowledge-service/app/db/repositories/projects.py#L468-L487) `get_by_book` — *"at most one 'book' project per book"*, `AND NOT is_derivative`.

Three sharp edges remain, all handled in this plan (§BPS-2 verdict): (e1) `create_or_get` dedup is per-`(user, book)` — advisory lock `hashtext("{user_id}:{book_id}")` + `WHERE user_id=$1 AND book_id=$2` ([`projects.py:205-223`](../../../services/knowledge-service/app/db/repositories/projects.py#L205-L223)) — it is per-book *only because creation is owner-only*; (e2) **no DB `UNIQUE` on `knowledge_projects.book_id` exists** — the docstring warns *"legacy rows may have several projects per book; `resolve_work` already tolerates that by picking the earliest"* ([`:190-192`](../../../services/knowledge-service/app/db/repositories/projects.py#L190-L192)); (e3) billing already splits `Principals(owner, caller)` ([`grant_deps.py:45-57`](../../../services/knowledge-service/app/auth/grant_deps.py#L45-L57)) — partition/budget = owner, provider spend = caller.

### F5 — five Work creators, all caller-keyed; one is a live fork bug

1. `POST /books/{book_id}/work` — [`works.py:147-260`](../../../services/composition-service/app/routers/works.py#L147-L260): EDIT gate → resolve → knowledge `create_project` (owner-only!) → `works.create(user_id=caller, …)`; knowledge-outage degrade → `_ensure_pending_work` ([`:92-107`](../../../services/composition-service/app/routers/works.py#L92-L107)).
2. MCP `composition_create_work` — [`server.py:622-712`](../../../services/composition-service/app/mcp/server.py#L622-L712) + `_resolve_or_create_default_project` ([`:539-601`](../../../services/composition-service/app/mcp/server.py#L539-L601)); its MED-1 branch ([`:662-675`](../../../services/composition-service/app/mcp/server.py#L662-L675)) already documents that a non-owner grantee cannot auto-provision.
3. `POST /works/{project_id}/derive` — [`works.py:284-376`](../../../services/composition-service/app/routers/works.py#L284-L376) (see F6).
4. **PlanForge `_ensure_work`** — [`plan_forge_service.py:793-811`](../../../services/composition-service/app/services/plan_forge_service.py#L793-L811): the parameter is *named* `owner_user_id`, but [`routers/plan_forge.py:68-71`](../../../services/composition-service/app/routers/plan_forge.py#L68-L71) passes the authenticated **caller** after only an EDIT gate. An EDIT-grantee running PlanForge therefore **silently forks their own pending Work** for the book — which can *never* be backfilled (knowledge create is owner-only, F4). A latent per-user fork that any `UNIQUE(book_id)` would collide with.
5. `POST /works/by-id/{work_id}/resolve-project` — [`works.py:481`](../../../services/composition-service/app/routers/works.py#L481), the self-heal backfill, again caller-keyed.

### F6 — derivatives share the source's `book_id`, so BPS-2's bare UNIQUE cannot ship as written

[`works.py:322`](../../../services/composition-service/app/routers/works.py#L322): `book_id = source.book_id`; [`:355-357`](../../../services/composition-service/app/routers/works.py#L355-L357): `works.create_derivative(user_id, derivative_project_id, book_id, source.id, …)`. A C23 derivative (dị bản) is **by design** a second `composition_work` row on the same book — spec-only copy-on-write over the same manuscript, with its own knowledge partition. A bare `UNIQUE(book_id)`:

- **fails the backfill** on any book that already has a derivative, and
- **forecloses the shipped C23 feature** going forward.

The register's intent ("one **manifest** per book") survives as a **partial** unique over canonical Works — see PM-4. The same evidence forces a second refinement: if the 12 tables' predicates replaced `project_id` with `book_id` *literally*, a derivative's spec tree, jobs, and canon rules would **merge into the source's** on every book-scoped read. `project_id` must survive as the Work partition key — see PM-3.

### F7 — the one deliberately un-scoped query, and the actor it preserves

[`job_consumer.py:283-306`](../../../services/composition-service/app/worker/job_consumer.py#L283-L306): the re-drive sweeper selects `id, user_id` system-wide (no tenant filter — it is infrastructure) and re-runs each job **as its row's user**. Post-rename that column is `created_by`: the actor survives, so BYOK spend attribution is unchanged. One-line edit; listed in the file table.

### F8 — the proven backfill + PK-swap shapes to copy

- **Batched, marker-gated backfill:** [`migrate.go:654-725`](../../../services/book-service/internal/migrate/migrate.go#L654-L725) (`backfillWordCounts`, CB3): marker table + version-id row, keyset cursor batches of 500 over UUIDv7 ids (`WHERE id > $last ORDER BY id LIMIT 500` — time-ordered total order), one `UPDATE … FROM agg` per batch, pure-function-of-current-data so a crash retry is safe.
- **In-place PK swap under a `pg_constraint` guard:** composition's own C16 re-key, [`migrate.py:49-77`](../../../services/composition-service/app/db/migrate.py#L49-L77) — add col → backfill `uuidv7()` → flip PK inside a guarded `DO $$` block. The exact idempotent-DO-block shape every destructive step below uses.

### F9 — the resolve-to-owner primitive already exists in the shared SDK

[`loreweave_grants/__init__.py:253-268`](../../../sdks/python/loreweave_grants/__init__.py#L253-L268): `GrantClient.resolve_owner(book_id, user_id)` returns the book **owner's** user_id to any grantee, cached, fail-closed. And composition itself already has one resolve-to-owner precedent: [`authoring_runs.py:204-234`](../../../services/composition-service/app/routers/authoring_runs.py#L204-L234) — a book's OWNER-grant holder may pause/close a collaborator's run, *acting as* `foreign.owner_user_id` ("row tenancy preserved").

### F10 — the `.runs/` tables are book-scoped in schema but owner-keyed in every read

`plan_run` ([`migrate.py:935-938`](../../../services/composition-service/app/db/migrate.py#L935-L938)), `authoring_runs` (`:988-991`) and `plan_bootstrap_proposal` (`:1103-1107`) carry `owner_user_id NOT NULL` **and** `book_id NOT NULL`. `plan_artifact` (`:960-970`) carries `owner_user_id` but **no `book_id` column at all** — it is book-scoped only transitively, via `run_id → plan_run.book_id` (FK, `ON DELETE CASCADE`). Every repo read filters by `owner_user_id`: two collaborators on one book cannot see each other's plan runs even though the rows sit inside the package (`00A §2` puts `.runs/` inside `<book>/`). For the three directly-keyed tables the schema needs nothing and only the access layer changes; `plan_artifact`'s widened read must gate through its `plan_run` join (OQ-3).

---

## The BPS-2 knowledge-service verdict

**VERDICT: `UNIQUE(book_id)` (partial, per PM-4) is SAFE NOW. No knowledge-side schema change is a prerequisite.** Evidence in F4: knowledge already keys the canonical book project to the book owner, already resolves grantees to the owner at its access layer, and already exposes un-user-scoped per-book reads. The 1:1 chain `book → composition_work (partial unique) → project (uq_composition_work_project)` therefore lands on a service that expects exactly one canonical project per book.

The three edges become three composition-side obligations, all inside this plan:

1. **(e1) Auto-provision must not race per-user.** Knowledge's `create_or_get` serializes per-`(user, book)`. Post-re-key that stays safe **iff** project creation continues to reach knowledge as the **owner** — which it does, because knowledge's own route rejects non-owners (F4) and this plan keeps auto-provision owner-only (OQ-1 default). No two-user race window opens.
2. **(e2) No knowledge `UNIQUE(book_id)` is added.** Legacy multi-project books exist in the wild (`resolve_work`'s `candidates`/`unmarked_candidates` branches prove it). Composition's pre-flight (M0) asserts one *canonical Work* per book; the knowledge side keeps earliest-wins tolerance. Adding the knowledge constraint would need its own collision policy and is out of scope (and unnecessary — `uq_composition_work_project` already makes the *bound* project unique).
3. **(e3) Billing split is preserved by the rename.** `user_id → created_by` keeps provider spend keyed to the acting caller (BYOK), matching knowledge's `Principals(owner, caller)`. Graph partition and project budget stay with the owner because `knowledge_projects.user_id` is untouched.

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **PM-1** | **One ordered plan, two deploys.** Deploy 1 = M0–M3 (pre-flight → expand → backfill → cutover: the BPS-1/2 re-key). Deploy 2 = M4–M5 (the [`23`](23_book_architecture.md) structure lift + the destructive contract step). Each deploy's migration runs at startup, in-process with the code that needs it. | The re-key is the prerequisite of everything ([`23`](23_book_architecture.md) "P0 gates everything else"); the arc lift needs `structure_node` review-soaked first. Two deploys puts a human checkpoint before the point of no return (PM-13). |
| **PM-2** | **BPS-2 ships now; knowledge-service is untouched.** See verdict above. The only knowledge-adjacent change is composition-side: `_ensure_work` and the resolve tails stop keying by caller (PM-9). | F4 — the check BPS-2 demanded was run and passed. |
| **PM-3** ✏️ *refines BPS-1* | **`book_id` becomes the TENANCY scope key; `project_id` survives as the Work PARTITION key.** Every re-keyed predicate becomes `project_id = $1` (already globally unique per Work via `uq_composition_work_project`) with access gated on the row's `book_id` E0 grant; `book_id` is added, backfilled, `NOT NULL`, and indexed for the book-scoped reads `23` needs (arc list, browser group headers). `user_id` predicates are **deleted**, not replaced. | F6: a literal `project_id → book_id` predicate swap merges a derivative's spec/jobs/canon into the source's. BPS-1's *intent* — "user_id demotes from scope key to actor" — is fully honored; the discriminator between two Works on one book (source vs dị bản) simply cannot be the book. |
| **PM-4** ✏️ *refines BPS-2* | **The manifest unique is PARTIAL:** `CREATE UNIQUE INDEX uq_composition_work_book ON composition_work(book_id) WHERE source_work_id IS NULL AND status = 'active'`. One **canonical** manifest per book; derivatives (C23) remain N-per-book by design; archive-and-recreate stays possible. `uq_composition_work_pending` re-keys `(user_id, book_id)` → `(book_id)` (still `WHERE pending_project_backfill`; such rows are also caught by the canonical unique — the pending index stays as the narrow race guard the C16 comments reason about). | F6. The register's "one manifest per book" was written before checking the derive flow; the partial predicate is what the sentence *means* once C23 is in view. Recorded here rather than silently deviating (00A header rule). |
| **PM-5** | **`user_id` → `created_by` is an in-place `RENAME COLUMN` at cutover (M3), no dual-column window** — on the 12 BPS-1 tables + `composition_work` + `generation_correction` + `motif_application`. The four `.runs/` tables rename `owner_user_id → created_by` in the same sweep. **On the two composite-PK tables (`style_profile`, `voice_profile`) the rename alone is NOT the fix:** their PKs embed the actor ([`migrate.py:453`](../../../services/composition-service/app/db/migrate.py#L453) `PRIMARY KEY (user_id, project_id, scope_type, scope_id)`, [`:468`](../../../services/composition-service/app/db/migrate.py#L468) `(user_id, project_id, entity_id)`) and both upserts conflict on them ([`style_voice.py:53`](../../../services/composition-service/app/db/repositories/style_voice.py#L53)/[`:118`](../../../services/composition-service/app/db/repositories/style_voice.py#L118)) — after a bare rename, `created_by` stays part of ROW IDENTITY, a grantee editing the shared profile INSERTs a second row per scope instead of updating, and the packer's most-specific read returns 2 rows: DA-11 violated by the PK itself. M3.4 swaps the PKs to `(project_id, scope_type, scope_id)` / `(project_id, entity_id)` and demotes `created_by` to a plain actor column; M0.6 pre-flights the cross-user duplicates that can already exist today (EDIT-grantees can write caller-keyed rows now). | House deploy model: startup migration in the same process as the new code, single-replica dev/deploy — there is no old-code window for a dual column to protect. A copy-backfill of an identical value is pure waste. `generation_correction`/`motif_application` join because DA-11 says *"`user_id` inside the package means actor"* and DA-10 forbids two names (`user_id`, `owner_user_id`, `created_by`) for one concept. Reversible: `RENAME` back; M3.4 reverses by restoring the old PKs (safe iff M0.6 held and no post-cutover duplicates were minted — part of the M3 rollback note). |
| **PM-6** | **Backfill shape:** `book_id` copied from `composition_work` via `project_id` join. **Batched keyset (500/batch, UUIDv7 cursor — the F8 pattern) for `outline_node` and `generation_job`** (the two large tables); **single-statement UPDATE for the other ten** (dozens-to-low-thousands of rows each; a batch loop over 40 rows is ceremony). Marker-gated `pkg_rekey_v1` in a `package_migration` marker table (same shape as `word_count_backfill_migration`). | F8. Real data scale: books run to ~4200 chapters; outline/jobs are the only tables that track that scale. |
| **PM-7** | **Pre-flight failures ABORT the migration before any DDL and fail the boot loudly.** Unlike CB3's best-effort word counts (a cosmetic stat), a half-applied scope re-key is a tenancy defect; the service must not serve half-keyed. Every M0 assertion logs the offending rows (ids, counts) and raises. **Nothing is ever silently merged, deleted, or guessed.** | 23 Phase-0 guard, widened. `silent-success-is-a-bug-not-environment`. |
| **PM-8** | **`_work_or_deny` → `_book_or_deny`** ([BPS-8]). New shape: `meta = works.scope_meta(project_id)` — an **un-user-scoped, ids-only** read returning `(book_id, work_id, project_id)`, mirroring knowledge's `project_meta` anti-oracle pattern (F4) — then `_gate(tc, meta.book_id, level)`; `None` → the same H13 uniform error. Tools that take `book_id` directly skip the lookup entirely (the "removes a query" BPS-8 promised applies to those; project-keyed tools keep one ids-only query). HTTP mirrors via a `book_id_for_project` dependency. | F2 — the ordering inversion is the whole fix: grant first-class, row ownership no longer consulted for ACCESS. Ids-only keeps the un-scoped read oracle-safe (knowledge precedent, `projects.py:454-466`). |
| **PM-9** | **Work resolution de-users:** `resolve_by_book(book_id)`, `get_pending_for_book(book_id)`, `get(project_id)`, `get_by_id(work_id)` — all drop the `user_id` parameter; `create*/backfill_project` take `created_by` as a plain actor stamp. `work_resolution.resolve_work` loses `user_id`. PlanForge's `_ensure_work(book_id)` becomes caller-independent — **the F5 fork bug dies structurally**: a grantee resolves THE canonical Work; a grantee-created pending Work is one-per-book (PM-4) and is backfilled by whichever later owner-path creates the project. | F5. The fix is the re-key itself, not a patch on `_ensure_work`. |
| **PM-10** ✏️ *refines BPS-6* | **`decompose_commit`:** `arc_id` → `structure_node_id` (re-pointed in M5 via the lift map), `book_id` added, and the exactly-once index becomes **`UNIQUE(project_id, idempotency_key)`** — not `(book_id, idempotency_key)` as BPS-6 literally says. | Same F6 logic at the ledger: a derivative replaying a client key must not be handed the **source** Work's stored result. `project_id` ⊂ `book_id`, so the register's intent (drop the per-user scope) is honored; only the discriminator is kept. |
| **PM-11** | **`conformance.py`'s raw SQL is re-keyed in place** (both queries keep the double-filter on *both* joined tables — `a.project_id=$1 AND o.project_id=$1` — the kinds-bug rule), not extracted to a repo in this pass. | Minimal-diff cutover; the double-filter discipline is the load-bearing part and survives verbatim with the new key. |
| **PM-12** | **No feature flag. The cutover is atomic per service deploy.** This is a single-service DB: every reader/writer of these tables lives in composition-service and ships in the same image as the migration that reshapes them. A `PKG_REKEY_ENABLED` env flag would be a global toggle gating user-facing behavior — the exact smell [`settings-and-config.md`](../../standards/settings-and-config.md) makes a `/review-impl` finding — and would double every predicate for a window nobody can test both sides of. | Settings law; single-writer DB; startup-migration house style (migrate.py's own docstring: *"applied on every startup — no migration tool"*). |
| **PM-13** | **Rollback points.** M1–M2 are additive → reversible by dropping the new columns/indexes. M3's renames reverse by renaming back (one guarded DO-block each). **M5 is the point of no return** (arc-row delete + CHECK swap + legacy index drops) — carried forward verbatim from [`23`](23_book_architecture.md)'s migration table ("Phase 4 is the point of no return") and gated on every M0/M4 assertion having passed **plus** the D-checklist (test strategy) being green in deploy 1. | 23's rollback rule, promoted to the master plan. |
| **PM-14** | **The superseded PO decision is rewritten at its source.** [`grant_deps.py:14-18`](../../../services/composition-service/app/grant_deps.py#L14-L18)'s docstring is replaced in M3's commit with the new law (per-book rows, grant-gated, `created_by` = actor, pointer to BPS-1/2/8 and this file). | F3. A stale in-code decision note is how a future agent "fixes" the re-key backwards. |
| **PM-15** | **Per-user settings do NOT ride the Work.** `composition_work.settings` today bundles work-level knobs; everything that is genuinely a per-user choice (model refs under BYOK — the reason the old PO decision existed) must already live in per-user settings surfaces, not in the shared manifest. M0 includes an **inventory assertion**: dump distinct `settings` keys and confirm against the settings registry that none is per-user. Any hit → decide (move to user settings) before cutover, never after. **Two keys are already known and decided in this spec** so the inventory cannot stall mid-migration: `source_language` (OQ-7) and `reference_embed_model_ref/_source` (OQ-9 — the literal instance of the old decision's motivation, resolved as a technical pin). | The old decision's *motivation* ("work bundles per-user model-refs that must not leak") is a real concern the re-key must disprove, not ignore. Settings law SET-1..8. |
| **PM-16** ✏️ *corrects 00A §4 (`import_source` row)* | **Outside-the-package tables are explicitly untouched:** `composition_daily_progress`, `composition_progress_baseline` (per-user stats), `import_source` (`owner_user_id`, un-shareable pre-book staging — 00A §4 shelves it at `.runs/` *inside* `<book>/`, which its own DA-11 forbids for a per-user scope key; the conflict is recorded and resolved in OQ-10, and task 1b fixes the 00A row), `consumed_tokens`, `outbox_events`. The `deps/` registry tables (`motif`, `arc_template`, `structure_template`, `motif_link`) keep their 2-tier tenancy unchanged. | 00A §2's "outside the package" list *is* the boundary; touching it here would be scope creep. Recorded per the header rule (never silently deviate from the register). |

---

## The migration — exact steps

All SQL is idempotent (IF NOT EXISTS / guarded DO-blocks), matching migrate.py house style. Python-side backfills live in a new `app/db/package_rekey.py`, called from the migration entrypoint after `_SCHEMA_SQL`, marker-gated.

### M0 — pre-flight assertions (run BEFORE any DDL; any hit → log rows + RAISE, boot fails)

```sql
-- M0.1 · one CANONICAL Work per book (derivatives are exempt BY DESIGN — F6/PM-4).
--        This supersedes 23 P0.0's query, which as written fails on any book with a dị bản.
SELECT book_id, count(*), array_agg(id) FROM composition_work
WHERE source_work_id IS NULL AND status = 'active'
GROUP BY book_id HAVING count(*) > 1;

-- M0.2 · at most one PENDING (lazy) Work per book — two users' outage-forks collide
--        with the re-keyed uq_composition_work_pending(book_id).
SELECT book_id, count(*), array_agg(id) FROM composition_work
WHERE pending_project_backfill GROUP BY book_id HAVING count(*) > 1;

-- M0.3 · zero kind='beat' rows (BPS-4: verified dead, but `kind` was a free string — F6 of 23).
SELECT count(*) FROM outline_node WHERE kind = 'beat';

-- M0.4 · zero ORPHAN project rows — a project_id with no composition_work row has an
--        unrecoverable book_id (cross-DB; no join to knowledge at migration time). Per table:
SELECT 'outline_node' AS t, count(*) FROM outline_node o
  LEFT JOIN composition_work w ON w.project_id = o.project_id WHERE w.project_id IS NULL
UNION ALL SELECT 'generation_job', count(*) FROM generation_job j
  LEFT JOIN composition_work w ON w.project_id = j.project_id WHERE w.project_id IS NULL
-- … same shape for scene_link, narrative_thread, canon_rule, style_profile, voice_profile,
--   scene_grounding_pins, reference_source, decompose_commit, generation_correction.
--   (divergence_spec / entity_override are FK'd to composition_work.id — no orphan possible.)
;

-- M0.5 · PM-15 settings inventory (informational dump + registry cross-check in the test;
--        two keys are pre-decided so this cannot stall mid-migration: source_language = OQ-7,
--        reference_embed_model_ref/_source = OQ-9):
SELECT DISTINCT jsonb_object_keys(settings) FROM composition_work;

-- M0.6 · zero cross-user duplicate style/voice rows per package scope — the old PKs include
--        user_id, so EDIT-grantees can already have written caller-keyed rows that collide
--        with M3.4's narrowed PKs (PM-5).
SELECT project_id, scope_type, scope_id, count(*), array_agg(user_id) FROM style_profile
GROUP BY project_id, scope_type, scope_id HAVING count(*) > 1;
SELECT project_id, entity_id, count(*), array_agg(user_id) FROM voice_profile
GROUP BY project_id, entity_id HAVING count(*) > 1;
```

**Resolution protocol for hits (manual, documented, never automated):** M0.1/M0.2 → an operator picks the survivor row and re-points the loser's children (`UPDATE … SET project_id = <survivor>` per table) or archives the loser — by hand, against the snapshot first. M0.3 → inspect and hand-delete or re-kind the rows. M0.4 → the orphans predate the Work model; archive them to a `_pkg_rekey_quarantine` side table by hand. M0.6 → the operator merges duplicate profiles by hand (per scope: pick the survivor — normally the book owner's row — delete the rest), against the snapshot first. Then re-boot; M0 re-runs.

**Pre-flight preview — run READ-ONLY against the live dev DB, 2026-07-10.** The assertions were
executed ahead of time so Deploy 1 starts with facts, not surprises. Results: **M0.2 = 0 · M0.4
orphans = 0 · 201 Works / 195 books · 81 legacy arc rows** (the M4 lift's whole workload — small).
Two hits, both scoped and **pre-decided**:

| Hit | Detail | Pre-decided resolution |
|---|---|---|
| **M0.1 — ONE book** with two canonical Works | book `019eeb09-a4aa…`, both Works owned by the claude-test account; the 2026-06-22 Work has 6 outline rows, the 2026-06-28 duplicate has **0** (the F5 fork bug caught in the wild) | archive the empty 2026-06-28 Work (`019f0f0d-b723…`); nothing to re-point |
| **M0.3 — 4 `kind='beat'` rows** (the F6 free-string hazard, confirmed real) | all four titled literally "Beat", empty `goal`, test account, same day 2026-06-05 — an agent experiment | archive all 4; nothing references them |

The dev-DB operator pass is therefore **two known actions**, not open-ended triage. Production
data (if any diverges) still gets the full protocol above.

### M1 — EXPAND (additive DDL, inline in `_SCHEMA_SQL`)

```sql
-- M1.1 · book_id on the 12 BPS-1 tables + generation_correction (nullable until M2 completes)
ALTER TABLE outline_node          ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE scene_link            ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE narrative_thread     ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE canon_rule            ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE style_profile         ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE voice_profile         ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE scene_grounding_pins  ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE divergence_spec       ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE entity_override       ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE reference_source      ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE generation_job        ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE decompose_commit      ADD COLUMN IF NOT EXISTS book_id UUID;
ALTER TABLE generation_correction ADD COLUMN IF NOT EXISTS book_id UUID;

-- M1.2 · book-scoped read indexes (partials mirror the existing project ones)
CREATE INDEX IF NOT EXISTS idx_outline_node_book      ON outline_node(book_id)      WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_generation_job_book    ON generation_job(book_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_canon_rule_book        ON canon_rule(book_id)        WHERE active AND NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_narrative_thread_book  ON narrative_thread(book_id)  WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_scene_link_book        ON scene_link(book_id);
CREATE INDEX IF NOT EXISTS idx_reference_source_book  ON reference_source(book_id, created_at DESC);
-- style_profile / voice_profile / pins / divergence / override / decompose_commit / correction:
-- plain (book_id) indexes, same IF NOT EXISTS shape.

-- M1.3 · 23 A1's structure_node table + depth/cycle trigger + outline_node.structure_node_id
--        + motif_application.structure_node_id — DDL text owned by 23 (Target data model),
--        executed here so M4's lift has a target. 22 B1's eight SC4 columns on outline_node
--        land here too (additive; column list owned by 22).
```

*(book-service, parallel and independent: [`22`](22_scene_model_and_crud.md) A1 — `scenes.book_id`/`title`/`source_scene_id` + batched backfill inside `migrate.go`, same CB3 pattern. Sequenced with this deploy but owned by 22.)*

### M2 — BACKFILL (Python, marker `pkg_rekey_v1`, blocking at startup — PM-7)

```sql
-- Large tables (outline_node, generation_job): keyset batches of 500 (F8 pattern)
UPDATE outline_node t SET book_id = w.book_id
FROM composition_work w
WHERE w.project_id = t.project_id AND t.id = ANY($batch_ids) AND t.book_id IS NULL;

-- Small tables: one statement each
UPDATE scene_link t SET book_id = w.book_id FROM composition_work w
WHERE w.project_id = t.project_id AND t.book_id IS NULL;
-- … ditto narrative_thread, canon_rule, style_profile, voice_profile, scene_grounding_pins,
--   reference_source, decompose_commit.
-- FK-derived pair (belt: via work_id, not project_id):
UPDATE divergence_spec t SET book_id = w.book_id FROM composition_work w
WHERE w.id = t.work_id AND t.book_id IS NULL;         -- entity_override identical
-- generation_correction: via its job (the actor stamp stays the corrector's):
UPDATE generation_correction t SET book_id = j.book_id FROM generation_job j
WHERE j.id = t.job_id AND t.book_id IS NULL;
```

**Post-backfill assertions (same run, before M3):** `SELECT count(*) FROM <t> WHERE book_id IS NULL` = 0 for all 13 tables → then `ALTER TABLE <t> ALTER COLUMN book_id SET NOT NULL` (guarded DO-blocks). A non-zero count → RAISE (an M0.4 orphan escaped — impossible unless M0 was bypassed).

### M3 — CUTOVER (same deploy; DDL + the code that ships with it)

```sql
-- M3.1 · the manifest uniques (PM-4)
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_book
  ON composition_work(book_id) WHERE source_work_id IS NULL AND status = 'active';
DROP INDEX IF EXISTS uq_composition_work_pending;
CREATE UNIQUE INDEX IF NOT EXISTS uq_composition_work_pending
  ON composition_work(book_id) WHERE pending_project_backfill;

-- M3.2 · the exactly-once ledger re-scope (PM-10; column re-point happens in M5)
DROP INDEX IF EXISTS idx_decompose_commit_idem;
CREATE UNIQUE INDEX IF NOT EXISTS idx_decompose_commit_idem
  ON decompose_commit(project_id, idempotency_key);

-- M3.3 · actor renames (PM-5) — one guarded DO-block per table, e.g.:
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'outline_node' AND column_name = 'user_id') THEN
    ALTER TABLE outline_node RENAME COLUMN user_id TO created_by;
  END IF;
END $$;
-- … × composition_work, scene_link, narrative_thread, canon_rule, style_profile, voice_profile,
--   scene_grounding_pins, divergence_spec, entity_override, reference_source, generation_job,
--   decompose_commit, generation_correction, motif_application;
--   and owner_user_id → created_by on plan_run, plan_artifact, authoring_runs,
--   plan_bootstrap_proposal (PM-5).
-- idx_composition_work_user is dropped + recreated as idx_composition_work_created_by.

-- M3.4 · composite-PK actor demotion (PM-5): style_profile / voice_profile PK swap — the
-- rename cascades into the constraint but leaves the actor INSIDE row identity, which is
-- DA-11 violated by the PK itself. Guarded DO-block, the F8/C16 shape (runs after M3.3,
-- so the column is already `created_by`):
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
             WHERE table_name = 'style_profile' AND constraint_name = 'style_profile_pkey'
               AND column_name IN ('user_id', 'created_by')) THEN
    ALTER TABLE style_profile DROP CONSTRAINT style_profile_pkey;
    ALTER TABLE style_profile ADD PRIMARY KEY (project_id, scope_type, scope_id);
  END IF;
END $$;
-- … voice_profile identical → PRIMARY KEY (project_id, entity_id). created_by demotes to a
-- plain actor column on both (safe: M0.6 proved no cross-user duplicates). The two upserts'
-- ON CONFLICT targets change to the new PKs in the SAME commit (§Repo/service layer) — a
-- conflict target must name a live unique constraint
-- (postgres-partial-index-on-conflict-predicate-must-match, generalized).
```

**M3 code (lands in the same commit — the access-layer cutover, §Repo/service layer below).**

### M4 — STRUCTURE LIFT (deploy 2; = [`23`](23_book_architecture.md) migration phases 1–3, executed under this plan's gates)

1. For each `outline_node WHERE kind='arc'`: insert a `structure_node` (field mapping per 23 phase 1), recording `(old_outline_id, new_structure_node_id)` in a **temporary lift map** `_arc_lift_map`. Row counts asserted equal.
2. `UPDATE` each arc's child chapters `SET structure_node_id = <new>, parent_id = NULL`.
3. Provenance backfill from `motif_application.annotations->>'arc_template_id'` (23 phase 2 — disagreeing arcs → log + leave NULL, never guess); `motif_application.structure_node_id` backfill + annotation-key drop (23 phase 3).
4. **PM-10 re-point:** `decompose_commit.arc_id` → values mapped through `_arc_lift_map`; column renamed `structure_node_id` (guarded DO-block).

### M5 — CONTRACT (the point of no return — PM-13; gated on M0+M4 assertions + the D-checklist)

```sql
-- M5.1 · delete lifted arc rows + swap the kind CHECK (BPS-4: beat AND arc both gone)
DELETE FROM outline_node WHERE kind = 'arc';
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'outline_node_kind_check') THEN
    ALTER TABLE outline_node DROP CONSTRAINT outline_node_kind_check;
    ALTER TABLE outline_node ADD CONSTRAINT outline_node_kind_check
      CHECK (kind IN ('chapter','scene'));
  END IF;
END $$;
-- Guards re-asserted IMMEDIATELY before: zero kind='beat' rows (an agent could have minted one
-- between deploys — the free-string window only closes when 23 B3's Literal args ship);
-- zero orphan children of deleted arcs.

-- M5.2 · template renames (BPS-5)
ALTER TABLE arc_template RENAME COLUMN threads    TO tracks;
ALTER TABLE arc_template RENAME COLUMN arc_roster TO roster;
-- (guarded DO-blocks; `layout[].thread` readers key on track `key` — updated in 23 A7's code)

-- M5.3 · drop the lift map
DROP TABLE IF EXISTS _arc_lift_map;
```

---

### M6 — registered non-additive downstream train (per OQ-11's rule; added at integration 2026-07-10)

One non-additive change from a downstream spec is registered here so its ordering is load-bearing
and visible, per OQ-11 ("non-additive DDL MUST register as a numbered M-step before building"):

| Step | Change | Ordering |
|---|---|---|
| M6.1 | [`27`](27_planforge_v2_compiler.md) A3: drop `outline_chapter_required`, re-add inverted as `outline_chapter_written_kinds` (chapter/scene nodes may exist with `chapter_id NULL` — the "planned, not yet written" state PF-8 needs), with 27's arc/beat `chapter_id` pre-flight | **After M5** (the CHECK references the post-lift kind set) · ships with **27 V2-A** · MUST land before 27 V2-E's first link insert (every skeleton-link insert violates the old CHECK) |

Additive DDL from 24/26/28 (keyset index, IX-11 columns, `arc_conformance_state`) rides each
spec's own build phase per OQ-11 — no registration needed here.

## Repo/service layer changes (the M3 code sweep)

Signature law after the sweep: **read methods take `project_id` (or `book_id` for book-wide reads) and NO user_id; write methods additionally take `created_by: UUID` as a plain actor stamp; nothing filters on the actor.** Access is decided *before* the repo, at the gate (PM-8).

| File | Change | Scale |
|---|---|---|
| [`app/db/repositories/works.py`](../../../services/composition-service/app/db/repositories/works.py) | PM-9 de-user of all 7 methods; new `scope_meta(project_id) -> (book_id, work_id)` ids-only read (PM-8); `create*/update` take `created_by` | 7 predicates, whole file |
| [`outline.py`](../../../services/composition-service/app/db/repositories/outline.py) | every `user_id = $1 AND project_id = $2` → `project_id = $1`; `commit_decomposed_tree`'s ledger insert stamps `created_by` + `book_id`; docstring rule (:3-5) rewritten | **36 predicates, ~24 methods — the biggest single file** |
| [`generation_jobs.py`](../../../services/composition-service/app/db/repositories/generation_jobs.py) | same sweep; joins to `outline_node` drop the user leg, keep the project leg both sides | 18 predicates |
| `canon_rules.py` · `style_voice.py` · `scene_links.py` · `references.py` · `narrative_thread.py` · `generation_corrections.py` · `motif_application.py` · `derivatives.py` · `grounding_pins.py` | same sweep; `style_voice.py` additionally re-targets both upserts' `ON CONFLICT` ([`:53`](../../../services/composition-service/app/db/repositories/style_voice.py#L53)/[`:118`](../../../services/composition-service/app/db/repositories/style_voice.py#L118)) to the M3.4 PKs `(project_id, scope_type, scope_id)` / `(project_id, entity_id)` | 6/6/5/5/4/4/4/3/2 |
| [`app/mcp/server.py`](../../../services/composition-service/app/mcp/server.py) | `_work_or_deny` → `_book_or_deny` (PM-8) at all **24 call sites** + the helper; `composition_create_work` tail keys `created_by`; MED-1 message survives (OQ-1) | ~130 tokens |
| [`app/routers/works.py`](../../../services/composition-service/app/routers/works.py) | POST /work + derive + resolve-project re-key (PM-9); idempotent-get tails drop `user_id` | :92-260, :284-376, :481+ |
| `routers/outline.py` · `plan.py` · `engine.py` · `canon.py` · `grounding.py` · `style_voice.py` · `references.py` | gate stays `_gate_book`; repo calls drop `user_id`, pass `created_by` on writes | ~787 tokens across 24 router files (mechanical) |
| [`routers/conformance.py`](../../../services/composition-service/app/routers/conformance.py) | PM-11 in-place raw-SQL re-key, double-filter preserved | 2 queries |
| [`app/services/plan_forge_service.py`](../../../services/composition-service/app/services/plan_forge_service.py) | `_ensure_work(book_id)` caller-independent (PM-9 — kills F5); call sites :189/:454/:712 | 1 method + 3 sites |
| [`app/worker/job_consumer.py`](../../../services/composition-service/app/worker/job_consumer.py) | sweeper `SELECT id, user_id` → `id, created_by` (F7) | 1 line |
| [`app/packer/pack.py`](../../../services/composition-service/app/packer/pack.py) + engine callers | the five gated repos (:184-188) called without `user_id`; `pack`'s `user_id` param becomes the actor for spend attribution only | chokepoint + callers |
| [`app/work_resolution.py`](../../../services/composition-service/app/work_resolution.py) | `resolve_work(book_id, …)` — user param deleted | whole module |
| [`app/grant_deps.py`](../../../services/composition-service/app/grant_deps.py) | PM-14 docstring rewrite; `authorize_book` unchanged | doc only |
| `plan_runs.py` · `authoring_runs.py` (repo/service/router) | `owner_user_id` → `created_by` rename ripple; read-scope per OQ-3 | mechanical |

---

## Grant-tier consequence table

After the move, one law: **VIEW reads the package, EDIT writes it, OWNER does the cross-user/administrative acts.** Per re-keyed table (E0 grant on the row's `book_id`; MCP + HTTP identical — same `authorize_book`/`_gate` chokepoints):

| Table | Read | Write | Notes |
|---|---|---|---|
| `outline_node` (+22's SC4 fields) | VIEW | EDIT | shared spec — the BPS-1 headline |
| `scene_link` · `scene_grounding_pins` · `style_profile` · `voice_profile` | VIEW | EDIT | spec satellites |
| `narrative_thread` · `canon_rule` | VIEW | EDIT | `tests/` — assertions are shared |
| `reference_source` | VIEW | EDIT | was per-user; now package-visible (OQ-5) |
| `divergence_spec` · `entity_override` | VIEW | EDIT | derive itself already EDIT-gated on the source book ([`works.py:326`](../../../services/composition-service/app/routers/works.py#L326)) |
| `generation_job` | VIEW | EDIT (prose-gen tier per E0-4c) | **spend stays keyed to `created_by`** (BYOK; matches knowledge `Principals`) |
| `generation_correction` | VIEW | EDIT | correction rides the job |
| `decompose_commit` | — (internal ledger) | EDIT (via the commit endpoint) | replay scoped `(project_id, key)` (PM-10) |
| `composition_work` | VIEW (`get`/resolve) | EDIT (`patch`, create) | knowledge auto-provision stays OWNER (OQ-1); archive = EDIT |
| `plan_run` / `plan_artifact` / `authoring_runs` / `plan_bootstrap_proposal` | OQ-3 (default VIEW; `plan_artifact` via its `plan_run` join — F10) | EDIT · pause/close cross-user = OWNER (existing, [`authoring_runs.py:204-234`](../../../services/composition-service/app/routers/authoring_runs.py#L204-L234)) | schema untouched |

---

## Dual-running & cutover strategy

**There is no dual-read window and no feature flag (PM-12).** Justification, spelled out because it is the kind of decision that looks lazy until the alternatives are priced:

1. **Single-service DB.** Every SQL statement against these 13 tables lives in composition-service (§F1 — one raw-SQL escape, also in this service). No second service can observe a half-cut state.
2. **The migration ships inside the image that needs it** (migrate.py's on-startup model). New code never runs against old schema; old code never runs against new schema except during a multi-replica rolling deploy — and this deployment is single-replica compose/dev today. If multi-replica ever arrives, the rename step (M3.3) is the only non-additive piece and would then move to an expand/contract pair; recorded here so that future operator knows exactly which step to split.
3. **A flag would be worse, not safer.** Doubling 129 predicates behind `if flag` produces two code paths of which only one is ever load-tested, and the flag itself violates the settings boundary (a global env toggle gating user-visible behavior).
4. **Sequencing is the safety mechanism instead:** additive M1–M2 first (old predicates keep working over the expanded schema), cutover M3 with its code atomically, destructive M5 a full deploy later behind a human checkpoint.

---

## Test strategy

| # | Test | Detail |
|---|---|---|
| T1 | **Snapshot-DB migration test** (per 23 D5) | `pg_dump` the shared dev `loreweave_composition` → restore into an ephemeral DB → run M0–M3 (and later M4–M5) → assert: per-table row counts unchanged; zero NULL `book_id`; `created_by` = old `user_id` bit-for-bit; canonical-unique holds; derivative rows survived. **Never against the live dev DB** (`kg-integration-tests-truncate-shared-dev-db`); marked `xdist_group("pg")`. |
| T2 | **M0 assertion unit tests** | Seed a doctored snapshot with each violation class (multi-canonical Work, 2-user pending pair, a `kind='beat'` row, an orphan project row) → assert the migration REFUSES to run and names the rows. The failure path is load-bearing; test it, don't assume it (`checklist-is-self-report-enforce-by-tests`). |
| T3 | **Grantee-widening tests** (the inverse of the old M5-isolation tests) | User B (EDIT grant, not owner): reads owner's outline via MCP (was H13-denied — F2); creates a node (`created_by = B`); PlanForge run by B attaches to THE canonical Work — zero pending forks created (F5 regression). B edits a style scope the owner already set → the shared row is **UPDATED in place** — row count per scope stays 1 and the packer's most-specific read returns exactly one row (the M3.4 effect test, per `checklist-is-self-report-enforce-by-tests`). B adds a reference → the Work's pinned embed model resolves for B or fails actionably, spend attributed to B (OQ-9). User C (no grant): H13/404 everywhere (anti-oracle preserved). |
| T4 | **Derivative-separation tests** | Book with source + dị bản: book-scoped reads return per OQ-2's resolution; a derivative's outline/job/canon reads never leak source rows and vice versa (`project_id` partition — PM-3); `decompose_commit` replay with the same key on the two Works returns two distinct results (PM-10). |
| T5 | **Sweeper + spend attribution** | Re-driven job runs as `created_by` (F7); `generation_job` insert path stamps the acting caller, not the owner — asserted by effect on the usage row. |
| T6 | **Cross-service live-smoke** (≥2 services — composition + book-service grants; mandatory) | Real stack: grantee B live-drives outline read + write + a $0 local-model generation on a shared book. Per `new-cross-service-contract-needs-consumer-live-smoke`, driven through the gateway path, not hand-fed. Evidence string in VERIFY per CLAUDE.md. |
| T7 | **M5 gate rehearsal** | On the T1 snapshot: run M4, assert lift-map completeness (every `decompose_commit.arc_id` resolves), then M5, assert zero orphans + CHECK swap + renames. Only after this rehearsal is M5 allowed on the real DB (PM-13). |

**Rollback points, restated:** after M1/M2 — drop columns/indexes, code untouched. After M3 — rename back + restore old indexes/PKs (M3.4 — safe iff no post-cutover duplicates were minted, per PM-5) + revert the commit. After M4 — `structure_node` rows + lift map are additive; delete them. **After M5 — none.** M5 is why deploy 2 exists.

---

## Task breakdown

**Deploy 1 (one continuous run, one VERIFY):**

| # | Task | File(s) |
|---|---|---|
| 1 | M0 pre-flight + `package_migration` marker table + `_pkg_rekey_quarantine` protocol doc | `app/db/package_rekey.py` (new), `app/db/migrate.py` |
| 1b | Supersession blocks, SAME commit as task 1 (the 22 ⚠-Amendment precedent): 23's P0.0–P0.4 + migration phases 0–5 get a ⚠ block pointing at 25 M0–M5 (P0.0's query lacks the derivative exemption — M0.1 replaces it); 22's A1/B0 sequencing notes point at 25; 00A §4's `import_source` row moves to the outside-the-package list (OQ-10) | `23_book_architecture.md`, `22_scene_model_and_crud.md`, `00A_BOOK_PACKAGE_STRUCTURE.md` |
| 2 | M1 additive DDL (13 × `book_id`, indexes; 23 A1 `structure_node` DDL; 22 B1 columns) | `app/db/migrate.py` |
| 3 | M2 batched/small backfills + NOT NULL flips + assertions | `app/db/package_rekey.py` |
| 4 | M3 DDL (uniques, renames) | `app/db/migrate.py` |
| 5 | M3 repo sweep (the table in §Repo/service layer, top-down: `works.py` → `outline.py` → the nine small repos) | `app/db/repositories/*` |
| 6 | `_book_or_deny` + 24 MCP sites + router gates + `work_resolution` + PlanForge `_ensure_work` + sweeper + `pack.py` | `app/mcp/server.py`, `app/routers/*`, `app/services/plan_forge_service.py`, `app/worker/job_consumer.py`, `app/packer/pack.py` |
| 7 | PM-14 docstring rewrite + PM-15 settings inventory check | `app/grant_deps.py` |
| 8 | T1–T6 | `tests/` |
| — | *(parallel, book-service)* 22 A1 scenes DDL + backfill | `internal/migrate/migrate.go` (owned by 22) |

**Deploy 2 (after deploy-1 D-checklist green + PO checkpoint):**

| # | Task | File(s) |
|---|---|---|
| 9 | M4 lift (arc → `structure_node`, lift map, provenance, `motif_application` backfill) | `app/db/package_rekey.py` |
| 10 | M5 contract (arc delete, CHECK swap, BPS-5 renames, PM-10 re-point, lift-map drop) | `app/db/migrate.py`, `app/db/package_rekey.py` |
| 11 | T7 + re-run T1 over M4–M5 | `tests/` |

**Dependency order:** 1 gates 2–3 gates 4–5–6 (5 and 6 are one atomic commit with 4 — PM-12). 9 needs deploy 1 shipped + 23 A1's table (task 2). 10 needs 9's lift map. [`23`](23_book_architecture.md)'s A3+ (repos/engine/MCP for `structure_node`), 22's B2+, and 26/27/28 all sit **on top of** deploy 1 and are not sequenced here.

---

## Open questions

| # | Question | Disposition |
|---|---|---|
| **OQ-1** | ✅ *ratified (PO 2026-07-10)* — may an EDIT-grantee auto-provision the book's knowledge project (via `resolve_owner` + a service bearer minted as the owner), or does auto-provision stay OWNER-only? | ✅ **Decision (ratified): stays OWNER-only.** Knowledge's E0-3 Q4 decided owner-only deliberately (the project's `user_id` must equal the book owner — F4); minting owner-identity bearers on a grantee's action is a privilege escalation with real billing surface (project budget = owner). The existing MED-1 message already gives the grantee an actionable path. Cost of the default: a grantee-created pending Work waits for the owner's next create/resolve to backfill — surfaced, not silent. |
| **OQ-2** | ✅ *ratified (PO 2026-07-10)* — when a book has derivatives, do book-scoped reads (arc list, browser group headers, scene browser) return the canonical Work's spec only, or all Works' specs? | ✅ **Decision (ratified): canonical only** (`source_work_id IS NULL`); derivative surfaces pass their `project_id` explicitly. A derivative is an alternate universe — mixing its arcs into the source book's browser headers is incoherent UX, and 23's consumers were all designed against "the book's plan", singular. |
| **OQ-3** | ✅ *ratified (PO 2026-07-10)* — do `plan_run`/`plan_artifact`/`authoring_runs`/`plan_bootstrap_proposal` **reads** widen from owner-keyed to book-grant-keyed (VIEW) in deploy 1? For the three tables carrying `book_id` directly, schema already permits it (F10) and only repo predicates change; `plan_artifact` has **no** `book_id` column, so its widened read gates through `JOIN plan_run r ON r.id = plan_artifact.run_id` with the grant checked on `r.book_id` (F10) — still predicate-only, no DDL (a direct `book_id` column is NOT added in M1; the join through the run is the artifact's natural scope). | ✅ **Decision (ratified): yes, in the M3 sweep.** `.runs/` is inside the package (00A §2) and BPS-1's rationale (a team shares its build directory) covers it; leaving it owner-keyed re-creates the F5 class one layer up (a grantee re-runs PlanForge because they cannot see the owner's run). Writes stay actor-stamped; pause/close keeps its OWNER escalation. If the PO prefers caution, deferring **only this** row is cheap — it is predicate-only, no DDL. |
| **OQ-4** | ✅ *ratified (PO 2026-07-10)* — timing of deploy 2 (M4–M5, the point of no return). | ✅ **Decision (ratified): the next session after deploy 1 survives a real authoring session + T1–T6 green** — not the same run. M5 deletes data; a soak window costs nothing (no deadline) and is the only rollback insurance M5 has. |
| OQ-5 | `reference_source` becomes package-visible: collaborators can now read pasted third-party reference passages. | **Decided — follow BPS-1** (it is one of the 12; the shelf steers shared generation, so hiding it from the team makes the pack unreproducible). No licensing change: content was always stored server-side; visibility follows the existing E0 grant the user already chose to extend. |
| OQ-6 | What if M0.1/M0.2 fire on the real dev DB (cross-user duplicate canonical/pending Works)? | **Decided — manual merge protocol** (M0 resolution note): operator picks the survivor, re-points children per table against the snapshot first, re-runs. Never automated, never silently merged (PM-7; 23's "resolved by hand" rule). |
| OQ-7 | Does `composition_work.settings.source_language` (seeded at create — [`works.py:250-252`](../../../services/composition-service/app/routers/works.py#L250-L252)) stay on the shared manifest? | **Decided — yes.** It is a fact about the book (its original language), not a per-user preference; PM-15's inventory assertion is the general guard for anything that is not. |
| OQ-8 | For the integrator: `26` (staleness/conformance surfacing) and `27` (link step) must consume `structure_node_id`s minted in M4 — the lift map is dropped in M5, so any provenance either of them needs must be materialized as columns before M5 runs. | ✅ **Adjudicated MOOT (integration, 2026-07-10):** neither consumer needs the lift map — `26` IX-11's `source` defaults `'authored'` for M4-lifted arcs (correct: they were human-authored pre-lift), and `27`'s provenance is plan-run-scoped (`plan_run_id`/`plan_event_id` exist only on nodes the *linker* mints, never on lifted ones). The lift map drops in M5 as planned. |
| OQ-11 *(added at integration, 2026-07-10)* | Where does post-Deploy-2 DDL from downstream specs ride (`26`'s IX-11 columns + `arc_conformance_state`, `27`'s V2-A, `24`-H1.2's keyset index)? This file declared "26/27/28 are not sequenced here", leaving a gap all three deferred into. | **Decided — the M-train rule.** **Additive** DDL (new nullable columns, tables, indexes) rides *each spec's own build phase*, inline in `_SCHEMA_SQL` in that spec's build order — `IF NOT EXISTS` keeps it idempotent; no central train. **Non-additive** DDL (drops, CHECK swaps, PK changes — e.g. `27` A3's `outline_chapter_required` swap) MUST register as a numbered M-step in THIS file before building, because ordering against M4/M5 is load-bearing. Separately, the `24`-H1.1 children-route semantics flip is **pinned to Deploy 2** (the M4 lift deploy) so route and data flip together — the Manuscript Navigator never sees chapters as roots. |
| OQ-9 | `composition_work.settings.reference_embed_model_ref/_source` — a BYOK model-ref written onto the shared manifest by the references router, write-through on first add ([`references.py:9-17`](../../../services/composition-service/app/routers/references.py#L9-L17), [`repositories/references.py:31-34`](../../../services/composition-service/app/db/repositories/references.py#L31-L34), DDL comment [`migrate.py:477-478`](../../../services/composition-service/app/db/migrate.py#L477-L478)). This is the literal instance of the superseded decision's stated motivation ("the work bundles per-user model-refs that must not leak across collaborators under BYOK" — F3). Does it survive the re-key on the shared manifest? | **Decided — it stays on the manifest, as a TECHNICAL PIN, not a per-user preference.** One embedding space per Work is a property of the shelf's data (every stored vector must be comparable to every query vector), exactly as `source_language` is a property of the book — the settings-law test "would two users want different values?" is **no**: a second model would corrupt retrieval for everyone. Spend stays attributed to the acting caller (`created_by`, BYOK — verdict e3). One obligation rides the decision: a grantee's add/search resolves the pinned — possibly first-adder-owned — `model_ref` through provider-registry **as the caller**; T3 asserts by effect that this resolves for a non-owner (or fails actionably through the existing 422/`embed_model_set=false` path, never silently). If provider-registry refuses foreign refs, the add path re-resolves the equivalent model for the caller and re-pins nothing. M0.5's registry now has an answer for this key instead of a mid-migration stall. |
| OQ-10 | 00A §4 places `import_source` at `.runs/` (inside `<book>/`) with scope key `owner_user_id` — under DA-11 ("`user_id` inside the package means actor, never scope") that row cannot stand as written. PM-16 classifies the table outside-the-package. Which is right? | **Decided — outside-the-package; PM-16 stands and 00A §4's row is the error.** Staging is pre-book: `import_source` rows exist before (and independent of) any Work, and staged raw text is never shared build state. The contradiction is recorded here rather than silently resolved (the header rule PM-4/PM-10 follow); task 1b moves the 00A §4 row to the outside-the-package list in the same supersession commit. |

---

## Risks

| Risk | Mitigation |
|---|---|
| Backfill locks `outline_node`/`generation_job` on a 10k-row book | PM-6 batched keyset, 500/batch (F8's proven shape); small tables single-statement by measured size |
| A book with two canonical Works (or two users' pending forks) silently merges | M0.1/M0.2 **fail loudly**, manual protocol (PM-7) — never merged. Lesson: `silent-success-is-a-bug-not-environment` |
| The migration test truncates/mutates the live dev DB | T1 runs against a restored snapshot only — `kg-integration-tests-truncate-shared-dev-db` |
| Dropping `user_id` predicates opens an IDOR (any project readable by guessing ids) | PM-8: access moves to the E0 gate *before* the repo; `scope_meta` is ids-only (knowledge's anti-oracle precedent); T3 asserts no-grant → 404/H13. Lesson: `worker-loaded-id-needs-parent-scoping` (the sweeper + every by-id load keeps a parent scope — here the book gate) |
| The re-keyed pending-Work race relies on the partial unique's predicate | The catch-and-re-get in `_ensure_pending_work` keeps matching the index predicate exactly — `postgres-partial-index-on-conflict-predicate-must-match` |
| `kind` CHECK swap fires on historical rows nobody inventoried | M0.3 + the M5 re-assert count beats *and* the arc delete precedes the swap — `migration-check-constraint-must-backfill-all-historical-blocks` |
| Mock-heavy unit suites hide a cross-service gate bug (grant client ↔ book-service) | T6 live-smoke through the consumer path — `new-cross-service-contract-needs-consumer-live-smoke`, `mocked-client-hides-server-side-default-filters` |
| A future agent reverts the re-key because the old PO decision is still written in code | PM-14 rewrites `grant_deps.py`'s docstring at the source, where that agent will look |
| Stale images false-green the live-smoke | Rebuild before T6 — `live-smoke-rebuild-stale-images-first` |
| The recon/register overstates or understates the debt (counts drift by session) | Every count in F1 was re-run on 2026-07-10 (`debt-batches-list-is-stale-verify-first`); T1's row-count assertions re-verify at run time |

---

## Non-goals

- **Spec branching (BPS-15).** One canonical spec per book, shared; collaborator divergence forks the **Work** — the C23 derivative substrate, preserved untouched (BPS-15's 2026-07-10 correction: "fork the book" was wrong; the real mechanism is fork the Work, and it exists). Nothing here builds or forecloses the branch UX (diff/merge/promote), which would grow on that substrate.
- **Parts/saga relation (BPS-9, DA-12 guard).** `chapters.part_id` and narrative structure stay independent axes; no DDL in this file touches `parts`, and the M4 lift never reads it.
- **Knowledge-service schema.** No `UNIQUE(book_id)` there (verdict edge e2); no ownership changes; `Principals` billing split untouched.
- **The `deps/` registry** (`motif`, `arc_template` beyond BPS-5's two column renames, `structure_template`, `motif_link`) — 2-tier tenancy already correct (00A §8).
- **Outside-the-package tables** (PM-16) and **`import_source`** — per-user by design, untouched (its 00A §4 placement conflict is recorded in OQ-10).
- **PlanForge link-step content** (owned by `27`), **staleness/conformance surfacing** (owned by `26`), **Plan Hub wiring** (owned by `24`), **new agent tools** (owned by `28`), **`structure_node` MCP CRUD** (specced in 23 BA11).
