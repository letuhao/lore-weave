# Book → reality — the pipeline INDEX

**Status:** INDEX (2026-08-08). Not a design. Its purpose is to make the parts **choosable**.

**Reconciles:** Data Plane **DP-A1–A19 / DP-R1–R8 / DP-T0–T3**, Foundation Invariants **I1–I19**, User Boundaries & Tenancy, Locked Decisions ledger, Data Plane channels **DP-Ch1–Ch37**

---

## Why this exists

**PO:** *"A user can request a reality creation. It has multiple functions, not only simple data
create — it is manifest ingest and more. And it binds `book → lore bible → pre-manifest stub →
manifest → reality data` and more. This is very complex; we cannot do everything at once. We need to
index them, then choose to design and implement some of the parts."*

And the sequencing rule, which is the load-bearing half:

> **"We are going to the game engine first, because that is the correct build order. You cannot give
> a user a manifest builder if you do not know what the game engine can support."**

The previous document — [`2026-08-08-user-created-realities.md`](2026-08-08-user-created-realities.md)
— designed the **last** stage of this pipeline as if it were a standalone feature. It is not: it is
the terminal step of a chain whose middle is undesigned and whose authorable surface is bounded by an
engine still being built. Its security analysis stays valid; **its timing does not.** Parked, and
pointed at from §5.

---

## 1 · The three tracks this chain crosses

The chain is not one track's work. `BOOK_TO_GAME/_index.md` already draws the boundary, and it is
worth quoting because it is the sentence that stops the pipeline being modelled as one pipe:

> **The game concept is not directly consumable by the game.** It is unstructured by nature. Turning
> it into something an engine can run is the *generators'* job, and that is a different job.

```
  LoreWeave platform          BOOK_TO_GAME                    LLM_MMO_RPG
  ──────────────────          ────────────                    ───────────
  book · glossary · KG    →   world → game concept        →   generators → manifest → engine
  BUILT, real data            DESIGN ONLY, 17 docs            PARTLY BUILT, ~60k lines
```

---

## 2 · The stages, measured

Every "state" cell below is a measurement taken 2026-08-08, not a recollection.

| # | stage | track | state | measured |
|---|---|---|---|---|
| **S1** | **Book** — the source text | LoreWeave | ✅ **built, real data** | `book-service`; `loreweave_book` **584 MB / 394 books** |
| **S2** | **Glossary / KG** — authored lore SSOT + derived graph | LoreWeave | ✅ **built, real data** | `glossary-service` (+ wiki), `knowledge-service`; `loreweave_glossary` **1847 MB** — the largest database in the stack |
| **S3** | **Lore bible** — the authored *game concept*: invents what the book lacks | BOOK_TO_GAME | 🟡 **DESIGN ONLY** | `07_lore_bible.md` + 16 sibling docs. **Zero code.** `_index.md`: *"Nothing here is built."* |
| **S4** | **Pre-manifest stub** — the bridge from unstructured concept to structured input | — | 🔴 **NOT A NAMED ARTIFACT ANYWHERE** | `grep -rli "pre-manifest\|manifest stub"` over all of `docs/` → **no hits**. The PO named it in this conversation; the repo has never had a word for it. |
| **S5** | **Manifest / ruleset** — what the engine ingests | LLM_MMO_RPG | 🟢 **substantially built** | `ruleset-core` 5197 lines · `ruleset-loader` 3852 · real entry point `load_reality(reality_id, store, bindings) -> (Ruleset, RealityBinding)` · **shipped artifacts**: `artifacts/engine_default.toml`, `artifacts/presets/proving-ground.toml` |
| **S6** | **Engine** — the deterministic runtime | LLM_MMO_RPG | 🟢 **substantially built** | `dp-kernel` 15105 · `world-gen` 30772 · `sim-core` 2459 · `actor-hub` 1974 · `game-rules` 1029 |
| **S7** | **Reality data** — the per-reality database | LLM_MMO_RPG | 🟡 **schema built, NEVER INSTANTIATED** | 19 migrations + manifest + provisioner + deprovisioner + capacity planner — and `SELECT count(*) … LIKE 'reality%'` → **0** |
| **S8** | **Reality request** — the user-facing function | — | 🔴 **DESIGNED THIS SESSION, PREMATURE** | No route, no tool; `reality_registry` has no owner. See §5. |

