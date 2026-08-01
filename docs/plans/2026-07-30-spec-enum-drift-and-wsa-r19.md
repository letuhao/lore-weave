# Plan — finish `WSA-R19`, correct three stale statuses, and close the spec-only-enum gap

> **Date:** 2026-07-30 · **Size:** L (files=11, logic=10, side_effects=3) · **Track:** LLM_MMO_RPG
> **Predecessor:** `63d122b36` — which deferred exactly this item, on the grounds that it is a seam
> across three features needing its own boundary review. That reasoning held; what did **not** hold is
> the assumption that the work had not started.

---

## 0 — What opening the targets found (and it is not what any register says)

`63d122b36`'s release note said `SPG-R10` + `WSA-R19`/`R21`/`R22` were *"NOT applied — deferred to its own
claim, on purpose"*, citing `EF_001:67`/`:131` as **self-consistent and honest**. Both halves were wrong:

| Row | Register says | Target actually says | Truth |
|---|---|---|---|
| `WSA-R19` | doc 32:14 — *"still PROPOSED, not applied"* | `EF_001:352` — `EntityId { …, Place(PlaceId) }` | **HALF-APPLIED** |
| `WSA-R21` | doc 32:14 — *"still PROPOSED"* | `NPC_001_cast:67` — *"`Locus` **ADDED** 2026-07-30 (`WSA-R21`; boundary review + lock claim)"* | **APPLIED** |
| `WSA-R22` | doc 32:14 — *"still PROPOSED"* | `ACT_001:205` — *"Out-of-world actors forbidden V1 (ACT-A7) — **NARROWED** 2026-07-30 (`WSA-R22`)"* | **APPLIED** |

So doc 32:14 is a **blanket status claim that is false for three of the six rows it covers**, and my own
release note repeated it because I checked `EF_001:67` (which is stale) instead of `EF_001:352` (which is
current). Reading the *table* rather than the *code* is the same error one layer down.

### `WSA-R19` is the THIRD half-application of this arc

`EF_001` §5 carries the applied change; **four** statements around it still describe the old shape:

| Site | Says | Should say |
|---|---|---|
| `:67` domain-concepts table | *"Closed sum type — `Pc \| Npc \| Item \| EnvObject`"*, *"**4 variants V1**"* | 5, incl. `Place(PlaceId)` |
| `:131` doc-comment | *"cells are **not** `EntityId`s today"* | they are, as of `WSA-R19` |
| `:340` exhaustiveness rationale | *"forces every consumer to handle all **4** variants"* | 5 |
| `:357+` variant table | no `Place` row | a `Place` row with its reason |

Prior instances: `SPG-R1` (`ChannelTier`, ~70 sites, [REC-97](../03_planning/LLM_MMO_RPG/19_reconciliation_register.md))
and the `SPG-R1`/`R3`/`R5` "Applied so far" claim. **Three occurrences means the response is a mechanism,
not a third careful sweep.**

---

## 1 — The mechanism: `design-lint` covers SPEC-ONLY enums

### The gap, in the check's own words

`design-lint.py`'s `count` check compares *"N variants of `X`"* claims against the real Rust enum, and
states its limit explicitly:

> *"**KNOWN LIMIT:** it can only check enums that EXIST in code. `EffectOp` is spec-only, which is
> precisely why nobody could settle 9 vs 11 — this check will start covering it the day ABL_001 is
> implemented, and not before."*

`EntityId` is spec-only. So the *"4 variants V1"* claim sat next to a 5-variant declaration **in the same
file** with nothing able to look. Documenting a hole is not covering it — the repo's own phrase.

### The fix

Parse enums out of fenced ` ```rust ` blocks **in the markdown corpus itself**, and use them as a
second source for the same `count` check:

```
count-drift  claim "N variants of X"  vs  Rust enum in crates//services/    (existing)
                                     vs  enum declared in a corpus code block  (NEW)
spec-enum-drift  the SAME enum declared in 2+ docs with DIFFERENT arity        (NEW)
```

Both reuse `closed-set-gate.parse_enums` + `strip_comments`, exactly as `rust_enum_arities` already does,
so the three checks cannot disagree about what a variant is. **This matters here specifically**:
`MAP_001` carries a *struck-through, commented-out* `ChannelTier` block, and a parser that counted it
would produce a phantom enum. The comment stripper is what makes that safe, and it is bite-tested.

### Precision guards (the `count` check's own lesson, applied)

`count` spent its first life as INFO-only because a loose matcher produced ~8 parse errors in 11
findings. So the new source is deliberately narrow:

1. **Skip elided blocks.** A body containing `...`, `…`, or a `// …` placeholder is illustrative, not a
   declaration. Counting it would contradict a correct claim with a partial sample.
