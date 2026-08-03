# Pending-refactor debt register

**Opened 2026-08-03** · covers **three tracks whose debt outlived the run that created it**:
the glossary↔KG entity refactor (this folder), the
[chat-service control-plane refactor](../2026-07-30-chat-service-control-plane-refactor.md), and
the [generation SSOT](../2026-07-31-generation-ssot.md).

> **Why one file.** All three are *deferred structural work with residue*, and in every case the
> residue was surviving in a place that will not outlive its run — a Parked row inside a RUNSTATE,
> a sentence in a spec, or nothing at all. Three of the items below were recorded as **closed**
> and are open; four had no written home of any kind.

## How to read it

- **`id`** is `YYYY-MM-DD-NN` — the date the debt was **first recorded in writing**, then a
  sequence within that date. Stable; it does not change when the item moves phase.
- **★ = this file is the item's ONLY home.** Everything else is a pointer, and the linked row is
  authoritative. Do not restate a number here that a command or another register already prints —
  that is how a second source of truth starts (the generation-SSOT run recorded that exact
  mistake as its own debt row).
- **`re-verified`** means the claim was re-run against `24dd7bdac` on 2026-08-03. Rows without it
  are carried from their source document **as written** and have not been re-checked.

---

## A · glossary↔KG entity refactor

Full context: [`README.md`](README.md). All rows also appear in the **Deferred Items** table of
[`docs/sessions/SESSION_HANDOFF.md`](../../sessions/SESSION_HANDOFF.md).

| id | item | state |
|---|---|---|
| **2026-08-03-01** | `D-GLOSSARY-KG-REFACTOR-DESIGN` — three investigations, **no design**. The entry point; nothing else in section A can be worked first | open |
| **2026-08-01-01** | `D-ENTITY-IDENTITY-HASH` — identity is `hash(user, project, name, kind)` over LLM output; a miss mints. **21 of 21** `:EntityStatus` rows unreachable by the guard's FK lookup | **parked** by author 2026-08-02 |
| **2026-08-02-01** | `D-ENTITY-LIFECYCLE` — five private notions of "gone", no event between any two. Game-tier critical | open |
| **2026-08-02-02** | `D-KG-KIND-FACETS` — the **KG-mirror half** of the kind spec's M4 (`kind_code TEXT NOT NULL`) | open |
| **2026-08-02-03** | `D-GLOSSARY-EVENTS-NO-SOT` — three `glossary.*` events outside the "AUTHORITATIVE" registry. **Fires first** of section A: `glossary.entity_deleted` needs it | open |
| **2026-08-02-04** | `D-KIND-FACETS-SURFACE` — the **API + FE half** of M4. 399 entities carry a facet; no consumer can see one | open |
| ★ **2026-08-03-02** | `D-ENTITY-EXISTS-GUARD` — `entity_genres_handler.go:40` has no `deleted_at IS NULL`; guards 6 paths, one of which fires a **paid LLM call** on deleted content and caches it | **fix-now**, open · *re-verified* |
| ★ **2026-08-03-03** | `D-KNOWN-ENTITIES-PER-JOB` — `extraction_worker.py:473` fetches before the chapter loop at `:556`; a deleted entity is re-emitted for the rest of the job | **fix-now**, open · *re-verified* |
| ★ **2026-08-03-04** | `D-OUTBOX-PAYLOAD-TRASH` — `outbox.go:398` re-publishes a trashed entity on edit; knowledge-service re-embeds it, silently reversing the deletion | **fix-now**, open · *re-verified* |
| ★ **2026-08-03-05** | `D-CANON-CHECK-BLIND-TO-ROLE` — a `cast_plan` names Lâm Trạch the trap-setter; the drafting run gave the trap to `Lâm Diệp`, a `rival` **minted seven minutes earlier** by the `cast` pass, and the critic scored **`canon_consistency = 5/5`** on all three chapters. Nothing holds a role assignment where a check can fail on it: the plan has it as free text, the glossary has two untyped `character` rows, the graph has neither. **Kind was correct on both entities — this is not a kind bug** | open · [evidence §1](2026-08-03-dogfood-entity-consistency-evidence.md) |
| ★ **2026-08-03-06** | `D-BOOTSTRAP-PREVIEW-LIES` — `bootstrap_service.propose()` dedupes glossary seeds against *prior proposals only*, never against the book, while the chapter half of the same function does query the book. Offered **12 "NEW GLOSSARY ENTRIES"** that all existed, each rendered `Character` (real kinds: `power_system`, `organization`, `event`, `item`). Apply is safe — upsert-by-name preserved the kinds — so this is a **human-approval gate showing a claim that is wrong on both novelty and kind**, not corruption | open · [evidence §2](2026-08-03-dogfood-entity-consistency-evidence.md) |
| ★ **2026-08-03-08** | `D-UNKNOWN-PARK-IS-PROSE-NOT-DATA` — an entity parked under `unknown` keeps its unmatched attributes only as PROSE: `appendUnmatchedAttrsToFallback` joins them into `- code: value` lines and appends them to the kind's `description`. That is the right instinct (losing the observation is worse than filing it badly) and the wrong SHAPE for the consumer — the thing that will read them is a later kind-resolution pass deciding what this entity actually IS, and it would have to re-parse prose the extractor had already delivered structured. `source_kind_code` remembers the code it arrived as; the raw attribute payload is the missing other half. **Author-proposed 2026-08-03: a JSONB column on the parked row.** Not urgent while parking is rare; load-bearing the moment the refactor tries to re-kind parked entities in bulk, which is the whole point of the bucket | open · [evidence §2 context](2026-08-03-dogfood-entity-consistency-evidence.md) |
| ★ **2026-08-03-07** | `D-KG-EDGE-TYPING-UNCHECKED` — the relationship proposer offered 8 edges, **3 defensible**: one category error (a `power_system` `enemy_of` a person) and two reversed (`event` `betrayed` the two characters who *are* the betrayers). Every fact needed to reject them is already in the glossary kinds the proposer does not consult | open · [evidence §3](2026-08-03-dogfood-entity-consistency-evidence.md) |

