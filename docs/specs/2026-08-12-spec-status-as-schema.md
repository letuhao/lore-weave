# Status as schema — stop detecting stale claims, start making them machine-shaped

**Status:** 🟡 **DRAFT — for CLARIFY. Not approved, not started.** Written because
[`CR-PROSE-CLAIMS`](../plans/2026-08-16-claim-rot-RUN-STATE.md) is the one row the claim-rot track
left open with no mechanism, and because **the two obvious mechanisms are already disproven by
measurement** (§2.4). *(This status line uses the very field the document proposes to constrain. If
§3 ships, this line becomes `draft` with no evidence pointer — and if the work ships and this line
still says `draft`, the gate refuses the commit. That is the test I want it to face.)*

**Reconciles:** A gate, lint, test, `const` assertion, validator, or an axiom that constrains code ·
Settings & Configuration Boundary · MCP Tool I/O Standard — the first because §3 proposes a gate and
the whole argument below is about **reach** (`NV-3`); the others because `SET-6` and `IN-2` already
say the same thing this document says about a different field: **a closed set of values must be an
enum, or nothing downstream can rely on it.** What is new here is not the rule, it is the subject: a
*document's* lifecycle field has never been treated as one.

> **This line first also named `Non-Vacuity`, and the gate refused the commit — for the second time,
> in the second document, on the same string.** [`2026-08-15-claim-rot.md`](2026-08-15-claim-rot.md)
> carries a note in its own header saying exactly this: *the standard's name is not a row's first
> cell in the index.* I read that note and wrote the same phantom reference anyway. There is no row
> whose first cell contains "vacu"; the index reaches the standard only through the concern row cited
> above. **A document about claims that do not resolve, opening for the second time with a claim that
> did not resolve** — and both times the only thing that noticed was the gate.

---

## 1 · The defect

A document states its own lifecycle — *"DRAFT, not started"*, *"Cycle 0 scaffold"*, *"blocked"* — and
that statement is a claim about the world that nothing compares to the world. The work ships; the
line does not move; the next reader believes it. Measured lifetimes in this repo: **three weeks** for
a spec whose build board reads ALL CLEARED, and **months** for a README describing a crate with eight
binaries as *"empty-compiling, no behavior"*.

The claim-rot track ([`e66eb7d9d`](../plans/2026-08-16-claim-rot-RUN-STATE.md)) fixed the **figure**
half of this: numbers in a marker-delimited window, measured on every commit. It fixed nothing for
prose, and said so.

---

## 2 · Phase 0 — measured, and the measurement is not friendly to §3

### 2.1 · The corpus

| fact | value | command |
|---|---|---|
| spec files | **532** | `ls docs/specs/**/*.md` |
| cited by a board (`docs/plans`, `docs/sessions`) | **386** (72%) | stem match across 548 board files |
| …of those, carrying a `Status:` line | **77** | `grep -lP '^\*\*Status'` over the cited set |
| …carrying none | **309** | the remainder |
| not cited by any board | **146** | the complement |

**72% is not a narrow scope.** The predicate *"cited by a board"* was chosen because it is computed
rather than enumerated — it is not `NV-3` — but it is also not small, and a 386-file retrofit is a
different proposition from the one that word "narrow" suggests.

### 2.2 · The one cut that IS narrow

**No status line is no claim, and no claim cannot rot.** The defect requires an assertion. So the
subject of the *defect* is the **77** specs that assert something, not the 386 that are cited. Making
the other 309 declare a status is a **completeness** policy — a real and separable decision, with its
own cost and its own failure mode (inventing a status for a document nobody owns is itself a claim
that can be wrong).

That splits the work in two, and only the first is this defect:

* **Rule A** — a spec that HAS a status must use the closed set and carry its evidence pointer. **77 files.**
* **Rule B** — every board-cited spec MUST have a status. **309 files.** Separate question, §4.

### 2.3 · Vocabulary: there is no closed set today

Across the 77, roughly **25** distinct spellings: `DESIGN`, `DESIGN COMPLETE`, `DESIGN LOCKED`,
`DRAFT`, `CLARIFY`, `SHIPPED`, `DONE`, `BUILT`, `CLOSED`, `FIXED`, `PARKED`, `DEFERRED`, `BLOCKED`,
`DECIDED`, `INVESTIGATION COMPLETE`, `MEASURED`, `BASELINE`, `METHODOLOGY`, `INDEX`, `PLAN`, `SPEC` …

Nothing can key on a field with 25 spellings and 455 absences. This is exactly `SET-6` and the
Frontend-Tool-Contract's *closed-set arg ⇒ `enum`*, applied to a field nobody thought of as an arg.

### 2.4 · Two mechanisms, both already disproven — do not re-propose them

| mechanism | verdict | evidence |
|---|---|---|
| Match lifecycle claims in prose and verify each | **rejected** | [`2026-08-15-claim-rot.md`](2026-08-15-claim-rot.md) §2.2: **197** documents make a claim of this shape, dominated by hypotheticals, past states and quoted error text (*"SQL `column does not exist`"*). A real finding would be buried in false positives |
| Compare a declared status against the git history of commits naming the spec | **rejected** | Built and run 2026-08-12: **1 hit across 260 top-level specs**, and it reaches only **56 of 260 (21%)** — commit messages rarely name a spec file. **204 default-uncovered**, which is `NV-3` by construction: it would report *clean* over a corpus it never opened |

The second one is the reason this document exists. It found a genuine instance
([`2026-07-20-book-structure-pipeline.md`](2026-07-20-book-structure-pipeline.md), stale three weeks,
fixed in `903d153c8`) — and it found it at 21% reach, which means the honest reading is *"there are
probably more and this cannot see them"*, not *"the corpus is clean"*.

