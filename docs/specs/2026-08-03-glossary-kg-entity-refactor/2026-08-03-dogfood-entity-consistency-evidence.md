# Dogfood evidence — what entity inconsistency actually costs the reader

**Status:** EVIDENCE · not a design, not an investigation. **Opened:** 2026-08-03
**Source:** an end-to-end authoring run on the Mị Đế book, driven through the real frontend
**Subjects:** book `019f9f2d-f9f1-7037-ba78-8ccc3e19c956` · plan run `019fc5f4-fef8-7f09-94bc-7c76eb6d3ca4`
· authoring run `019fc62f-9dea-7b4f-bce7-8945948ccd9a`

> **Why this file is here.** The three inputs to this refactor were each found by following a bug
> *inside the system* — an unreachable FK, a kind that disagreed with itself, five private notions
> of "gone". None of them shows what the reader gets. This run produced three finished chapters of
> prose, and the entity-consistency gap is legible in them without reading any code. Keep it as the
> acceptance case: **a design that cannot prevent §1 has not addressed this refactor.**

---

## 1 · A character minted at 05:47 took the antagonist's defining act at 05:54 — and the canon check scored it 5/5

The plan's own `cast_plan` artifact is unambiguous about who betrays the protagonist:

| name | role | `is_new` |
|---|---|---|
| Lâm Trạch | **antagonist** | false |
| Lâm Diệp | rival | **true** |

and its summary for Lâm Trạch reads *"the closest friend, the one who set the trap"*.

The `cast` pass proposed three new cast members, flagged them honestly (`is_new: true`), and the
review panel rendered that correctly — this is **not** a labelling defect. A human approved them;
`Apply seed` minted all three into the glossary at **05:47** as `character` entities
(glossary 29 → 32: `Lâm Diệp`, `Thanh Nguyệt`, `Lục Vô Tội`).

**Seven minutes later**, the level-4 drafting run wrote the trap into the story and gave it to the
wrong entity. Chapter 3 has Lâm Trạch — the cast-designated antagonist — pouring tea and offering
comfort, and then attributes the anonymous letter luring the protagonist to his death to the
brand-new `rival`:

> *"cách hành văn, cách ngắt nhịp và cả sự ngông cuồng ẩn sau những dòng chữ tinh tế kia… nó mang
> một phong thái quá đỗi quen thuộc. Một sự quen thuộc mang hơi thở của Lâm Diệp."*
> — *the phrasing, the cadence, the arrogance behind those elegant lines… it carries a bearing far
> too familiar. A familiarity that breathes of Lâm Diệp.*

The betrayer has been split in two, and the half that acts is the character that did not exist
before this morning. The critic's verdict on that chapter, stored on the unit row:

```
coherence=5  voice_match=5  pacing=4  canon_consistency=5   violations=[]   severity=ok
```

**`canon_consistency = 5/5`, on all three chapters.** So the signal that exists to protect exactly
this — the callback discipline the whole book is a test of — reports a perfect score while the
central betrayal is handed to the wrong entity.

### Why it belongs to THIS refactor, not to the critic

The obvious reading is "the critic is weak." That is not the useful one. The critic has no
question to ask. **Nothing in the system holds the proposition "Lâm Trạch is the one who sets the
trap" in a form a check can evaluate against prose.** The `cast_plan` holds it as free text in an
artifact; the glossary holds `Lâm Trạch` and `Lâm Diệp` as two `character` rows with no relation
between them and no role; the graph holds neither role nor the plan's assignment. A canon check
handed a chapter and a roster of names can only verify that the names are known — and every name
in that chapter *was* known, because the system had minted the new one seven minutes earlier.

This is the identity root ([entity-identity](2026-08-01-entity-identity-under-qualitative-extraction.md))
observed from the far end: *a miss does not degrade, it mints* — and once minted, the new entity is
indistinguishable from canon to everything downstream, including the check whose job is to notice.

**What a design must answer:** where does a *role assignment* live such that (a) the plan writes it,
(b) the glossary/KG can hold it as more than prose, and (c) a canon check can fail on it? Note this
is not the same question as "what kind is this entity" — Lâm Trạch and Lâm Diệp are both correctly
`character`. Kind was right and the story was still wrong.

---

## 2 · The materialise preview claimed 12 new glossary entries; all 12 already existed

`plan_bootstrap_propose` offered, for human approval:

```
NEW CHAPTERS (11)          — correct, all 11 were new
NEW GLOSSARY ENTRIES (12)  — every one of the 12 already existed in this book
```

and rendered every one of the 12 with the kind **`Character`**, including entities whose stored
kinds are not `character` at all:

