# RUN-STATE — the engine's authorable surface: what may an author actually say?

**Reconciles:** `scripts/closed-set-gate.py` · `scripts/zero-digest-gate.py` · `scripts/hot-path-gate.py` · `scripts/gate-wiring-gate.py` — the audit is §1. All three of the first govern `ruleset-core`/`ruleset-loader`, which is this track's subject, and the reconciliation found that **the answer already exists in executable form and has never been written down**: `RulesetPatch` is `deny_unknown_fields`, so the loader can already say yes or no to any key an author writes. `G-S5a` does not need a survey. It needs the existing refusal made legible — and kept honest.

---

## 0 · HOW TO WORK

**The binding execution contract is [`§0.6d` of the reality-layer run-state](2026-08-08-reality-layer-RUN-STATE.md)** — adopted verbatim: the execution invariant, the source-of-truth rule, the six-step bite sequence, the hazards, the blocker rule, the continuation check, and the list of things that are NOT stop conditions (a commit · a green sweep · a POST-REVIEW · uncommitted work · wanting a decision this file can seal).

Hazards, each of which has cost time on the last four tracks:

* **Run `--run-all` DETACHED and read its REAL exit code** (`BDR-89`/`BDR-90`). And **edit nothing while it runs** — the world-service track burned a 25-minute sweep by editing a comment after launching it (`WSD-8`).
* **Byte-level I/O for anything a shell executes, and for documents** (`BDR-86`).
* **Never restore a bite with `git checkout`** (`TLD-10`) — it restores from the index.
* **A bite harness is itself an unverified check** (`TLD-11`), and **a gate's own documentation can trip it** (`WSD-4`).

---

## 1 · PHASE 0 — AUDIT-EXISTING

### 1.1 · Why this track and not the one I recommended

I proposed the gateway's world route. **It is stage `S8` of a pipeline the PO parked on the day it was designed**, with reasoning that is about build order rather than effort:

> *"we are going to the game engine first, because that is the correct build order — you cannot give a user a manifest builder if you do not know what the game engine can support."*

So the recommendation was wrong, and wrong the same way twice in two days: made from what I remembered rather than from what the repo says. `WSD-1` recorded that shape yesterday.

### 1.2 · Four of the five blocking gates are already discharged, and the index does not know it

`2026-08-08-book-to-reality-pipeline-index.md` §4 lists what blocks each stage. Measured today:

| gate | the index says | measured | command |
|---|---|---|---|
| `G-S7a` | "**Zero** realities have ever existed" | **10** | `SELECT count(*) FROM reality_registry` |
| `G-S7b` | "The meta database **does not exist**" | exists, 39 migrations | `\l`; `ls migrations/meta/*.up.sql` |
| `G-S8a` | "`reality_registry` has **no owner**" | `owner_user_id` **and** `owner_kind` | `information_schema.columns` |
| `G-S8b` | "`loreweave` is the **only** login role and it is `rolsuper`" | 3 roles; `loreweave_provisioner` is `rolsuper=f rolcreatedb=t` | `SELECT rolname, rolsuper, rolcreatedb FROM pg_roles WHERE rolcanlogin` |
| **`G-S5a`** | "the engine's supported surface is **not enumerated for authors**" | **still true** | §1.3 |

Its §6 menu is stale in the same direction: **B** (stand up meta + one reality) and **C** (the `CREATEDB`-only role) are done, and **E** (the `dp` SDK slices) is done. Of the five candidates, **A and D remain**, and the document says of A: *"A is the one this document was written to make possible."*

### 1.3 · The finding: the answer is already executable, and only the prose is missing

`G-S5a` reads as though someone must go and decide what an author may declare. **They must not.** It is already decided, in code, and already enforced:

```rust
#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]          // <- patch.rs, and its module doc says why
pub struct RulesetPatch { … }
```

> *"A misspelled key in a rules file is the single most likely authoring error, and the default serde behaviour — ignore it — means the author's edit **silently does nothing**."*

So the loader can already answer *"may an author say X?"* for every X. The authorable surface is exactly `RulesetPatch` and its nested patches — **seven top-level sections**, all `#[serde(default)]`:

| section | shape | what the author is doing |
|---|---|---|
| `[combat]` | 15 scalar keys | setting **values** in engine vocabulary |
| `[stats]` | 5 keys (two are `[i32; SLOT_COUNT]`) | setting **values** |
| `quantities` | `Vec<String>` | **naming identities** the engine has never heard of (`QTY-A5`) |
| `[[resources]]` | 10 keys | declaring which identities are **pools** (`QTY-A4`) |
| `[[progression_kinds]]` | nested, with `[[tiers]]` | `PGN-R2b` — folds into a stored TABLE, not into the `Ruleset` |
| `[[verbs]]` | 10 keys | `CMD-1` — declared actions and their ordinals |
| `[limits]` | 3 keys | `LIM-1` — how big this world declares itself to be; **constrains the other six** |

