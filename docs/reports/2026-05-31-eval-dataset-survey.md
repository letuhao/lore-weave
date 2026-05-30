# Eval Dataset Survey — public literary extraction datasets (cycle 74e)

**Date:** 2026-05-31 · **Context:** the gold set is self-built + self-adjudicated
(9 chapters), which risks **annotation bias / circularity** (we annotate to what our
own extractor/prompt expects). This survey assesses public, independently-annotated
datasets as bias-reducing anchors, per the user's concern. Scope: the 3 most-relevant
candidates surfaced — LitBank (en), Chinese-Literature-NER-RE (zh), NCRE (zh wuxia).

Our target schema (what any dataset must map to): **entities** = 6 kinds
`person·place·organization·artifact·concept·other`; **relations** = 28 predicates in 6
categories `Kinship·Mentorship·Authority·Spatial·Action·Social`; **events** =
`summary + participants` (+ kind enum); plus a deliberate "scene-relevance omission" rule.

## Verdict at a glance

| Dataset | Lang | License | Best for | Drop-in? | Mapping cost |
|---|---|---|---|---|---|
| **LitBank** | en | **CC-BY 4.0** ✓ | **Entities (independent anchor)** + coref/quotes | Entities: near-yes | Low (entities) / High (events) |
| **Chinese-Lit-NER-RE** (lancopku) | zh (modern prose) | **none stated** ⚠️ | Modern-zh entities + coarse relations | No | Medium (coarse relations) |
| **NCRE** (LimboChen, NLPCC2025) | zh (wuxia) | **none + source copyrighted** ⚠️⚠️ | **Relation TAXONOMY reference** | No (different task + copyright) | N/A (schema reference only) |

**Headline:** LitBank is a clean, immediately-usable **independent entity anchor for English**
— exactly the bias antidote we wanted. **Relations have no drop-in public gold** in our
format+domain+license: lancopku is coarse + unlicensed + modern register; NCRE has a near-perfect
taxonomy but a different task shape, no license, and is built on still-copyrighted Jin Yong novels.
So our **fine 28-predicate relation gold stays self-built** — now an *informed* decision, with
bias reduced by (a) the independent LitBank entity anchor, (b) cross-checking our predicate vocab
against NCRE's, (c) multi-drafter source-grounded adjudication. Vietnamese + classical-zh register
remain gaps only self-built (or a follow-up WYWEB/C-CLUE survey) can fill.

## 1 · LitBank — github.com/dbamman/litbank

- **License:** Creative Commons Attribution 4.0 (CC-BY 4.0) — usable + redistributable with attribution. **Cleanest of the three.**
- **Size / lang:** 100 English fiction works, ~210,532 tokens (~2K words each). English only.
- **Layers:** entities (6 ACE types, **nested** + common nouns) · **events** (realis only) · coreference · quotation attribution.
- **Format:** Brat standoff + tab-separated layered; dirs `entities/ events/ coref/ quotations/ original/`.
- **Relations:** **none** (no relation triples — only coreference).

**Entity mapping → our 6 kinds (LOW cost):**

