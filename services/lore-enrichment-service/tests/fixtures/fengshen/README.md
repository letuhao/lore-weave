# 《封神演義》 — the ITEM corpus fixture

The source the **item** half of the contract pool is proven against —
[`40.6`](../../../../../docs/03_planning/LLM_MMO_RPG/40_progression_planner/06_item_contract.md) (what
item registers) and
[`40.8`](../../../../../docs/03_planning/LLM_MMO_RPG/40_progression_planner/08_retrieval_and_enrichment.md)
(how it finds and enriches).

Sibling of [`../wuxia/`](../wuxia/README.md), which does the same job for progression. Same discipline,
different subject.

## Why this book

Fengshen Yanyi is very likely the most **treasure-dense** classical Chinese novel that exists — hundreds
of named 法寶 driving the plot, offensive, defensive, sealing and auxiliary. That density is the point,
and not because it makes the fixture easy:

> **Retrieval has a great deal to find here, which is exactly what makes the things it CANNOT find a
> fair test of enrichment.**

The PO's framing, which this corpus is shaped to: *find-and-load only works for the unique items the
story actually names. Everything else — grades, slots, categories, stats — has to come from genre
knowledge and the author's own ideas. That is the enrichment step.* A corpus where retrieval always
succeeds would prove nothing about the half of the pipeline that matters.

## Authorship — read this before citing anything

- The **characters, treasures, owners and events are real facts** about the Ming novel, checked against
  Baidu Baike's 封神法宝 entry and the English Wikipedia article.
- The **prose is fixture-authored in the style of the novel.** It is **not verbatim Ming text** and must
  never be quoted as such.

Written this way deliberately: the teeth below have to sit in exact places, and a real chapter cannot be
edited to carry a designed gap. The wuxia fixture solved the same problem by inventing its book outright;
here the *facts* are worth keeping real because the enrichment step is partly a test of whether genre
knowledge and source knowledge agree.

## What is here

```
book/   synopsis + three chapter excerpts.   AUTHORED SOURCE — says[] may cite these.
wiki/   four reader-built pages.             DERIVED — a citation here is a citation to a summary.
```

`PGN-A14` requires the seal to record `is_authored_source` per chunk. The flags live in
[`fixture_teeth.json`](fixture_teeth.json), **outside the corpus**, for the reason that file explains at
length: metadata about a test must never live inside the thing under test.

## The four planner kinds, one corpus

[`40.7` `MOD-A1`](../../../../../docs/03_planning/LLM_MMO_RPG/40_progression_planner/07_module_organisation.md)
says there are four planner kinds and item needs one of each. This corpus exercises all four, and gives
each a **different** outcome on purpose:

| slot | kind | what this corpus does to it |
|---|---|---|
| `item_archetype` | `Composite` | **retrieval succeeds** — dozens of named treasures with stated function |
| `instrument_tag` | `Enumeration` | **partial** — a reader wiki groups them, but says the grouping is its own, not the book's |
| `item_grade` | `Ladder` | **fully enriched** — the book *states* that no ranking exists (I2) |
| `equip_slot` | `Profile` | **accept the default** — silence, and silence is not an override (I4) |

Four kinds, four different verdicts, one run. That is the pattern claim in
[`40.7` §7](../../../../../docs/03_planning/LLM_MMO_RPG/40_progression_planner/07_module_organisation.md)
being put where it can fail.

## The teeth, in one line each

Full statements, with the exact strings and the reasoning, in
[`fixture_teeth.json`](fixture_teeth.json). Twelve:

| # | what it tests |
|---|---|
| **I1** | retrieval finds the named uniques richly — the easy half, and it must be easy |
| **I2** | **the sharpest one.** The corpus says out loud that treasures have no ranking. A game needs grades anyway ⇒ rung-4 genre convention from an authored pack, labelled, never invented |
| **I3** | the tag grouping exists only in a *wiki* page — so `says[]` may not cite it (`PGN-A14`) |
| **I4** | no equipment-slot concept anywhere ⇒ **accept the engine default**. Silence is not an override |
| **I5** | three treasures named with no properties, and the text says so |
| **I6** | one page carries two accounts of 杏黃旗's origin and cannot decide ⇒ refuse, do not pick |
| **I7** | a cardinality and a magnitude sitting next to each other — 二十四顆 is legal, 長七尺 is a trap |
| **I8** | colour and family drama must be **discarded** |
| **I9** | 封神榜 is a `Document`, and the corpus says *此非兵器，乃名冊也* twice |
| **I10** | mounts are **not** items (`PL_007` §5.2 → `TVL_003`) ⇒ refuse by name |
| **I11** | 九龍神火罩 traps, *then* fire — item effect or the wielder's art? Refuse, naming both |
| **I12** | 打神鞭 only works on actors listed on 封神榜 ⇒ a **dangling cross-module reference** (`EPL-A8`) |

**I2, I10 and I12 are the three worth running first.** I2 is the whole enrichment argument; I10 is the
module-boundary argument; I12 is the only tooth that can prove `EPL-A8`, which has no prior art anywhere
in this repo.

## If you are tempted to improve this corpus

Don't. Every gap is deliberate and filling one silently disarms the stage it exists to test — the
wuxia fixture's README says the same thing for the same reason. Add a tooth if you must; never remove
one by helpfulness.

## What passing does NOT prove

That the generated items are any good to play with. This is the **contract** half — taxonomy and
classification. Whether a world built from these lists is playable is `PPL-A2`'s question, and nothing
here answers it.