| shown as | actually is |
|---|---|
| Linh năng học *(the study of spirit-energy)* | `power_system` |
| Chân Linh *(the immutable innermost soul layer)* | `power_system` |
| Thanh Tâm Ấn *(a soul-healing technique)* | `item` |
| Ma đạo *(the demonic path//faction)* | `organization` |
| Sự phản bội tại khởi đầu *(the founding betrayal)* | `event` |

**Root:** `bootstrap_service.propose()` builds `claimed_glossary_keys` from
`list_active_for_book(...)` — *prior bootstrap proposals* — and never asks the glossary what the
book already contains, while the chapter half of the same function does exactly that
(`self._book.list_chapters(...)` → `existing_titles`). The kind shown is
`ge.get("kind_code") or "character"`, a default applied at preview time.

**No data was corrupted**: apply goes through `/internal/books/{id}/extract-entities`, which
upserts by name, so the stored kinds were preserved (verified after apply — `Chân Linh` is still
`power_system`, count still 29 before the separate cast seed). The service's own comment already
names this posture: the upsert is *"the backstop against a true duplicate slipping through — an
accepted approximation, documented not hidden."*

That posture is defensible for the write. It is **not** defensible for the preview, which is a
human-approval gate: the author is asked to approve creating twelve things that exist, under kinds
they do not have. Two of the three inputs to this refactor are about the system not knowing what an
entity is; here it does know, and does not ask.

---

## 3 · Relationship proposals: 3 of 8 defensible

From the ontology session on the same book (2026-08-02), the KG relationship proposer offered 8
edges. Three were kept. Of the five rejected:

- **one category error** — `Linh hồn năm tầng` *(the five-layer soul model, a `power_system`)*
  `enemy_of` `Huyết Vô Thường` *(a person)*. A schema cannot be an enemy of a man.
- **two reversed** — `Sự phản bội tại khởi đầu` *(the founding betrayal, an `event`)* `betrayed`
  `Lâm Trạch` and `… betrayed Tô Thanh Dao`. They are the betrayers, not the betrayed.

Both failure modes are type/direction errors that the kinds already present in the glossary would
have caught: `enemy_of` between a `power_system` and a `character` is not a valid typing, and a
`betrayed` edge whose subject is an `event` has no reading. The proposer does not consult them.

This is the same shape as §1 one layer down — the facts needed to reject the proposal are in the
system, and the thing that could act on them cannot see them.

---

## 4 · Not this refactor's — recorded so nobody re-finds them here

The same three chapters carry composition-quality defects with no entity dimension. They are named
here **only** so a reader of this file does not mistake them for evidence, and they get no row in
the register — the [generation SSOT](../2026-07-31-generation-ssot.md) is their home if they are
ever worked:

- **beat leak** — chapter 1 (`HOOK`, "the gift and the shadow it casts") also writes the betrothal
  scene, which is chapter 2's beat; chapter 2 then writes it again.
- **near-duplicate scene** — chapters 2 and 3 both stage "Tô Thanh Dao under the moon at the
  pavilion, refusing him coldly."
- **repeated stock phrase** — *"y phục lụa trắng thêu chỉ bạc"* (white silk robes embroidered with
  silver thread) appears near-verbatim in all three chapters.
- **length** — 800–1100 words per chapter, short for the form.

None of these were caught by the critic either (`pacing=4` throughout), but none of them requires
knowing what an entity is.

---

## 5 · What this run also proves works

Recorded because a register of defects with no baseline is not evidence of anything. On the same
run, driven entirely through the frontend by a local model at **$0.15 total**:

- propose (llm) → 1 arc, 11 beats · compile → 11 outline chapters · validate · bootstrap → 11 real
  book chapters · Pass Rail 6/7 with two human checkpoints · 35 scene nodes linked · 3 chapters
  drafted at level 4.
- The `cast` pass correctly matched **nine** existing characters and flagged exactly the **three**
  it invented.
- `beats` assigned per-chapter roles and a tension curve (`HOOK` 65 → `ESTABLISHMENT` 35 → 58 →
  `RISING_CONFLICT` 55) consistent with the arc.
- The prose honours the premise's science-of-cultivation conceit without labelling it
  (*"điều động các hạt hạ nguyên tử trong L-Field"* — directing the sub-elementary particles within
  the L-Field), and preserves the dramatic irony the plan asked for: the reader is told the comfort
  is a lie in the same paragraph the protagonist accepts it.

The gap in §1 is therefore **not** "the pipeline does not work." It is that the pipeline works well
enough to produce a canon error worth catching, and nothing in it can catch one.