**02 · 03 · 04** were declared *"not deferrals — fix now"* and then described as *"already closed."*
That sentence was their entire tracking mechanism, and it was false. They are **fix-now**, not
deferrals: this register exists so they cannot be lost a second time, **not** to license
deferring them.

**05 · 06 · 07** are the 2026-08-03 dogfood rows, and they are a different kind of item: each was
observed in *output a reader would see*, not in code. Their evidence lives in
[`2026-08-03-dogfood-entity-consistency-evidence.md`](2026-08-03-dogfood-entity-consistency-evidence.md),
which also records what the same run proved WORKS — a defect list with no baseline is not evidence.
**05 is the acceptance case for this whole refactor:** a design that cannot prevent it has not
addressed the problem. 06 is small and self-contained (fix-now-shaped, one function); 07 needs the
kind-typing this refactor is already re-cutting, so it waits on the design.

---

## B · chat-service control plane — [`D-CHAT-CONTROL-PLANE`](../2026-07-30-chat-service-control-plane-refactor.md)

**Nothing has been built.** Verified 2026-08-03: no availability SSOT exists in chat-service
(`grep -rn "def availability\|class Availability\|Withheld" services/chat-service/app` → 0), and
`stream_service.py` is unchanged since the spec was written. The interim fixes of 2026-07-30
shipped and are not a substitute — the spec says so itself.

