# Plan — Quantity architecture spec + corpus corrections (2026-07-28)

**Size:** L (files=8, logic=9, side_effects=0) · **Type:** `[BE]` design/spec only, no code
**Trigger (PO):** *"dừng build và update spec, lấy điểm mạnh của chaos vào spec của chúng ta và loại
điểm yếu của nó"* — after three turns of audit established that LoreWeave's quantity model has no
layer beneath its closed derived set.

---

## 1. Goal

Answer two requirements that pull against each other, by putting them on different layers:

1. *"Kiến trúc mới có thể implement toàn bộ [7 progression systems] mà không phải đập đi xây lại?"*
2. *"Derived stats vẫn phải hard code … nhưng chúng phải có khả năng mở rộng."*

**Deliverable:** `docs/03_planning/LLM_MMO_RPG/35_quantity_architecture.md` (`QTY-A1..A12`,
`QTY-D1..D8`, `QTY-Q1..Q4`) plus the corpus corrections it forces.

**No code in this run.** The build order lives in 35 §12 and starts at `Q0`.

---

## 2. Evidence base

Four cold-start sub-agent audits, 2026-07-28. Every claim in doc 35 carries a `path:line`.

| Audit | Corpus | Load-bearing output |
|---|---|---|
| A | `chaos-actor-module` + `chaos-backend-service/crates/actor-core` | derived is never computed (`aggregator/mod.rs:253`); determinism broken; the god-class diagnosis quote |
| B | `chaos-backend-service/crates/element-core` | config→registry→ordinal→dense array pattern; `sort()` renumbering defect; no persistence |
| C | this repo's `ruleset-core` / `ruleset-loader` / `commit-service` | 20 authorable knobs, **all numbers**; no `progression_kind` in code; zero elements; the 13-site blast radius |
| D | adversarial, over the design corpus | **refuted 3 of 4 planks** of the position doc 35 replaces (see §4) |

A follow-up pair (re-run with the corrected frame: *judge the architecture, not the completeness of a
paused rebuild*) produced the hierarchical-actor pattern and the closed/open boundary that doc 35 §7
takes from.

---

## 3. Scope

**In:**
- New spec `35_quantity_architecture.md` — the four layers, `QTY-A3` (laws bind to **roles**), the L1
  growth story (`QTY-A10/A11`: additive vs behavioural; length-declared canon + upcast + epoch switch).
- 7 named strengths taken from chaos with citations; 7 named weaknesses refused with the site where
  each bit.
- Four corpus corrections (§4).
- Register `QTY` in `00_foundation/06_id_catalog.md`.
- Extend `IMP-D9`'s hold to cover `stat_archetypes` / templates / F3, and insert `Q0` ahead of `W1`.

**Out (deliberate):**
- Any code. `Q0` is the first code slice and is not this run.
- Re-running the §9.4 benchmark with a committed harness — named as `Q0`'s companion task; doing it
  here would be scope creep and it does not change any decision in doc 35 (see §4.3).
- Resolving `QTY-Q1..Q4`. They are open by design; `Q4` (shared registry vs duplicated scaffolding) in
  particular must be a conscious call, not a drift.

---

## 4. The corrections (why the corpus could not be left alone)

These are **factual errors in sealed documents** that were cited as load-bearing evidence — including
by me, one turn earlier. Left in place they would mislead the next reader the same way.

1. **`27 §6` convergence #2 misattributed** to *immersive · cultivation · ARPG*. Raw reports show one
   genuine source; **cultivation and ARPG wrote the opposite** (`27a:730,747` / `27a:274,349`).
   → `27 §6.1` added with a per-agent table, and the surviving reading recorded: cultivation objected
   to open *slots* while proposing open *pool identity* (`27a:739`), which is exactly `QTY-A3`.
2. **`27 §9.4`'s re-measurement is unverified** — *"probe file written, run, then deleted"*
   (`27a:782`); no harness in the repo. → marked UNVERIFIED, may not overturn a locked decision.
3. **"The 88× justification was wrong" is itself wrong** — 88× compares closed-array vs `HashMap`;
   1.08× compares closed-array vs *interned-ordinal array*. Different competitors, not in tension.
   → corrected in `26 §1`'s banner and `27 §9.4`.
4. **`XST-R6` / `WSA-R02` propose the wrong fix** — the laws read **9 of 10** slots by name, so an
   "open tail" of slots is one dead slot. → R6 **retired** (`QTY-D4`), R02 **mechanism revised,
   finding preserved** (`QTY-D5`), `DF7-A1` **upheld and scoped** (`QTY-D6`).

---

## 5. Files