2. **Code wins over corpus.** If the enum exists in Rust, the Rust arity is authoritative and the corpus
   declaration is ignored for `count` — the code is the thing that ships.
3. **Cross-doc drift is its own finding kind**, so a real disagreement between two docs is not reported
   as "the claim is wrong" when the question is which doc is right.

### Bite-test obligations (NV-2), all four

- change a *"N variants"* claim next to a corpus-declared enum → `count-drift` reds;
- declare the same enum with different arity in two docs → `spec-enum-drift` reds;
- put `...` in the body → **no** finding (the elision guard, which would otherwise cry wolf);
- comment out an enum → **no** phantom (the `ChannelTier` case, which exists in the tree today).

---

## 1b — Design review (Lead self-review) — the cross-doc half is cut

### `RD-1` — `spec-enum-drift` across docs would fire a FALSE POSITIVE on its first run ⛔ cut

Three docs declare `pub enum ActorId`, and **two of them are legitimately different types**:

```rust
// 06_data_plane/17_channel_lifecycle.md:243 — the DATA PLANE's ActorId
pub enum ActorId { Player { player_id, session_id }, Npc { npc_id } }        // 2 variants

// EF_001 §5.1 / NPC_001 §2 — the FEATURE layer's ActorId
pub enum ActorId { Pc, Npc, Synthetic{kind}, Admin, Locus(PlaceId) }         // 5 variants
```

Both are correct. It is the same `DP-A13` boundary this arc has now met three times: the data plane
keeps its own vocabulary and the feature layer keeps another. A cross-doc arity comparison would call
that drift on its very first run — and the `count` check's own recorded history is that a lint which
cries wolf **gets switched off**, which is how it spent its first life as INFO-only. Shipping a new
check with a known false positive would repeat that exactly.

**Revised scope: PER-FILE.** When checking a claim in file `F`, use an enum declared **in `F` itself**.
That is precisely the `EF_001` defect — *"4 variants V1"* at `:67` against a 5-variant declaration at
`:352`, one file, no ambiguity about which is authoritative — and it has **no homonym problem at all**,
because two files never meet.

### `RD-2` — "code wins over corpus" discards signal, but chasing it now adds noise ⚠ deferred

If a doc declares an enum that *also* exists in Rust and the arities differ, that is real spec-vs-code
drift. But corpus blocks are frequently **abbreviated on purpose** without an ellipsis to mark it, so
comparing them wholesale would generate exactly the noise `RD-1` is avoiding. Left out of this pass and
recorded as `D-SPEC-CODE-ENUM-PARITY`, with the `ActorId` evidence above as the reason a naive version
does not work.

### `RD-3` — the elision guard must be bite-tested for a NON-finding

Easy to write a guard and never prove it guards. The bite-test list therefore includes two cases that
must produce **no** finding (elided body, commented-out block) alongside the one that must red. A guard
proven only by its absence of complaints is not proven.

---

## 2 — Steps

| # | Change | File |
|---|---|---|
| 1 | `count` gains a corpus-code-block source; new `spec-enum-drift` kind; elision + comment guards | `scripts/design-lint.py` |
| 2 | Bite-test all four behaviours; paste output | — |
| 3 | Finish `WSA-R19`: `:67`, `:131`, `:340`, `:357+` variant table | `EF_001` |
| 4 | Correct doc 32:14's blanket status; mark `R19`/`R21`/`R22` **APPLIED** with file:line evidence | `32_locus_as_actor.md` |
| 5 | Apply `SPG-R10` — state that `SpaceNode.holder: Option<EntityId>` resolves to `EntityId::Place` for a locus, which is the seam `SPG-A1`/`WSA-A7` approach from two sides | `36_map_architecture.md`, `EF_001` |
| 6 | `REC-98` — the third instance, and why the answer is a lint rather than a sweep | `19_reconciliation_register.md` |
| 7 | Boundary claim for the `EntityId` variant registration if the matrix lacks it | `_boundaries/*` |
| 8 | Correct `63d122b36`'s release note in `_LOCK.md` — it asserted these were unapplied | `_boundaries/_LOCK.md` |

## 3 — Risks

| Risk | Handling |
|---|---|
| The new parser produces phantom enums from prose/commented blocks | Reuse `strip_comments`; bite-test the real `ChannelTier` case |
| It cries wolf on illustrative blocks and gets switched off — the `count` check's actual history | Elision guard, bite-tested for a NON-finding |
| `EF_001` is CANDIDATE-LOCK | The variant already landed in §5; this pass makes the rest of the file agree. Lock claim if `_boundaries/` needs a row |
| Correcting my own release note reads as churn | It asserted something false about the tree; leaving it is how `63d122b36` becomes the next stale register |
