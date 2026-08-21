# Deferral supersession ledger

A deferral lives in a **plan** as a heading; a decision that retires it lives in a **spec** as a
`*Replaces `D-…`*` line. Nothing connected the two, so a spec could declare a deferral replaced
while the plan heading stayed open — and `plan-final-verification` refuses a `[x]` QC row on the
*heading*, so a stale one blocks a row that is actually finished.

Measured 2026-08-21: **29 deferrals declared replaced by a spec, 16 of them still unstruck in the
plan.** That is the batch this ledger adjudicates.

**A `Replaces` line is a claim, not a closure.** Four of the sixteen turned out to be
mis-citations — §3.1 claims to replace `D-T42D-GRAPHSTORE-HAS-NO-CALLERS`, but §3.1 is about
`VectorStore` and the deferral is about `GraphStore`. A rule that struck every heading with a
`Replaces` line would have silently closed four live rows. So each pair is adjudicated by hand
here, and `scripts/superseded-deferral-gate.py` refuses any pair that is not.

| verdict | meaning | the gate then requires |
|---|---|---|
| `SUPERSEDED` | the spec really does close it | the plan heading is struck |
| `MIS-CITED` | the spec's `Replaces` line names the wrong deferral | nothing; the heading stays open |
| `PARTIAL` | the spec closes one half; a named residue stays open | nothing; the residue is stated below |
| `OPEN` | the spec is policy, not closure — the `Retry when` names a future event | nothing |

## Adjudications — 2026-08-21

| deferral | verdict | spec | why |
|---|---|---|---|
| `D-MAINTENANCE-IS-NINE-JANITORS` | SUPERSEDED | §1.2 | `DECIDED · ✅ BUILT (A10)`, and the deferral's own `Retry when` already reads `✅ ANSWERED`. |
| `D-T17-PORT-SCOPE-UNDECIDED` | SUPERSEDED | §1.3 | `Retry when` reads `✅ DECIDED BY THE PO 2026-08-13: the port owns EVERYTHING`. |
| `D-T38-KAL-SCOPE-UNDECIDED` | SUPERSEDED | §5.2 | `Retry when` reads `✅ DECIDED BY THE PO 2026-08-13`; §5.2 settles reads-through-the-KAL. |
| `D-T41-RELATIONS-NOT-REBUILDABLE` | SUPERSEDED | §4.4 | The `Retry when` offers two branches and §4.4 takes one: relations are **accepted** as not rebuildable, and `ISOLATED_STACK.md` says so. |
| `D-QC5-ROLE-JUDGE-PRECISION` | SUPERSEDED | PO 2026-08-21 | Not by §2.3 — that is about verdict *shape*, a different question, and its `Replaces` line is loose. Closed by the PO call **local judge only, measured precision documented as the accepted ceiling**. The check stays off by default, so the gap cannot reach an author. |
| `D-T39-NO-COVERAGE-DIGEST-SOURCE` | SUPERSEDED | §4.5 | The digest question is genuinely closed — no digest, event invalidation instead. ⚠️ §4.5 **overstated it** and was corrected here on 2026-08-21: see the residue note below. |
| `D-T25B-SOAK` | MIS-CITED | §3.2 | §3.2 is the restore drill's recall gap. Unrelated. The soak deferral is live: duration and the `passage` scope are still owed. |
| `D-T42D-GRAPHSTORE-HAS-NO-CALLERS` | MIS-CITED | §3.1 | §3.1 wires **`VectorStore`**. This deferral is **`GraphStore`**. Different port, still no callers. |
| `D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL` | MIS-CITED | §1.1 | §1.1 grows a fact **read**; this is about closing an interval on the **write** path. |
| `D-AGE-BROWSE-PAGES-IN-PYTHON` | OPEN | §1.4 | §1.4 is the standing *"AGE refuses rather than half-implements"* rule — a policy the deferral obeys, not a closure. Waits on T42's read strategy. |
| `D-AGE-EVENT-WRITE-UNIMPLEMENTED` | OPEN | §1.4 | Same: policy, not closure. Waits on T42's write contract. |
| `D-T17-BACKFILL-CYPHER` | OPEN | §1.3 | Waits on a second `GraphStore` adapter (T42) — an event, not a decision. |
| `D-T17-SWEEP-IS-NOT-MECHANICAL` | OPEN | §1.3 | §1.3 re-scopes by class; the `Retry when` still waits on T25 landing. Re-adjudicate when T25 closes. |
| `D-NO-CI-BUILDS-ANY-SERVICE-IMAGE` | OPEN | §5.3 | Consistent, not contradictory: §5.3 decides CI **must** build every image; the plan says building it is out of *this* plan's scope. The work is owed elsewhere. |
| `D-T33-CAUSAL-COVERAGE-UNMEASURED` | PARTIAL | §4.3 | 🔴 **A live gap, found by this audit.** §4.3 is titled *"Causal coverage is measured in QC-6"* — and its body measures **identity only** (duplicate groups, anchor resolution, opaque `e.id`). QC-6 was ticked `[x]` on 2026-08-21 against that table. **Causal coverage was never measured.** The identity half is closed; the causal half is open and now says so. |
| `D-QC5-ATTRIBUTION-CHANNEL-UNWIRED` | SUPERSEDED | §2.2 | The **rule source** half is closed and verified in code, not just claimed: `authoring_run_service.py:745-751` feeds `active_rules` from `CanonRulesRepo.list_active` at the seam QC-5 drives. The **nondeterminism** half is decided (PO 2026-08-21: five runs, temperature 0, seeded where supported) but not yet run. Residue also: `quality_report.py:138` still passes `active_rules=[]` — a second seam, deliberately unstructured per its own docstring, but it reports no `active_rule_count`, so a reader cannot tell that from a failure. ⚠️ **Resolved 2026-08-21:** this id was ALREADY struck-and-closed at plan line 7100 on 2026-08-13 — one deferral, two headings, opposite states, and every reader found whichever came first. The live heading is struck and the residue moved to `D-QC5-FIVE-RUN-SPREAD-NOT-MEASURED`. The gate now refuses this shape outright. |

## Residue notes

### §4.5 corrected — the event invalidation reached **one** cache, not both
§4.5 said the B9 event-driven invalidation *"is the answer for both caches"* and *"makes the LRU's
'never cleared' comment false rather than tolerated"*. Measured 2026-08-21:

* `context/anchors.py` — TTL automaton cache. `invalidate_anchor_cache` exists and **is** called,
  from `events/handlers.py:1060` and `:1464`. Event-invalidated. ✅
* `jobs/glossary_anchor_cache.py` — the per-process LRU. Line 8 still reads *"per-process, never
  cleared"* and line 104 *"Production code never calls clear (M5 spec)"*. **No caller anywhere.**

The comment was never made false. **The digest decision stands** — no digest is worth building —
but the LRU is closed by a different argument than §4.5 gave: it is keyed by
`(book_id, chapter_index)`, bounded to 1000 entries with LRU eviction, and M5 scoped its staleness
to *"read-only within an extraction run"*. That is accept-and-document, not
invalidate-by-event. The deferral's claim that it *"has no such bound"* was wrong: eviction is one.