| # | File | Change |
|---|---|---|
| 1 | `docs/03_planning/LLM_MMO_RPG/35_quantity_architecture.md` | **NEW** — the spec |
| 2 | `.../26_implementation_architecture.md` | §1 banner corrected (`QTY-D7`); `IMP-D9` hold extended to `Q0` |
| 3 | `.../27_extensibility_stress_test.md` | §6 row flagged + **§6.1 new**; `XST-R6` retired; §9.4 UNVERIFIED banner |
| 4 | `.../31_world_simulation_architecture.md` | `WSA-R02` revised; `WSA-A6` re-based off the retired R6; layer-name collision noted; `Q0` inserted before `W1` |
| 5 | `.../features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md` | `DF7-A1` amended — upheld, scoped to L1, given a bounded-growth obligation |
| 6 | `.../00_foundation/06_id_catalog.md` | `QTY-*` registered |
| 7 | `.../SESSION_HANDOFF.md` | ▶ NEXT block |
| 8 | `docs/plans/2026-07-28-quantity-architecture-spec.md` | this file |

---

## 6. Acceptance

- [ ] Every strength claimed of chaos carries a `path:line` into the chaos repo; every weakness
      refused carries the site where it bit.
- [ ] `DF7-A1` is **upheld**, not overturned — the closed derived set survives, and the amendment says
      what it is closed *over*.
- [ ] The growth story is concrete enough to build: named artifacts (`B1`/`D1` → `B2`/`D2`), a named
      event (epoch switch), and a stated invariant it preserves (RLS-A3 / RLS-D18).
- [ ] Every retired/revised item points forward to its replacement, and every replacement points back.
- [ ] `design-lint` + all repo gates green; no dead cross-doc links.

## 7. Risks

| Risk | Mitigation |
|---|---|
| `QTY-A3` (roles) is new and untested against the full law set | reduced to ONE role (`Vital`) on cardinality grounds; `Q2` proves it by binding `Vital → qi` with the defeat law unchanged |
| Layer-name collision: WSA "L1" ≠ QTY "L1" | called out inline at `31 §2` and in doc 35 §3 |
| A spec with no consumer is the anti-pattern this repo already punishes | 35 §12 is a build order whose first slices are gates and one branch, not an open-ended backlog. §8 below is the direct answer |
| The corrections touch SEALED documents | none is a re-litigation from memory — each cites the raw report line that contradicts the sealed text, per the SEALED rule's own *"re-read it"* clause |

---

## 8. Red-team round — same day, and it reversed a core axiom

Four adversarial agents (performance · multiverse · gameplay extension · the four open questions),
over four mostly-disjoint corpora. **Two findings were raised independently by three of the four**,
which is why they were treated as settled rather than debated further.

**Reversed:** `QTY-A6` (per-reality array width) — mutually exclusive with `QTY-A12`, probably
unimplementable given the monomorphic island manager, and its benefit is a rounding error at our
measured struct sizes (`Actor` 192 B → ≈408 B at a fixed `[i32;64]`; 10 k actors = +2.2 MB). Replaced
by fixed compile-time width + declared identities inside it + **`QTY-A6.1` (`O(n)` per actor,
`O(n²)` per ruleset)** — the scoping rule the first draft omitted, which was chaos's actual mistake.

**Corrected:** `QTY-A11` refused this document's own `Q2` (a slot *removal*) → `QTY-A10(c)`, and `Q2`
no longer removes anything.

**Added:** `QTY-A13` (a source contributes, never declares) · `QTY-A14` (an ordinal never travels
without its digest) · `QTY-D9` (tenancy — the draft had zero occurrences of owner/user/scope key) ·
`QTY-D11` (adopt `XST-R7`) · `QTY-D13` (checkpoint boundary + `LAW_VERSION`) · §6.5 (the seven systems
finally walked) · §5.5 (nouns here, verbs at `WSA-R18`).

**Closed:** all four open questions → `QTY-D12`/`D13` + §13.1. Seven new ones opened (`QTY-Q5..Q11`),
including the honest one nobody had written down: *will more than one team author genuinely different
quantity sets? QTY earns its cost only if yes.*

**Recorded against myself:** three miscitations (`recovery.rs`, `PROG_001:83`'s `f32`, and claiming the
doc leaned on `XST-R7` when it contained no reference to it). A wrong citation in a sealed document is
exactly how the *previous* round's errors happened, so they are logged in doc 35 §10.6 rather than
quietly fixed.

**New tracked defect, live in code and independent of this spec:** `D-PUBLISHER-DROPS-RULESET-PIN` —
`services/publisher/pkg/pgsource/pgsource.go:56-72` does not SELECT `ruleset_digest` while
`contracts/events/envelope.go:57` is `omitempty`, so the pin vanishes the moment an event leaves its
reality DB. Must be fixed before `Q1`.
