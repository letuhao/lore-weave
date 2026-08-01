# 《寒潭劍錄》 — the POC-1 corpus fixture

The book and reader-built wiki that [doc 39](../../../../../docs/03_planning/LLM_MMO_RPG/39_progression_generation_pipeline.md)'s
progression pipeline is proven against.

> **`PGN-A8` — a fixture that already contains the answers makes every stage vacuous.**
> `NV-1` applied to test *data* rather than to a check. If this wiki contained a complete numbered
> tier ladder, the LLM would transcribe, every gate would approve, every test would pass, and the POC
> would have proven that copying works.

So this corpus is **authored to be answerable-but-incomplete**, the way a real reader wiki is. Every
gap below is deliberate. **Filling one in silently defeats the stage it exists to test** — if you find
yourself "improving" the fixture, you are disarming it.

## What is here

```
book/   the novel — a synopsis + three chapter excerpts.   AUTHORED SOURCE.
wiki/   five reader-built pages about it.                   DERIVED text, by in-world fans.
```

The split matters. `PGN-A14` requires the corpus seal to record `is_authored_source` per chunk,
because `says[]` may cite only authored source — a citation to a *wiki* chunk is a citation to
somebody's summary. Today `book_grounding` stamps every corpus `kind="other"`, which is exactly why
that distinction has to be carried here and not inferred later.

## The three systems

| id | 中文 | `ProgressionType` | `BodyOrSoul` | exercises |
|---|---|---|---|---|
| `internal_energy` | 內功 | `Stage` | Body | realms, sub-levels, breakthrough |
| `swordsmanship` | 劍術 | `Skill` | Body | `derives_from` |
| `comprehension` | 悟性 | `Attribute` | **Soul** | soft cap, the xuyên-không path |

A fourth is **implied and never named** — see R4.

## The teeth — what each gap tests

| # | Requirement | Where it lives | Stage it tests |
|---|---|---|---|
| **R1** | tiers are **named**, and **no magnitude is ever stated as a rule** | `wiki/neigong.md` — five realms, zero numbers | `PGN-A5`: the model may take the names and the order and **nothing else**. Every integer must come from the policy. |
| **R2** | the sub-level **naming pattern** is stated **once** | `wiki/neigong.md` §2 — 每境三重：初重、中重、上重 | The naming owner (`PGN-A0` row 3). One approved answer must expand deterministically to 3 rows per realm — *not* 15 invented names. |
| **R3** | **one contradiction** between two pages | `wiki/neigong.md` says 每境**三**重; `wiki/jianshu.md` cites 凝脈**第五**重 | `PGN-A10` §2.1 — the fold must **refuse and mint a new S2 question** naming both `answer_id`s. Never a silent pick, never a model's. |
| **R4** | **one system implied but never named** | `book/ch11.md` + `wiki/hantan_sect.md` — bronze-coloured skin, blades that do not cut, 打熬筋骨 — presented as *description*, never as a system with realms | Enrichment does real work. `says[]` cannot cover it; a `proposed_text` with **no span** must, and a human must approve it. |
| **R5** | **one flavour detail with no mechanical consequence** | `wiki/hantan_sect.md` §4 — the founder's plum tree, grey robes with a crane, the pool freezing in the eleventh month | The pipeline must be able to **DISCARD**. A pipeline that absorbs everything turns set-dressing into rules. |
| **R6** | **one tier named but never ordered** | 罡元 appears in `wiki/hantan_sect.md` §2 and **nowhere in `neigong.md`'s sequence** | `PGN-A4` + §4.3: `not_stated` on a required, non-defaultable field (`tier_index`) ⇒ an **S5 refusal naming the field**, not a guess and not a silent drop. |
| **R7** | **one training rule that needs a PLACE** | 寒潭 is required to pass 蘊海 (`wiki/neigong.md` §3, `book/ch27.md`) | `PGN-A20` — 閉關 generates `TrainingSource::Time`; 寒潭 → `TrainingCondition::LocationMatch(PlaceTypeRef)` must **refuse by name**, citing the place element module that does not exist. |
| **R8** | **a magnitude trap in narrative form** | `book/ch27.md` — 閉關**三年** | The sharpest `PGN-A5` test in the corpus. *Three years* is a **narrative instance**, not a rule. A pipeline that derives `tier_max` from it has confused *what happened once* with *what is true*. Nothing anywhere says how long a breakthrough takes **in general**. |
| **R9** | `derives_from`, stated plainly | `wiki/wuxing.md` §2 — 悟性高者，劍術一日千里 | The one cross-system edge in scope. |

## What is deliberately NOT here

- **No numbers of any mechanical kind.** No tier caps, no rates, no durations-as-rules, no "X times
  stronger". Search the corpus for digits: what you find is chapter numbers, a month, and R8's trap.
- **No `TrainingRuleDecl` beyond time-driven.** `PGN-Q9` was closed by the PO — training rules cross
  the world-generation pipeline and cannot complete now. R7 exists so the boundary is **exercised as a
  refusal**, not hidden by omission.
- **No completeness.** Two wiki pages carry a `<!-- 待補 -->` marker where a real wiki would. That is
  the corpus telling the truth about itself.

## If a stage passes on this corpus

It has read an incomplete, partly self-contradictory, reader-built wiki about a novel; separated what
the book says from what it does not; refused three things by name; discarded one; and emitted a ladder
whose every integer came from a human-authored policy.

That is POC-1. It is **not** POC-2 — nothing here plays. See doc 39 §0.0.
