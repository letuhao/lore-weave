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

| id | gap | why it blocks | size |
|---|---|---|---|
| `G-S3` | **Lore bible has no schema and no producer.** 17 documents describe the tier; nothing writes or stores one. | `S4` and `S5` have no input | large — a tier |
| `G-S4` | **"Pre-manifest stub" is undefined.** No name, no shape, no owner, no doc. | It is the join between an *unstructured* concept and a *structured* manifest — the one conversion `BOOK_TO_GAME` says is the generators' job | unknown until `S3` has a shape |
| `G-S5a` | **The engine's supported surface is not enumerated for authors.** `engine_default.toml` declares it in engine terms; there is no derived statement of "what an author may say". | A manifest builder cannot be specified without it | medium — derive from existing types |
| `G-S7a` | **Zero realities have ever existed.** | Nothing downstream of `S5` has been exercised end to end | small to prove, if `L4` lands |
| `G-S7b` | **The meta database does not exist**, and `migrations/meta/` is a second migration tree at repo root with no manifest and no gate. | The provisioner's first action writes `reality_registry` | small–medium |
| `G-S8a` | **`reality_registry` has no owner**, and the `db_host` CHECK rejects the dev host. | Any user-owned reality | small schema, large decision |
| `G-S8b` | **`loreweave` is the only login role and it is `rolsuper` + `rolbypassrls`.** | A user-reachable `CREATE DATABASE` path | medium, and it is a prerequisite not a nicety |

---

## 5 · The parked document

[`2026-08-08-user-created-realities.md`](2026-08-08-user-created-realities.md) — **PARKED, not
withdrawn.** Its threat model (8 threats) and layer design (10 layers, each stating what it does not
do) remain the analysis for `S8` when `S8` is reached. What it got wrong is **scope and timing**: it
modelled a terminal stage as a standalone feature, while `S3`/`S4` are undesigned and the engine that
bounds the manifest is the current priority.

**Wake it up when:** `G-S5a` is answered (the authorable surface is known) **and** `G-S7b` + `G-S8b`
are done (meta exists; a `CREATEDB`-only role exists).

---

## 6 · Candidates for "choose one", each independently valuable

Not a plan. A menu, with the dependency each one clears.

| candidate | clears | why it might go first | why it might not |
|---|---|---|---|
| **A · Enumerate the engine's authorable surface** — derive, from `ruleset-core`'s types and `engine_default.toml`, the exact set an author may declare | `G-S5a` | Directly serves "engine first". Reads existing code; invents nothing. It is the input every later stage needs. | Produces a document, not a running thing |
| **B · Stand up meta + one reality end to end** | `G-S7a`, `G-S7b` | The whole per-reality tier has never executed once; this is the DATA/LIVE-RUN axis `1b` never had. Would have caught three of this session's findings in a minute. | Needs `G-S8b` (the role) to be honest about the security shape |
| **C · The `CREATEDB`-only role** | `G-S8b` | Prerequisite for anything user-facing; also removes the superuser bypass a refuter used to defeat constraints. | Infrastructure work with no visible product |
| **D · Give the lore bible a shape** | `G-S3` | Unblocks the whole middle. | Largest, least defined; `BOOK_TO_GAME` says it is authored and unstructured **by nature**, so "a shape" may be the wrong ask |
| **E · Continue slices 2–5** (`crates/dp` SDK) | the tier boundary | Already boarded and sealed as the build order. | Does not touch this pipeline's gaps |

**A is the one this document was written to make possible**, and it is the cheapest: it reads code
that already exists and produces the input `S4` and a future manifest builder both require.