### What the table says when you read it as a whole

**The two ends are built and the middle is not.** `S1`/`S2` hold gigabytes of real content. `S5`/`S6`
are ~60k lines of working engine. **`S3` is 17 design documents and no code, and `S4` does not exist
even as a word.** The pipeline is not a chain with a weak link; it is two solid halves with a gap
between them — and that gap is precisely the tier `BOOK_TO_GAME` was opened to name.

---

## 3 · Why "engine first" is right, stated as a constraint rather than a preference

The manifest is an **authored surface**. Two locked decisions already bound it:

- **`AUTHOR-1`** — *the manifest author is not a programmer.* Complexity in the authored surface is a
  hard cost, priced against what it buys.
- **`LIM-1`** — *a hard ceiling is the manifest's to declare, not the engine's to choose*, and a
  ceiling the engine cannot honour is a number in a file.

⇒ **Every field a manifest builder offers is a promise the engine must keep.** Offering a field the
engine cannot consume produces either a silent no-op or a runtime failure in front of players — and
`AUTHOR-1` says the author cannot be the one to discover which.

**The engine's supported surface is not hypothetical: `artifacts/engine_default.toml` IS that
declaration**, today. So "engine first" is not "wait indefinitely" — it is *stabilise the set of
things `engine_default.toml` can express, then derive the authorable surface from it.* The
dependency is real and it has a concrete artifact at its centre.

---

## 4 · The gaps, named so they can be chosen

> **⚠ RE-MEASURED 2026-08-11 — five of the seven rows below had gone stale, all in the
> same direction: claiming blocked what had since been built.** Four were discharged by the
> reality-layer / turn-loop / durable-subscribe / world-service tracks without anyone coming back to
> this table, and the fifth by the track that re-measured it. **Every one of them is a `SELECT` or an
> `ls` away**, which is what makes the rot worth recording rather than merely fixing: nothing here
> compares a "this is unbuilt" claim against the thing it names, so the table could only ever be as
> current as the last person who happened to re-read it. Tracked as `AS-PIPELINE-INDEX-ROT` in
> [`2026-08-14-authorable-surface-RUN-STATE.md`](../plans/2026-08-14-authorable-surface-RUN-STATE.md).

| id | gap | why it blocks | size |
|---|---|---|---|
| `G-S3` | **Lore bible has no schema and no producer.** 17 documents describe the tier; nothing writes or stores one. | `S4` and `S5` have no input | large — a tier |
| `G-S4` | **"Pre-manifest stub" is undefined.** No name, no shape, no owner, no doc. | It is the join between an *unstructured* concept and a *structured* manifest — the one conversion `BOOK_TO_GAME` says is the generators' job | unknown until `S3` has a shape |
| ~~`G-S5a`~~ | ✅ **DISCHARGED 2026-08-11.** `contracts/ruleset/authorable-surface.v1.yaml` — 8 patch types reachable from `RulesetPatch`, 72 authored keys, the 6 refused keys with the reason each author is told, and the `Floor`/`Mutability`/`Strategy` class of all 20 classified rows. **The answer already existed in executable form**: `RulesetPatch` is `deny_unknown_fields`, so the loader could already say yes or no to any key — it had simply never been written down. This row's own objection to candidate A (*"produces a document, not a running thing"*) was the design constraint: the enumeration is checked from two directions by two methods (`scripts/authorable-surface-gate.py` against the source, `crates/ruleset-loader/tests/authorable_surface.rs` against the real loader), because a hand-written list of a code-derived set is `closed-set-gate`'s drift one level up. 9/9 bitten | — | done |
| ~~`G-S7a`~~ | ✅ **DISCHARGED.** Was *"zero realities have ever existed"*; **10 exist**, and one was created over HTTP through `POST /internal/v1/realities` on 2026-08-11. `SELECT count(*) FROM reality_registry` | — | done |
| ~~`G-S7b`~~ | ✅ **DISCHARGED.** The meta database exists with **39 migrations**, and `migrations/meta/` is governed by `migration-manifest-gate` | — | done |
| ~~`G-S8a`~~ | ✅ **DISCHARGED** by `W6`: `reality_registry` carries `owner_user_id` **and** `owner_kind`. The `db_host` CHECK still requires `^pg-shard-[0-9]+\.(internal\|prod\|staging)$` and the dev host still does not match it — resolved by an **alias** rather than a widened constraint (`pg-shard-0.internal` genuinely resolves inside the compose network), so `db_host` stays a real connectable host | — | done |
| ~~`G-S8b`~~ | ✅ **DISCHARGED** by `W7`. Was *"`loreweave` is the only login role and it is `rolsuper` + `rolbypassrls`"*; there are **three**, and `loreweave_provisioner` is `rolsuper=f rolcreatedb=t` — `CREATEDB` and nothing else. `SELECT rolname, rolsuper, rolcreatedb FROM pg_roles WHERE rolcanlogin` | — | done |