### 2.5 · ⚠️ THE LOAD-BEARING NUMBER — coverage against the instances we actually have

Thirteen instances of claim rot are on record. **§3 addresses two of them.**

| # | instance | where it lives | §3 catches it? |
|---|---|---|---|
| 1 | measured-state `world-service` row | run-state table | figures half only (`e66eb7d9d`) |
| 2 | measured-state reality count | run-state table | ✅ already, by the shipped gate |
| 3–6 | pipeline index `G-S7a`/`G-S7b`/`G-S8a`/`G-S8b` — *"zero realities have ever existed"* | board prose | ❌ |
| 7 | `services/world-service/README.md` — *"Cycle 0 scaffold, no behavior"*, months | README prose | ❌ |
| 8 | the pgvector compose comment, stale from the hour it shipped | code comment | ❌ |
| 9 | `CR3`'s own `done=` cell — *"four reasons"* against six | board table cell | ❌ |
| 10 | `SESSION_HANDOFF` — *"every mutation reds its gate's self-test"*, actually 82/83 | handoff prose | ❌ |
| 11 | `CLAIM-ROT` left in the OPEN table after it was discharged | board row state | ❌ (but see §4 Q3) |
| 12 | `2026-08-15-claim-rot.md` — *"not approved, not started"* after shipping | **spec status** | ✅ |
| 13 | `2026-07-20-book-structure-pipeline.md` — *"DRAFT v2"*, three weeks | **spec status** | ✅ |

**2 of 13.** The majority of measured rot lives in **boards, READMEs and code comments**, not in spec
status lines. A mechanism that fixes 2/13 may still be worth its cost — the two it fixes are cheap to
fix and the field is genuinely unstructured — but **it must not be presented as closing
`CR-PROSE-CLAIMS`**, and the claim-rot board must not be allowed to record it as such. That is the
mistake this repo has made before: an instance fix with no detector, filed as a class fix.

---

## 3 · What is proposed

**Rule A.** A spec carrying a `Status:` line must express it as a closed-set token plus, for any
terminal state, an **evidence pointer that resolves**:

```markdown
**Status:** `shipped` — `e66eb7d9d`
**Status:** `superseded` — [`2026-08-16-claim-rot-RUN-STATE.md`](../plans/2026-08-16-claim-rot-RUN-STATE.md)
**Status:** `draft`
**Status:** `parked` — reason required, in the same line
```

Proposed set (§4 Q1 challenges it): `draft` · `clarify` · `approved` · `building` · `shipped` ·
`superseded` · `parked` · `wont-fix`.

The gate then does three things, none of which is prose matching:

1. **the token is in the set** — otherwise there is no field, only text;
2. **a terminal state carries a pointer, and the pointer RESOLVES** — a sha that exists, a path that
   exists. `citation-gate` already does path resolution and is the precedent to reuse;
3. **`draft`/`clarify` with a resolving `shipped-as` sha anywhere in the document is a contradiction**
   — the narrow, high-signal version of the disproven §2.4 check, keyed on a field instead of on prose.

**Non-vacuity obligations, stated up front** (`NV-1..6`, and this document will be held to them):

* the scope must be a **predicate over the tree**, never a file list — an enumerated allowlist here is
  `NV-3` and the whole §2.4 table is about reach;
* **reach floors** — the gate must assert `0 < floor < measured` for the number of status lines it
  parsed, or a rename of the `Status:` marker silently reduces it to a clean-tree no-op;
* **bite it six ways** before it is believed, including the arm where the marker moves.

**Rule B** (every board-cited spec must have a status) is **not proposed here.** It is §4 Q2.

---

## 4 · Open questions for CLARIFY — this is a draft because of these

**Q1 — is 2-of-13 worth a gate at all?** The honest alternatives are (a) build Rule A, cheap and
narrow, and leave 11/13 uncovered with that written down; (b) record `CR-PROSE-CLAIMS` as a conscious
won't-fix with §2.4 and §2.5 attached; (c) go after the majority instead — board rows and READMEs —
which is a **larger** problem with **no** disproof yet, only the 197-document false-positive
measurement that killed the naive version. **My reading: (a), on the condition that §2.5 is copied
into the board so nobody records it as closing the row.** But this is the PO's call, and the last
claim-rot spec was overturned by its own Phase 0 — so it should be treated as a question, not a lean.

**Q2 — Rule B, the 309?** Requiring a status everywhere buys uniformity and costs a 309-file sweep in
which a wrong status is a new false claim. Skipping it means the gate is silent on any spec that
simply omits the field — which is the escape hatch, and it is one keystroke wide.

**Q3 — should boards be in scope, given they hold instances 3, 9, 10 and 11?** A run-state row's state
(`open` / `cleared`) is arguably the *same* field with the same closed set, and instance 11 is exactly
that. This may be the higher-value half, and it is not costed here at all.

**Q4 — who owns the retrofit, and does it happen in one commit or as-touched?** As-touched is
`NV-3` again: the untouched files are default-uncovered, and instance 13 sat untouched for three weeks.

**Q5 — does the evidence pointer have to be *correct*, or merely *resolve*?** A `shipped` status
pointing at a real sha that implemented something else is a claim this gate would certify. Resolution
is checkable; correctness is not. Say so in the doc rather than implying more.

---

## 5 · What this does not fix

It does not read prose, and 11 of the 13 measured instances are prose. It does not know whether a
`shipped` sha shipped *this*. And it does nothing for the two instances with the longest measured
lifetimes — a README and a Dockerfile comment — because neither has a status field and inventing one
for every file in the tree is not a proposal, it is a wish.

**The scope this genuinely converts is narrow and should be stated as such:** *"a spec's own lifecycle
line is a field with a closed set and a resolving pointer, instead of a sentence nobody re-reads."*