The `Ruleset` struct's own doc comments already draw the line this track has to state: `combat`/`stats` are *"engine vocabulary with author-set values"*, whereas `quantities` is *"the first thing in this struct an AUTHOR names"* — author-set **identity**. Two different kinds of authoring, and a document that flattens them would be wrong about the most important thing in it.

### 1.4 · So the deliverable is not the document. It is the document's *witness*.

The index's own objection to candidate A is *"produces a document, not a running thing."* That objection is correct and it is fatal on this repo: a hand-written enumeration of a code-derived set is stale the first time someone adds a field, and it fails **exactly** the way `closed-set-gate` exists to prevent — *"Rust forces you to handle every variant but cannot force an ARRAY to CONTAIN every variant, so the list drifts silently."*

An enumeration of authorable keys is that array. It gets the same treatment.

### 1.5 · What already exists to build on — measured, not assumed

* **`RulesetPatch::missing_fields()` is PUBLIC** and returns the names of every undeclared field, built by **exhaustive destructuring** whose comment says *"a new field on `CombatPatch` is a compile error here until the completeness check knows about it."* For a `Default` patch that is the complete field list of `combat` + `stats`, obtained from the compiler rather than from me.
* **`deny_unknown_fields`** gives the refusal direction behaviourally, for free.
* **`engine_default.toml`** already carries every scalar's default and its unit (`_pm` is per-mille), and `engine_default_matches_the_code` already asserts the artifact and the `const fn` agree.
* The engine declares **no** quantities, resources, progression or verbs — so those four sections are *purely* author surface, with an empty engine layer beneath them.

### 1.6 · DP-R2 tier table

| datum | tier | scope key | store | why |
|---|---|---|---|---|
| The authorable-surface enumeration | **build-time artifact** | none | `contracts/` in git | It describes the ENGINE, which is one build for every reality. Not per-user, not per-reality — putting it in a database would give one binary many answers about itself. |
| A reality's authored layer (`RulesetPatch`) | **CP / per-reality** | `reality_id` | the reality's ruleset pin (`RulesetDigest`) | Already shipped; `RLS-A13` ties events to the rules that produced them. |
| `engine_default` (priority-0 layer) | **build-time artifact** | none | `crates/ruleset-loader/artifacts/` | `RLS-D2`: *"engine_default is an ARTIFACT, not prose."* This track is the same move, one level up. |

---

## 2 · SEALED FORKS

**`AS-F1` · The enumeration is a machine-readable CONTRACT with a human-readable rendering, not a prose document.**
`RLS-D2` already made this exact call for the defaults themselves — *"engine_default is an ARTIFACT, not prose"*, because every feature doc stating its own defaults made "omit the field ⇒ the default applies" unverifiable. Stating the authorable surface in prose would recreate the problem one level up. **Reversal trigger:** none.

**`AS-F2` · Both directions are checked, and by two different methods.**
A source-level check (does the enumeration list every field the patch types declare?) and a behavioural check (does the real loader accept every listed key, and refuse an unlisted one?). `V.2` on the reality-layer board asks for *"a mechanical oracle by a DIFFERENT method than the thing it checks"*; here the two halves check each other. A field added with no enumeration entry fails the first; an enumeration entry naming a key the loader would reject fails the second. **Reversal trigger:** none.

**`AS-F3` · This track does NOT change what is authorable.**
It states and guards the surface as it is. Any gap it exposes — a key that should be authorable and is not, or vice versa — is recorded, not fixed. Widening the surface is a design decision with a digest consequence (`RLS-A13`: two realities whose rules differ are two different rulesets), and it belongs to whoever owns the manifest, not to the person writing its inventory. **Reversal trigger:** none within this track.

**`AS-F4` · `progression_kinds` is enumerated but flagged as structurally different.**
Every other section folds into a `Ruleset` in memory; a progression kind folds into a stored TABLE, and `resolve` **refuses** a layer declaring them while `resolve_and_pin` accepts it. An inventory that listed it beside `[combat]` without that distinction would tell an author it works where it does not. **Reversal trigger:** none.

---

## 3 · THE BOARD