---

## 5 · The parked document

[`2026-08-08-user-created-realities.md`](2026-08-08-user-created-realities.md) — **PARKED, not
withdrawn.** Its threat model (8 threats) and layer design (10 layers, each stating what it does not
do) remain the analysis for `S8` when `S8` is reached. What it got wrong is **scope and timing**: it
modelled a terminal stage as a standalone feature, while `S3`/`S4` are undesigned and the engine that
bounds the manifest is the current priority.

**Wake it up when:** `G-S5a` is answered (the authorable surface is known) **and** `G-S7b` + `G-S8b`
are done (meta exists; a `CREATEDB`-only role exists).

> ### ⚠ ALL THREE CONDITIONS ARE NOW MET (2026-08-11) — and that is a PO decision, not an agent's
>
> `G-S5a` ✅ (`authorable-surface.v1.yaml`) · `G-S7b` ✅ (meta, 39 migrations) · `G-S8b` ✅
> (`loreweave_provisioner`, `CREATEDB` only). The condition this document wrote for itself is
> satisfied, so **`S8` is no longer blocked by the gates it named.**
>
> It does **not** follow that `S8` is next, and this note exists so nobody reads it that way. The
> parking reason was never only the gates — it was **build order**, in the PO's words: *"we are
> going to the game engine first, because you cannot give a user a manifest builder if you do not
> know what the game engine can support."* `S3` (lore bible) and `S4` (pre-manifest stub) are still
> undesigned, and this document's own §5 says the parked spec got **scope and timing** wrong by
> modelling a terminal stage as a standalone feature. Nothing about that has changed.
>
> It also carries a correction it must not be resumed without: it treats creation as ONE operation,
> and the PO's framing is that a user **requests**, and the request runs a multi-function pipeline.
>
> **What has changed is that the blocker is now a product decision rather than an engineering one.**
> Recorded here because the previous state — three unmet gates — was doing the deciding, and it
> stopped being true without anyone noticing.

---

## 6 · Candidates for "choose one", each independently valuable

Not a plan. A menu, with the dependency each one clears.

| candidate | clears | why it might go first | why it might not |
|---|---|---|---|
| ~~**A · Enumerate the engine's authorable surface**~~ | ~~`G-S5a`~~ | ✅ **DONE 2026-08-11.** And its stated objection was answered rather than accepted: it is not a document. The enumeration is a contract checked from two directions by two methods, because a hand-written list of a code-derived set drifts silently — `closed-set-gate`'s failure one level up. **It also found something the survey framing would have missed**: the answer already existed in executable form and only the prose was absent | — |
| ~~**B · Stand up meta + one reality end to end**~~ | ~~`G-S7a`, `G-S7b`~~ | ✅ **DONE.** 10 realities; one created over HTTP | — |
| ~~**C · The `CREATEDB`-only role**~~ | ~~`G-S8b`~~ | ✅ **DONE** (`W7`) — `loreweave_provisioner`, `rolsuper=f rolcreatedb=t` | — |
| **D · Give the lore bible a shape** | `G-S3` | Unblocks the whole middle, and is now the **only** remaining candidate on this menu | Largest, least defined; `BOOK_TO_GAME` says it is authored and unstructured **by nature**, so "a shape" may be the wrong ask |
| ~~**E · Continue slices 2–5** (`crates/dp` SDK)~~ | ~~the tier boundary~~ | ✅ **DONE** | — |

**A was the one this document was written to make possible.** Four of the five candidates are now
done, and `D` is what is left — together with `G-S4`, which cannot be scoped until `D` has an answer.
Both are design work on the pipeline's undesigned middle, which is precisely where the PO's
build-order reasoning pointed.
