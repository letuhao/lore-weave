# Removing ids from the model surface — the migration plan (DQ-T76 (f))

**Owner ruling, 2026-09-01:** *"approve DQ-T76 but we need migrate a lot of thing for this, need
a serious plan and test"* — approving **(f) name in / handle through**, and requiring the plan
before any tool changes.

> **The ruling is the plan, not the patch.** Building it tool-by-tool as they surface is the
> failure mode: a half-migrated catalogue where some tools take a name and some take an id is
> **strictly worse than either end state**, because the model cannot tell which is which.

Every number below is derived by a committed script and dated. Re-run before trusting it.

---

## 0. What problem this actually solves — and the honest size of it

Seven detection mechanisms were measured and rejected on
`D-FABRICATION-GUARD-IS-BLIND-TO-A-VALID-LOOKING-UUID` before this option was taken. The ground
for (f) is that all seven were **downstream of the real error**: asking a model for an id it has
no reachable way to obtain.

**That framing is now only partly supported, and this plan says so up front rather than
inheriting it.** Re-derived 2026-09-02 with `scripts/toolloop/argument_supply_census.py`:

| argument | published in-session | supplier ON THE WIRE | ruling cited |
|---|---|---|---|
| `source_entity_id` | 5% | **9%** (4 of 46) | 4 of 46 ✅ |
| `target_entity_id` | 11% | **96%** (131 of 137) | "67%" — **moved** |
| `run_id` | 41% | 100% (376/376) | ~100% ✅ |
| `project_id` | 54% | 100% (2032/2032) | ~100% ✅ |
| `world_id` | 100% | 100% (214/215) | ~100% ✅ |

🔴 **`target_entity_id` has moved from 67% to 96% since the ruling was written.** The ruling names
it as one of the two places "where [fabrication] does" happen. On today's corpus that is no longer
true, which leaves **`source_entity_id` as the only argument with a genuinely unreachable
supplier**. The migration's high-value surface is one argument, not two.

**This does not withdraw the ruling** — a name-in surface is defensible on its own terms — but it
does change what a successful outcome looks like, and §3 sets the bar accordingly.

---

## 1. The census (required by the ruling)

`scripts/toolloop/id_surface_census.py`, derived at run time. **2026-09-02: 199 live tools, 176 of
them take at least one `*_id`/`*_ref`, across 57 distinct id arguments.** Deprecated tools are
excluded — they are dropped from every wire whatever they declare.

**The arguments that are REQUIRED somewhere, ordered by how many tools require them:**

| argument | used by | required in | observed suppliers |
|---|---|---|---|
| `run_id` | 18 | 16 | 4 |
| `entity_id` | 17 | 10 | 6 |
| `job_id` | 7 | 7 | 2 |
| `node_id` | 8 | 5 | 1 |
| `world_id` | 7 | 5 | 4 |
| `map_id` | 5 | 5 | 2 |
| `user_model_id` | 5 | 4 | 1 |
| `motif_id` | 5 | 3 | 1 |
| `arc_id` | 5 | 2 | 1 |

`model_ref` is used by 18 tools but required by only 1 (DQ-T35 made it optional; DQ-T89 gave it an
account-tier answer). **`book_id` / `chapter_id` / `project_id` are out of scope**: the runtime
injects them from the turn envelope, so they are not the model's to supply.

🔴 **No live tool that takes a NON-CONTEXT id offers a name-based entry point in its own
description.** Four live tools say "by name" — `book_steering_delete`, `glossary_search`,
`memory_recall_entity`, `tool_load` — and every one of them takes only context ids. The resolver
exists (`findEntityByNameOrAlias`, glossary-service `extraction_handler.go:1430`) but **nothing
advertises it on the tool surface**, which is the gap (f) is really about.

**TWENTY-FIVE arguments have ZERO observed suppliers** — `revision_id`, `pass_id`,
`import_source_id`, `source_ref`, `source_entity_id`, `fact_id`, `edited_from_version_id`,
`session_id`, `part_id`, `after_id`, `image_ref`, `scene_id`, `new_parent_arc_id`,
`parent_arc_id`, `structure_node_id`, `plan_run_id`, `rule_id`, `block_id`, `outline_node_id`,
`location_entity_id`, `new_parent_id`, `winner_id`, `source_schema_id`, `structure_template_id`,
`before_chapter_id`. Seven of them are REQUIRED somewhere. For these, "name in" is not a
convenience — it is the only reachable form.