| # | row | done = |
|---|---|---|
| ~~`A0`~~ ✅ | this file + the Phase 0 audit | `phase0-reconcile-gate.py` passes, output pasted |
| ~~`A1`~~ ✅ | the enumeration artifact | every section and key of `RulesetPatch` and its nested types, each with type, unit, engine default (where one exists), and whether it is a **value** or an author-named **identity** |
| ~~`A2`~~ ✅ | the source-completeness half | a check that reds when a patch type gains or loses a field the enumeration does not, in **both** directions, with a reach floor |
| ~~`A3`~~ ✅ | the behavioural half | the REAL loader accepts every enumerated key and refuses an unlisted one — run against `ruleset-loader`, not a mock |
| ~~`A4`~~ ✅ | bitten | add a field without enumerating it → red naming both sides; enumerate a key the loader rejects → red; break the reach → red; all restored byte-exact |
| ~~`A5`~~ ✅ | the index is corrected | `G-S5a` discharged and the four stale gates in the pipeline index updated to what was measured in §1.2 |
| ~~`A6`~~ ✅ | verify | `cargo test --workspace` + a **detached** `--run-all` sweep, REAL exit codes pasted |

### `A6` — evidence: both REAL exit codes, read from the processes

```
cargo test --workspace                        EXIT=0    184 suites ok, 0 FAILED
python scripts/gate-wiring-gate.py --run-all  EXIT=0    86 GREEN, 0 RED

  scripts/authorable-surface-gate.py   GREEN  (  0.3s)
  scripts/actor-hub-figures-gate.py    GREEN  ( 20.8s)
```

**86, not 85** — the gate count rose because this track added one. 184 suites is +1 on the 183 the
branch carried in (`authorable_surface`, 4 tests).

**The first sweep of this track exited 1, on a gate I had never heard of.** `actor-hub-figures-gate`
measures figures that documents CITE, and this track moved two of them: wiring the gate took
`hook_gate_scripts` 50 → 51, and the four new tests took `rust_tests` 328 → 332 because
`ruleset-loader` is in its `CRATES`. Five citations across two documents went stale in one commit.
See `ASD-7` — it is the mechanism `AS-PIPELINE-INDEX-ROT` says is missing, already built, scoped to
one track's numbers.

### `A1`–`A3` — evidence

```
authorable-surface-gate: OK — 8 patch type(s) reachable from `RulesetPatch`, 72 authored key(s),
  all enumerated in contracts/ruleset/authorable-surface.v1.yaml and nothing enumerated that is
  not a field; 6 refused key(s) match both ways; 20 classification row(s) agree with the class
  their section advertises

cargo test -p ruleset-loader --test authorable_surface ... 4 passed; 0 failed
gate-wiring-gate: OK — 101 gate(s) discovered, all wired or exempted
```

The contract grew past a key list as the audit went on, and the additions are the substance:

* **The refusals.** `FORBIDDEN_KEYS` (3) and `FORBIDDEN_VERB_KEYS` (3) are keys that are *not*
  unknown — they are well known and simply not the author's, refused **by name** on a permissive
  first pass. An inventory that listed only what is accepted would have missed the half an author
  is most likely to reach for, and `forbidden.rs` already explains why absence is not a mechanism:
  refusing on absence is "a guard defeated by the very edit it exists to catch" (`NV-4`).
* **The classification.** `Floor` / `Mutability` / `Strategy` per field, from `classify!`. "You may
  set this" and "you may set this at preset floor, and it is `AdditiveOnly` thereafter" are
  different promises, and only the second is useful to a manifest builder.

### `A4` — 11/11 bitten, every restore byte-exact

```
[BITTEN]   a patch field the contract does not enumerate
[BITTEN]   a contract key that is not a field
[BITTEN]   a key removed from FORBIDDEN_KEYS
[BITTEN]   a classify row that no longer matches the advertised class
[BITTEN]   the self-test when the closure stops recursing
[BITTEN]   the reach floor when the source walk reads only one file
[BITTEN]   an empty source walk is a MISUSE naming the root
[BITTEN]   an engine default that is not the artifact's
[BITTEN]   an artifact default the contract does not quote
[BITTEN]   deny_unknown_fields removed from a patch type          <- source gate stays GREEN
[BITTEN]   the per-verb-row refusal never consulted               <- source gate stays GREEN
bitten: 11/11
```

**The last two are why there are two halves.** Both leave every name matching every name, so the
source gate is perfectly happy; only the loader can tell you the enumeration has stopped being
complete. And the two reach arms are deliberately different: a *partial* walk breaches the floor
(the root is found, the closure just quietly covers 3 types instead of 8), while an *empty* walk
never finds the root at all and must be a MISUSE that names it — a closure from a missing root
reaches nothing, and nothing agrees with everything.

---

## 4 · OPEN ROWS