| LitBank | → our kind | Note |
|---|---|---|
| PER (people) | person | clean |
| ORG (army, Church) | organization | clean |
| FAC (house, kitchen) | place | 3→1 collapse |
| GPE (London, village) | place | 3→1 collapse |
| LOC (forest, river) | place | 3→1 collapse |
| VEH (ship, car) | artifact | partial (we'd map vehicles→artifact) |
| — | concept | **gap**: LitBank has no abstract-concept type |
| — | artifact (non-vehicle) | **gap**: only vehicles are object-like in LitBank |

Verdict: **excellent independent entity anchor for en.** The only loss is that our finer
`place` vs `organization` vs `artifact` lines differ from ACE, and our `concept` has no
LitBank equivalent. Both are tolerable for an *anchor* (informational/external-validity), not
a 1:1 gate.

**Events:** LitBank tags **single event-trigger tokens** (realis). Ours are **summaries +
participants**. Granularity mismatch → **high mapping cost**; usable as an informational
realis-event anchor, not drop-in. (Note: LitBank's realis-only philosophy *matches* our
"only events that actually happen" stance — conceptually aligned, structurally different.)

## 2 · Chinese-Literature-NER-RE — github.com/lancopku (arXiv 1711.07010)

- **License:** **none stated** (no LICENSE file). Research use likely tolerated; redistribution into our repo is risky — do not bundle without clarifying.
- **Size:** 726 articles, 29,096 sentences, >1M chars (300 person-hours / 5 annotators).
- **Lang/genre:** **modern** Chinese literature prose (essays/short pieces from a website) — **NOT** the classical/vernacular register of our 西遊記/三國/紅樓夢 fixtures.
- **Format:** Brat-style — `T` tags (entity: Id/Type/Begin/End/Value), `R` tags (relation: Id/Arg1/Arg2/Type).

**Entity mapping (7 → ours, MEDIUM):** Person→person · Location→place · Organization→organization · Thing→artifact · Abstract→concept · Time/Metric→**dropped** (we don't extract those). 5/7 map — decent.

**Relation mapping (9 → our 28, COARSE):**

| lancopku | → our category | Loss |
|---|---|---|
| Family | Kinship | coarse — 1 label vs our 5 (no direction, no married/sibling/child split) |
| Social | Social/state | coarse vs knows/trusts/enemy_of |
| Located / Near | Spatial | ok-ish |
| Ownership | Action (`owns`) | ok |
| Create | Action (`born_from`?) | partial |
| Use | — | no clean match |
| Part-Whole / General-Special | — | taxonomic, not our narrative relations |

Verdict: an **independent coarse-relation + modern-zh-entity anchor** (informational). The
register mismatch (modern vs classical) and missing license limit it to anchor, not gate.

## 3 · NCRE — github.com/LimboChen/NCRE-dataset (NLPCC 2025)

- **License:** **none** (no LICENSE file). `NCRE.json` present.
- **⚠️ Source copyright:** built on **Jin Yong wuxia novels** (查良鏞 d.2018 → in copyright until ~2088). The repo ships **labels + dialogue units**, not redistributable source text. **Cannot be used as a chapter.txt fixture; taxonomy-reference only.**
- **Size:** 100 characters, 1,109 dialogue units, 3,591 relation instances, 10,773 labels.
- **Lang:** Chinese **wuxia** (vernacular — register *closer* to our classical fixtures than lancopku's modern prose).
- **Annotation:** ChatGLM-4 preliminary + 2 rounds human review (**LLM-assisted**, not pure human).
- **Task shape:** **character-pair relationship CLASSIFICATION** across 3 dimensions — NOT open (subject, predicate, object) triple extraction from text. Different task → high reformulation cost.

**Relation taxonomy (the valuable part) vs ours — near 1:1:**

| NCRE dimension | labels | → our schema |
|---|---|---|
| Type · kinship | family, clan, **sworn-siblings** | Kinship (`child_of`/`sibling_of`/`married_to`); sworn-siblings = our 三國 `結為兄弟` case |
| Type · affiliative | workplace, **mentorship**, sect | Mentorship (`disciple_of`/`mentor_of`) + Authority (`works_for`/`member_of`/`serves`) |
| Generational | senior / peer / junior | our kinship **direction** rules (kid→parent) |
| Polarity | positive / neutral / negative | our `polarity` (affirm/negate) + `enemy_of` |

Verdict: **best relation-taxonomy reference of the three** and confirms our 28-predicate
categories are well-founded (kinship/mentorship/affiliation/sworn-siblings/generational-direction
all present). But copyright + no license + different task shape = **schema reference only, no data ingest.**

## Cross-cutting conclusions

1. **Entities (en): adopt LitBank.** CC-BY, independent, scaled — the direct antidote to the bias concern. Use as the en entity external-validity anchor (replacing/supplementing the domain-mismatched CoNLL news anchor).
2. **Relations: no clean public gold exists** in our format+domain+license. Public sets are **coarse anchors + taxonomy references**, not drop-in. → Our fine 28-predicate relation gold **stays self-built** — but now provably so, and de-biased by the independent entity anchor + NCRE taxonomy cross-check.
3. **Events: LitBank realis events** = informational anchor (granularity mismatch), not drop-in.
4. **Vietnamese: gap** — none of the three cover vi. Self-built (Lục Vân Tiên + folktales) remains required.
5. **Classical-zh register: partial** — lancopku is modern; NCRE is wuxia + copyrighted. The true classical register of 西遊記/紅樓夢 is best matched by **WYWEB / C-CLUE** (classical-Chinese NER/RE) — not surveyed in depth; **follow-up**.
6. **License reality:** LitBank CC-BY ✓ · lancopku none ⚠️ · NCRE none + copyrighted source ⚠️⚠️.

## Recommendation

- **Adopt LitBank now** as the independent en entity anchor — measure our extractor against a LitBank sample, mapping ACE→our-6-kind, report alignment. This is the highest-value, lowest-friction bias fix.
- **Cross-check our 28-predicate vocab against NCRE's taxonomy** (schema only) — confirm coverage; consider adding generational-direction / polarity richness if missing.
- **Keep relation + event + vi/classical-zh gold self-built**, with bias reduced by: multi-drafter, source-grounded adjudication, inter-annotator agreement, never annotating from extractor output.
- **Follow-up survey: WYWEB / C-CLUE** for the classical-zh register (the one register our public anchors miss).

## Appendix — first LitBank alignment measurement (2026-05-31)

Ran the production extractor (`019e6a20`) against LitBank proper-name gold on 5 works
(P&P/Alice/Little Women — overlap our fixtures; Emma/Jane Eyre — independent), ACE→our-6-kind,
token-overlap matching. **Raw** name-level P 0.591 / R 0.477 / F1 0.528; **shared-kind** (person/place/org,
excluding LitBank-absent concept/artifact) precision **≈0.80**. 23/36 "FPs" were dynamic-taxonomy
(concept/artifact) entities LitBank cannot represent; recall is low largely **by design** (scene-relevance
omission). Per-work variance was huge (Emma P 1.00 ↔ Alice P 0.21). **Read:** external numbers are deflated
by *definition/taxonomy mismatch*, not model error — confirming LitBank belongs at **sanity-floor**, not as a
gate. This reframed the direction to a correction-loop-centric plan: see
[2026-05-31-extraction-accuracy-and-eval-plan.md](../plans/2026-05-31-extraction-accuracy-and-eval-plan.md).

## Sources

LitBank https://github.com/dbamman/litbank ·
Chinese-Literature-NER-RE https://github.com/lancopku/Chinese-Literature-NER-RE-Dataset (arXiv 1711.07010) ·
NCRE https://github.com/LimboChen/NCRE-dataset (arXiv 2507.04852, NLPCC 2025) ·
WYWEB https://aclanthology.org/2023.findings-acl.204/ (follow-up)