| id | item | state |
|---|---|---|
| **2026-07-30-01** | §A **tool-availability SSOT** — eight places independently answer *"is this tool available, and if not why?"*. Its invariant test (*"for every step of a pinned rail, availability is never `Withheld`"*) is the check that would have caught the originating incident on the day it was introduced | open |
| **2026-07-30-02** | §B **`TurnState`** — one owner of rail cursor / active tools / breaker counters, recomputed at defined lifecycle points. The mid-turn staleness bug is structural and will return under another name until this exists | open |
| **2026-07-30-03** | §C **guards become policies** over `TurnState`, evaluated in one place with logged precedence. Down-payment already made: `_rail_is_in_flight` | open |
| **2026-07-30-04** | §D **cross-mechanism invariant tests** — every mechanism has unit tests for itself; nothing tests them against each other, which is why a contradiction survived | open |
| ★ **2026-07-30-05** | §E the **anti-rot rule** has no home. It is not a row in [`docs/standards/README.md`](../../standards/README.md) and not in its *Known gaps* list. The index's **Agent Control Plane** row governs a different thing (*consuming* the control layer via the ACP SDK), so it does not cover this. Per CLAUDE.md a cross-cutting rule must have a row there — a rule living only in a spec is the shape the standard itself warns about | open · *re-verified* |
| ★ **2026-08-03-05** | **The deferral has no mechanism.** `docs/sessions/SESSION_HANDOFF.md` contains **no `deferral-registry:begin/end` block** (the repo's only one is in the LLM_MMO_RPG handoff), so `scripts/deferral-gate.py` never sees `D-CHAT-CONTROL-PLANE`. Its trigger — *"before the next feature that adds a control mechanism to the turn loop"* — is enforced by nobody noticing. **Not yet fired:** the only post-spec change to `tool_surface.py` (merge `1dc1509ed`) is a 7-line comment | open · *re-verified* |
| ★ **2026-08-03-06** | **The spec's own inventory is stale or unaddressable**, so whoever executes it recounts from scratch: `stream_service.py` is **7,818** lines, not 7,074; the 16 named caps all exist but `chat-service/app` carries ~8 more cap-shaped constants outside the list (`NARRATED_WRITE_NUDGE_CAP` in the same file, plus `ACTIVATED_TOOLS_CAP`, `RAIL_STEP_TOKEN_BUDGET`, `HOT_SEED_TOKEN_BUDGET`, `STORY_STATE_TOKEN_CAP`, `STEERING_TOKEN_CAP`, `SUBAGENT_MAX_ITERATIONS`, `ROUTER_MAX_ADDITIONS`); and 3 of §A's 8 availability places are not addressable by name (`done_suppress` is not a `def`, the repeated-failure de-advertiser is unnamed, and the eighth is *"(as of tonight) the auto-load guard"*) | open · *re-verified* |
| ★ **2026-08-03-07** | **The spec has no DoD, no order, no size, no gate spec.** §D's three bullets are the closest thing to acceptance criteria, and there is no incremental landing strategy for introducing a `TurnState` into a 7.8k-line function — which is the whole risk of §B | open |

---

## C · generation SSOT residue — [`2026-07-31-generation-ssot.md`](../2026-07-31-generation-ssot.md)

The slice board is **CLEAR** (S1–S13 closed 2026-08-01 → 08-03). These outlived it.

### C1 · Already homed — pointer only

**13 open rows** in the *Debt taken on* register of
[`docs/plans/2026-07-31-generation-ssot-RUNSTATE.md`](../../plans/2026-07-31-generation-ssot-RUNSTATE.md#debt-taken-on)
(the struck-through rows there are cleared; do not re-read them as open). That register is
authoritative and is **not** copied here. Its themes, so this file is greppable: plan-liveness
prevention shipped **disproven** · a second `story_order` convention on 16 dogfood scenes + the
writer that produced it · smoke debris · S13's citation half · `chat.*`/`composition.*` trace
namespacing · the **unmeasured cost** of counting ~40% more CJK/Vietnamese tokens · the kernel
estimator's own ~0.78× skew · an uncached identity resolve · no Rust check-status vocabulary
mirror · red-ability proof missing on most CI gates · 7 of 11 sweep cases not in CI · the
output-budget window clamp never exercised in production · no FE surface renders *why* a stream
was unguarded.

### C2 · ★ NOT homed anywhere — found by the 2026-08-03 completeness audit

Each is a §3.1 carry-forward row of the spec whose **owning slice closed without discharging it**,
or a §5 requirement that no slice ever owned.

| id | item | state |
|---|---|---|
| ★ **2026-08-03-08** | **B1 → S11 (closed):** `cowrite.py:350` `_TOKENS_PER_WORD` still duplicates `loreweave_llm.budget.TOKENS_PER_WORD` byte-for-byte — a third home for language-density constants. `cowrite` already imports from that module at line 30, so the dedup is a two-line change nobody made | open · *re-verified* |
| ★ **2026-08-03-09** | **S12-widen:** `scripts/enforcement-claims-gate.py` still checks **contract files only** (*"That is deliberately narrow"*, per its own docstring). It does not cover the B5 class — a **comment** asserting a guarantee — nor the `INV-*` code-invariant rows in the standards index. Those are the two shapes that produced two of that cycle's three worst findings, and the owner "S12 (widen)" was never a slice on the board | open · *re-verified* |
| ★ **2026-08-03-10** | **B4 → S9 (closed *inverted*):** `learning-service/app/db/online_judge.py` records no `generator_model`/`judge_distinct`. The carry-forward row said it *"needs the `ScoreReport` shape, which is S9's"* — S9 correctly shipped as **extract nothing**, so that shape was never built and the row lost its owner | open · *re-verified* |
| ★ **2026-08-03-11** | **B4 → S6 (closed):** `routers/wiki_judge.py:132` still passes `generator_model=art.generator_model` with the comment `# None ⇒ persisted as judge_distinct: null`, so the wiki path's distinctness stays unrecorded. (The translation path *was* fixed — `decoupled_judge.py:382` supplies the run's `model_ref`) | open · *re-verified* |
| ★ **2026-08-03-12** | **§5 Migration surface has no slice, no owner, no place in §6's order, no risk boundary and no DoD clause** — and two of its explicit demands are unmet: `contracts/guard-status.contract.json` carries `CheckStatus` only (no `wiki.generation_status`, the Go-owned union §5 names as having *"no contract file and no drift test"*), and the per-surface **null-semantics decision** (does NULL fail open or closed?) is recorded nowhere, including §8's decision log | open · *re-verified* |
| ★ **2026-08-03-13** | **B3's declared-unwired pair** — `YamlGuardrail` stays unwired until an L3-event write path exists, and `contracts/.spectral.yaml` stays unwired per DEFERRED 078. Both are honestly *declared* rather than claimed, which is correct; they are listed so the declaration has an expiry to check | declared, open |
| ★ **2026-08-03-14** | **Suite restoration is written and measured but NOT executed** — knowledge-service still carries **561 skips** and `-n auto` remains unsafe there (12 failed + 118 errors). Plan: [`docs/plans/2026-08-01-test-suite-restoration.md`](../../plans/2026-08-01-test-suite-restoration.md) | open *(carried from the RUNSTATE overview, not re-measured)* |
| ★ **2026-08-03-15** | **The spec itself is stale as a live document.** Header still reads `SPEC v2 (post-red-team)`; §6 marks only PHASE 0 + ROT-1 done, while the board is clear. §S6's stated blocker — *"`CompositionSettingsView` contains no `critic` string"* — is false at HEAD (14 occurrences; `modelRoles.ts` calls it *"the only UI that sets a critic"*). §6's order omits **S13** entirely, and the risk boundaries omit S3, S6, S8, S12, S13. DoD item 5's *"one pass registry"* is owned by no slice; S8, S9, S10 and S13 have no DoD clause | open · *re-verified* |

---

## Counts

| track | open | of which this file is the only home |
|---|---:|---:|
| A · glossary↔KG | 9 | 3 |
| B · chat control plane | 7 | 3 |
| C · generation SSOT | 13 + 8 | 8 |
| **total** | **37** | **14** |