| id | what | why not here | mechanism |
|---|---|---|---|
| `AS-PIPELINE-INDEX-ROT` | the pipeline index's gate table was wrong on **four of five** rows, all in the optimistic-for-work direction (claiming blocked when discharged) | `A5` fixes the rows; nothing stops them rotting again | **none yet, and that is the finding.** A gate whose subject is "a doc claims X is unbuilt; is it?" is the `orphan-model-gate` shape inverted, and it would have caught all four. **The shape already exists** — `actor-hub-figures-gate` does exactly this for one track's numbers (see `ASD-7`), measuring what documents CITE and reding on drift. Generalising it to *claims* rather than *figures* is the open work; every one of the four stale rows was a `SELECT` or an `ls` away |
| `AS-S8-UNPARKED-BY-ITS-OWN-GATES` | `S8`'s three stated wake-up conditions are now **all met** (`G-S5a` ✅ · `G-S7b` ✅ · `G-S8b` ✅), so the thing parking it is the PO's build-order call and `S3`/`S4` being undesigned — not the gates it named | **a product decision, and explicitly not an agent's.** `ASD-1` is what happens when an agent decides this by not reading | recorded in three places a reader will hit: the pipeline index §5 (a ⚠ block), `MILESTONE.md`'s `S8` row, and the handoff's DO-NEXT warning |

---

## 5 · DRIFT REGISTER

**An empty drift log is not evidence of a clean run.**

| id | what happened |
|---|---|
| `ASD-1` | **I recommended the gateway route without reading the spec that parks it.** `docs/specs/2026-08-08-user-created-realities.md` is `S8`, parked the day it was written, with the PO's build-order reasoning stated in its own header — and `MILESTONE.md` links it from a row marked 🅿. I had read that row an hour earlier to update a *different* line in the same table. Second occurrence in two days of recommending from memory over the repo (`WSD-1`, `WSD-2`), and the first where it would have built something the PO had explicitly deferred. |
| `ASD-2` | **The thing that saved it was `MILESTONE.md`, which CLAUDE.md says went 2.5 months stale once and warns about by name.** The catch was luck of the draw — the row happened to be four lines from one I was editing. There is no mechanism that would have stopped me building `S8`. |
| `ASD-3` | **A test assertion that passed for a reason that had nothing to do with its subject, and only biting found it.** `every_key_refused_inside_a_verb_row_...` asserted the refusal message names the VERB — `msg.contains("strike")`. With `refuse_authority_keys` deleted, it still passed: `deny_unknown_fields` produced a fallback error, and `toml`'s error rendering **echoes the offending source snippet**, which contains `name = "strike"`. The assertion was satisfied by the document being quoted back at it. Every test was green, the property was unguarded, and the text looked like exactly the right thing to check. Fixed by matching the error **variant** (`LoadError::Verb` vs `LoadError::Parse`) — the two mechanisms are distinguishable by type and indistinguishable by text. This is `NV-4` in its purest form: an adjacent decision, `deny_unknown_fields`, defeating a guard that depended on it. |
| `ASD-4` | **The gate crashed instead of reporting.** Biting the closure's recursion produced `KeyError: 'RowPatch'` — a traceback from the self-test, which is `rc=1` for the right reason with a message nobody can act on. The harness scored it SURVIVED, correctly: `BDR-84` already had a bite harness rejecting tracebacks. A gate whose failure mode is a stack trace teaches authors to ignore it. Fixed with `.get`, so the arm now names itself. |
| `ASD-6` | **I shipped the exact defect this artifact exists to prevent, INSIDE it, and found it by re-reading my own work rather than by any check.** Quoting the engine defaults into the contract created a **third copy** of numbers that already live in `engine_default.toml` and in `Ruleset::engine_default()` — and only those two were compared (`engine_default_matches_the_code`). A hand-maintained copy of a code-derived set, with nothing comparing it, in the file whose whole argument is that such copies drift silently. `RLS-D2` made the artifact authoritative precisely so the values would have one home, and I gave them a third. Fixed with `check_engine_defaults`, both directions and a reach floor; bitten twice. **Nothing would have caught this** — the source gate compares key NAMES, and the behavioural test never reads a default. |
| `ASD-7` | **The sweep went red on a gate I had never heard of, and it was right.** `actor-hub-figures-gate` measures figures that documents CITE and reds when they drift; wiring my gate moved `hook_gate_scripts` 50 → 51 and my four tests moved `rust_tests` 328 → 332, because `ruleset-loader` is in its `CRATES`. Five citations across two documents went stale in one commit, and I would not have known. Worth recording as the counter-example to `ASD-1`/`AS-PIPELINE-INDEX-ROT`: this is precisely the mechanism the pipeline index lacks — a check that compares a number a document states against the thing it names. It exists, it works, and it is scoped to one track's figures. |
| `ASD-5` | **I hand-rolled a YAML reader for the gate and it was wrong within a minute** — a section's `- key:` precedes its `rust_type:`, so every section's name was attributed to the *previous* type and the gate reported seven phantom keys against a correct contract. I had chosen a real parser for exactly this reason one track earlier (`serde_yaml` over a hand scanner, *"a document whose nesting a hand-rolled scanner could silently mis-walk"*) and then did the opposite here, reasoning from `manifest_ids`' four-line reader — which reads a **flat** list. Two gates already import PyYAML. |