> 🔴 **CORRECTED 2026-09-02.** This paragraph said **ten**. Re-derived by
> `id_surface_census.py`, it is twenty-five; the original came from reading a truncated view of
> the census output rather than the census. The ORDERING is unaffected — these were already
> Wave 1 — but a plan that miscounts its own scope by 2.5x invites the next reader to size the
> work from the wrong number, so it is corrected in place rather than in a footnote.

---

## 2. The ordering (required by the ruling)

**Wave 1 — the only measured-unreachable argument. STATUS: kg_propose_edge BUILT 2026-09-02
(both endpoints accept a name; id wins; ambiguity refuses with candidates). The BAR in §3 is
NOT yet measured, so Wave 1 is built but not proven.** `source_entity_id`: one supplier
(`kg_triage_list`), on the wire for 4 of 46 calls. Plus the twenty-five zero-supplier arguments above
(seven of them required somewhere), which are unreachable by construction. Small, and it is where the value is.

**Wave 2 — the entity family**, where the resolver already exists: `entity_id` (10 required),
`target_entity_id`. `findEntityByNameOrAlias` and `canonicalize_entity_name` do the work already;
this wave is about *exposing* them, not writing them.

**Wave 3 — everything else, and possibly never.** `run_id`, `project_id`, `world_id`, `job_id`
all have suppliers on the wire ~100% of the time. **These are the LOW-value half and the ruling
says so.** A name-in signature here costs signature churn and buys nothing measurable. Wave 3
should not start until Waves 1–2 have moved the bar in §3.

---

## 3. The bar (required by the ruling)

> *"fabricated-id rate, measured before and after on the same corpus. Not 'the tools now take
> names'."*

**Primary metric:** fabricated-id rate on `*_id` arguments, by
`scripts/toolloop/missing_id_stratified.py`, **stratified by argument** — a pooled rate across
waves would measure which tools the batches happened to run, the error this loop has now made
three times.

**Baseline, 2026-09-02**: on the shared-tool population, missing-id failures run 0.57%; the
degenerate-value population is 58 arguments across the whole corpus.

**Wave 1 passes when** `source_entity_id`'s fabrication rate falls *and* its call volume does not,
measured K≥5 on the same scenarios. A rate that falls because nobody called the tool is not a pass.

**A wave FAILS if** the fabricated-id rate does not move on the arguments it touched. Signature
churn without a rate change is a cost with no benefit, and the plan should stop rather than
continue to Wave 3.

---

## 4. Backward compatibility (required by the ruling)

> *"an accept-both tool that silently prefers one is how a migration becomes a defect."*

**Rule: accept both, and SAY which won.** For any migrated tool:

1. The name argument is the **declared** one; the id argument stays accepted but its description
   says it is legacy and names the replacement.
2. When both arrive, **the id wins** (it is unambiguous) — and the result carries an explicit
   `resolved_by: "id" | "name"` field. Silence here is the defect the ruling names.
3. When a name resolves to **more than one** entity, the tool **refuses with the candidates**, in
   the shape the disambiguation card already uses. It must never pick one.
4. The frontend calls these signatures too (§5), so id-acceptance is removed only after an FE
   audit, never in the same change as the name-in addition.

---

## 5. Rollback (required by the ruling)

Each wave is one commit per service, and each is revertible alone because:

- **the name argument is ADDITIVE** — nothing that works today stops working, so a revert cannot
  strand a caller;
- **no schema migration** is involved (this is tool signatures, not tables);
- **the FE keeps passing ids throughout** all three waves, so a revert needs no FE change.

The irreversible step is *removing* id acceptance. That is **out of scope for this plan** and
needs its own ruling once the bar in §3 has been met.

---

## 6. What this plan does NOT cover

- **It is not a code change and does not authorise one.** The next artefact after this is a Wave 1
  branch with its own before/after measurement.
- **The `resolved_by` field is a proposal, not a ruling.** It changes result shapes that consumers
  read.
- **Whether a name is even unique** per argument is unverified outside the entity family. For
  `run_id` or `job_id` there may be no human-meaningful name at all — in which case (f) does not
  apply to them and Wave 3 is empty rather than deferred.
- **The 96% figure for `target_entity_id` is one corpus on one date.** If it drops again, Wave 2's
  value goes up and this plan should be re-derived, not re-read.
