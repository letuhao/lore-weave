# 09 — The first real input: extracting a glossary from classical Chinese

Everything in this folder assumed a glossary. §[`07`](07_lore_bible.md) then found there was none — the
world this track built has **0 entities**, because extraction was deliberately skipped when the plan
was for the pool loop to read the novel directly. This is the record of satisfying that prerequisite
and of what the first slice actually produced.

Run 2026-08-01 · 封神演義（原著）, chapters 1–10 · Gemma-4 26B-A4B QAT, resolved by role through
`scripts/dev-model.py` · 8 kinds adopted · 59 attributes · `reasoning_effort: none`.

---

## 1. A step nobody had written down

Extraction refused with `EXTRACT_PROFILE_UNAVAILABLE`. The cause is a prerequisite of the
prerequisite: **a book must be ADOPTED before it can be extracted** — `book_kinds` populated and
`book_active_genres` set — and the world-setup script never did it, because the plan at the time was to
skip glossary entirely.

> **`BTG-A26`.** The chain is longer than the design assumed: **adopt → extract → glossary → sweep →
> bible**. Each link was individually documented somewhere and the chain was written down nowhere, so
> the first three were discovered by hitting them. Anything that claims a book is ready for this tier
> has to check adoption, not just existence.

Genres chosen: `universal` (mandatory) · `xianxia` · `fantasy` · `historical`. They drive attribute
auto-selection, so they are a real input, not metadata.

## 2. The result: it works, and on the hard case

186 entities created and 151 updated across 10 chapters, `completed_with_errors` with **0 failed
chapters** and no error message — non-fatal batch noise. Roughly 19 entities per chapter, with dedup
visibly working (the 151 updates are re-encounters, not new rows).

| kind | n |
|---|---|
| event | 42 |
| character | 41 |
| organization | 28 |
| terminology | 28 |
| item | 19 |
| location | 14 |
| species | 9 |
| power_system | 5 |

Quality on the entities themselves is **better than the design assumed**, and this matters because
classical Chinese is the hard case — no spaces, dense proper nouns, a register far from any model's
training centre:

```
character     姜桓楚      lord of the eastern march; rebelled over his daughter's
                          wrongful death, executed at the capital
item          炮烙        a red-hot instrument of execution used on those who defy
location      朝歌        the Shang political centre, now under tyranny
power_system  修仙/道術    the Daoist practice, able to sense heaven-and-earth omens
event         雷震子出現   an infant found beside an ancient tomb; taken as a disciple
```

Each of those is correct, sourced from the text, and usable.

## 3. The systematic error, and it is the one that matters

Of 28 entities filed as **organization**, roughly **18 are places**:

```
終南山 (mountain) · 九間殿 (hall) · 終南山玉柱洞 (cave) · 西岐 (city) · 太師府 (mansion) ·
武成王黃飛虎帥府 (mansion) · 南都 · 東魯 · 西宮 · 中宮 · 白虎殿 · 司天台 · 冀州
```

One is a **creature** — 五色神牛, a five-coloured divine ox, which is a *mount* — and one is a
**military unit**, 三千飛騎. Genuine organizations amount to 商朝 · 四鎮 · 九卿.

So `location` reports 14 while the real figure is nearer 32, and `organization` reports 28 while the
real figure is nearer 3.

> **`BTG-A27`.** **A kind error is worse than a missing entity, and the sweep cannot see it.** A
> missing entity is absent from the list and shows up as a gap; a misfiled one is *present, described
> correctly, cited correctly, and invisible to the question that would have found it*. A design layer
> sweeping `location` for map material would never see 冀州.
>
> This is precisely the residue §[`08`](08_measuring_a_creative_result.md) §5.3 predicted — *the profile
> measures the pipeline, not its inputs* — arriving on the first slice, in the first hour, at roughly
> **64% on one kind**. Every number in the census would have been green.

Worth being fair to the extractor: 商朝 as an organization is defensible, and a mansion is arguably
both a place and a household. But 終南山 is a mountain, and no reading makes it an institution.

## 4. What this changes

1. **Kind confidence belongs in the sweep, not in the extractor.** The sweep visits every entity
   anyway; asking *"is this kind right?"* per entity is nearly free at that moment and impossible
   afterwards. It is also exactly the shape the tier already wants — a decision per element, surfaced
   to a human, ranked.
2. **Do not trust a kind filter.** Any query of the form *"give me the locations"* silently returns 14
   of 32. Where the design says a design layer sweeps a kind (§[`07`](07_lore_bible.md) §6), it must
   sweep **everything** and let kind be a hint.
3. **The aggregate in §[`07`](07_lore_bible.md) §6 inherits this.** *"location 611 · sect 88"* would be
   wrong in the same proportion, and the "8 edge types never fired" signal — argued there as a
   statement about the world — could equally be a statement about the extractor. **That signal needs a
   second source before it is trusted.**

## 5. Honest limits of this measurement

* **10 chapters of 100**, and they are court-politics chapters. Items and power-system entities are
  thin (19 and 5) because 乾坤圈 and the cultivation material arrive later. The kind mix will move.
* **The 64% is eyeballed, not scored.** It is a reading of 28 names by one person, not a rubric against
  an answer key. It is enough to establish that the error class is real and large; it is not a rate to
  quote precisely.
* **One model, one setting.** `reasoning_effort: none` on a 26B local model. Whether a larger model or
  graded reasoning fixes the kind confusion is unmeasured, and it is the obvious next question — but it
  belongs to the extraction pipeline's own track, not to this one.
