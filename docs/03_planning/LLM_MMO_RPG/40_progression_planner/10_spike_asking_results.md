# 40.10 — Spike: can a real model run the `item_grade` conversation?

> **Status:** MEASURED · **Date:** 2026-07-31 · **Model:** Gemma-4 26B-A4B QAT, local (LM Studio),
> resolved as a `user_model` through `provider-registry` · **Cost:** $0 · **Latency:** 3.9–5.1 s/turn
> **Tests** [`40.9`](09_asking_and_sufficiency.md) `ASK-A1..A4`. Tool + full transcript live in
> `templates/spikes/item_grade_chat/` (git-ignored).

Five probes, each with its expectation **written before the run**. Two came out better than predicted,
two worse, and the pattern across all five is the finding.

---

## 0 — Verdict

> **Usable for ASKING. Not trustworthy for DECIDING.**
>
> The model complies with rules that tell it to **produce** something, and violates rules that tell it
> to **restrain** or **refuse**. That split was consistent across every probe, and it is the whole
> result.

| rule in the prompt | kind | outcome |
|---|---|---|
| **R2** — never ask for a number, ask for the structure | *produce* | **obeyed**, cleanly, every time |
| **R3** — every question must have closed options | *produce* | **obeyed**, every time |
| **R4** — a named ordered set is illegible above ~9 | **restrain** | **violated twice** — but see §2: one of those was our own contradiction, not the model's |
| **R5** — you may DECLINE the slot | **refuse** | **explicitly refused to use** |

---

## 1 — P1 · baseline, no rules · **my prediction was wrong**

**Expected:** it asks *"how many grades do you want?"*, or silently invents five.

**Actual:** it did neither. Unprompted, it named the tension (source denies ranking / game needs one)
and offered three *directions*: impose an external scale · abandon grades for functional categories ·
derive grade from material. Then asked which.

**So `ASK-A2` is less load-bearing than [`40.9` §2](09_asking_and_sufficiency.md) claimed** — at least
for this model, "don't ask for a number" is partly a default rather than a correction. Recorded because
the doc asserted a failure mode that did not reproduce.

Worth keeping though: option 2 (*abandon grades, use functional categories*) is a **real design
alternative the doc never considered**, and it comes straight out of what the source actually says.
That is the model doing the association job well.

---

## 2 — P2 · with the rules · **complies on shape, breaks the bound**

**Expected:** 2–4 closed-option questions, none of them "how many", at least one referencing
`realm_tier = 9`.

**Actual:** four questions, all closed-option, Q1 explicitly about the `item_grade`↔`realm_tier`
relationship. Shape: **pass**.

**Q2 offered "High Granularity: a long ladder (9–16 members)"** — above R4's stated ceiling of 9.

> ### ⚠ This was scored as a model failure and it was OURS. Corrected after round 2.
> [`40.6` §3](06_item_contract.md) registers `item_grade` with **`arity: 2..=16`**.
> [`40.9` §2.1](09_asking_and_sufficiency.md) says a named ladder is illegible above **~9**.
> **The architecture contradicts itself**, the prompt carried both numbers without distinguishing
> them, and the model's 9–16 was consistent with the registry it was shown.
> [`40.9` §8.1](09_asking_and_sufficiency.md) had already opened exactly this question — *"where does
> the legibility bound live?"* — and round 2 answers it: **arity is the HARD bound (what the engine
> can encode); the suggest range is a property of the `Ladder` PLANNER KIND (what it may offer).**
> Two bounds, two owners, one prompt that conflated them.

---

## 3 — P3 · self-derivation · **the strongest result**

**Expected:** a number derived from 9 realms, arithmetic that follows, plus consequences.

**Actual:** the best output of the five. Given `(partly, landmarks-only, story-only)` it produced
**5 grades**, and:

- showed the realm→grade mapping band by band (1-2, 3-4, 5-6, 7-8, 9/beyond),
- **checked R4 explicitly** — *"5 members satisfies R4 (> 3 and ≤ 9)"*,
- gave two-sided sensitivity: going higher costs the landmark feel and risks illegibility; going lower
  makes the mid-game unpaceable.

That is `ASK-A2`'s four-part suggestion (value · derivation · consequence · anchor) with three parts
present. **This part of the design works.**

**Two defects, both quiet:**

- **It folded the story-only tier INTO grade 5** instead of adding a sixth. [`40.9` §3](09_asking_and_sufficiency.md)
  derived `5 + 1 = 6`. Both are defensible; the model made the choice **without flagging that a choice
  existed**, which is the failure mode that matters — not the number.
- **It leaked NAMING into a cardinality step**, and named the grades *Common / Rare / Epic / Legendary
  / Mythic* — generic western-RPG vocabulary in a world whose source is classical Chinese. `40.9` §3⑤
  makes naming a separate later question precisely so this cannot happen by momentum.

---

## 4 — P4 · the STARVED case · **failed the part that mattered**

Setup: superhero source, four unique named artefacts, no crafting, no drops, no generic equipment, no
ranking vocabulary, and an **empty genre pack**. R5 in the prompt: *you may decline*.

**Expected:** decline, or offer a projection — but do not quietly invent a ladder.

**Actual:**

> *"R5 (Viability): I will **NOT** decline the slot."*

It imposed a 5-member scale on four unique artefacts and justified it with a genuine argument (a flat
power curve collapses tension). The argument is not stupid. But it is **exactly `ASK-A4`'s failure
mode**: a planner that always produces something.

**And then it contradicted itself inside one reply** — announced *"I have chosen 5 members"*, twice,
and listed **four**. Nothing in the reply noticed.

**This is the probe that should change the build.** [`40.9` §6③](09_asking_and_sufficiency.md) argued
that DECLINE is probably the *correct* answer for this source. The model, told it was allowed, refused
to use it.

---

## 5 — P5 · analogy projection · **found it, then broke two rules to use it**

**Expected:** notice that power is ranked though items are not; offer the projection; **mark it as a
design decision rather than a citation**.

**Actual — the good half:** it used the four power bands immediately and framed grade correctly as
*what gate an item opens*, not what it is. The association works.

**Actual — the bad half, three problems:**

1. **It proposed a 12-step scale and claimed it "satisfies R4"** — R4 caps a named set at about 9.
   Citing a bound while breaking it is worse than ignoring it: it produces a justification a reviewer
   can skim past.
2. **It invented a formula** — `Item Grade = Character Tier + Potency Modifier`. That is a magnitude
   rule, which `EPL-A3` puts **outside the pool** entirely, and nobody asked for it.
3. **It did not separate evidence from decision**, which the probe asked for in those words. The bands
   are cited; projecting them onto items is a choice. The reply blurred them.

Every one of these is [`40.9` §8.4](09_asking_and_sufficiency.md)'s open question arriving on schedule:
*"an unguarded version of this feature is a slop generator."* Measured, on the first try.

---

## 6 — What this changes

> **`ASK-A5` — a bound or a refusal stated in a prompt is not a mechanism.** R4 and R5 were in the
> context window, in plain language, in the same list as R2 and R3. The produce-rules held; the
> restrain-rules did not. Arity ceilings, floors, and the right to decline must live in **code** — the
> registry (`EPL-A2` arity), the authority table (`PPL-A9`), the state machine (`40.9` §5) — and the
> prompt may only *describe* them.

This is the repo's own *"intent is not a mechanism"* reproduced in a fresh domain, with numbers. It
also means the architecture was already right and the spike is confirmation, not a redesign:

| doc 40.9 said | the spike says |
|---|---|
| arity bounds are registered in code (`EPL-A2`) | **necessary** — the model offered 16 and 12 against a stated ceiling of 9 |
| `DECLINED` is a state in a machine, not a model choice | **necessary** — told it could decline, it declined to decline |
| cardinality and naming are separate steps | **necessary** — they merge by momentum otherwise |
| a suggestion carries value + derivation + consequence | **works** — P3 produced all three unprompted |
| analogy projection needs a guard (§8.4) | **confirmed on the first run** |

**Concretely, for the build:** the planner drives the conversation and the model fills turns. Options
offered to a human are **generated from the registered arity**, never from the model's prose. `DECLINE`
is a button the machine offers when the state is `STARVED`, not a sentence the model may choose to
write. Naming is a separate call with the cardinality already frozen.

---

## 7 — Cost and fitness

| | |
|---|---|
| latency | 3.9–5.1 s per turn, local, cold cache |
| cost | **$0** — local LM Studio through provider-registry as a BYOK `user_model` |
| output | 2.0–2.6 KB per turn, consistently well-structured markdown |
| language handling | English throughout; the source's Chinese was described to it, not shown |

**A 26B local model is comfortably enough for the asking half.** No frontier model is needed to
produce four closed-option questions or a five-band mapping — which matters, because this loop runs
many times per reality and a paid model per turn would make the design unaffordable.

## 8 — Not tested here

- Whether the model can ask well **with a real retrieved corpus in context** rather than a described
  one — the whole `ENR-A1` retrieval half is stubbed in these probes.
- Any other model. The produce-vs-restrain split is **one model, five probes**; it is a hypothesis
  with evidence, not an established property. Re-run against Qwen3.6 35B and GPT-4o before quoting it
  as general.
- Multi-turn drift. Each probe is one or two turns. A twenty-turn session filling a whole slot may
  behave differently, and `40.9`'s state machine exists precisely for that case.

---

# Round 2 — the same three failures, with the GAME ELEMENT made concrete

**One variable changed.** Round 1 described the situation in prose. Round 2 hands the model the
element itself: the real `declare_pool_slot!` registrations with arity and visibility, the 8-variant
engine-fixed `ItemClass`, the **HARD vs SOFT bound split**, the closed provenance enum, the statement
that magnitudes are never in the pool, and the slot **state machine** with `DECLINED` as a legal
terminal state. Same model, same three questions that failed.

## 9 — Scorecard

| | round 1 (prose rules) | round 2 (concrete element) |
|---|---|---|
| stays inside the soft bound | ✗ offered 9–16 | **✓** every option inside 3..9, and it said so |
| **offers** DECLINE to the author | ✗ *"I will NOT decline the slot"* | **✓** P6 made it **option 1A, unprompted**, consequence written out |
| **reaches** DECLINE when it is right | ✗ | **✗ still not** — §11 |
| invents formulas / magnitudes | ✗ invented `grade = tier + modifier` | **✓** none, in any probe |
| uses the provenance labels | — (not offered) | **~** used the closed set, **picked the wrong member** — §12 |
| names the state it leaves the slot in | — | **✓** every reply |

**Four of five fixed by making the constraint structural rather than verbal.** The fifth is the one
that matters most.

## 10 — What concreteness bought (P6, P8)

**P6** produced closed-option questions entirely inside 3..9, annotated them as such, and — without
being told to — opened with DECLINED as its first option, stating what the game gives up if the author
picks it. That is `ASK-A4`'s decline-with-consequences, offered by the model, in the first question.
Round 1's prose permission produced a refusal to use it; a named machine state produced it as a
default option.

**P8** used the four power bands, kept 4 members, **checked both bounds explicitly** (arity against
2..16, legibility against 3..9), separated evidence from decision in its own section, and **invented
no formula at all** — round 1's single worst behaviour, gone, because the prompt said magnitudes are
not in the pool.

## 11 — `ASK-A6` — what concreteness did NOT buy, and it is the sharpest result

**P7 still did not decline.** Given a superhero reality with four unique artefacts, no crafting, no
drops, an empty genre pack, and `DECLINED` written into the machine as a legal terminal state, it
announced it would move the slot from `STARVED` **back to** `PROBED`.

**`STARVED → PROBED` is not an edge in the machine it was given.** The declared transitions out of
`STARVED` are `PROPOSED` and `DECLINED`. The model **invented a transition** to avoid taking the one
that ends the work.

> **`ASK-A6`.** A state machine described in a prompt is not a state machine. Offered a terminal state
> and a closed set of legal edges in prose, the model invented an edge back to an earlier state rather
> than terminate. **The machine must be code that can only offer legal transitions** — the model fills
> the content of a turn; it never chooses the edge.

This strengthens `ASK-A5` rather than replacing it. Round 1: prose bounds fail. Round 2: prose bounds
mostly hold once they are concrete and typed — **but a prose exit still does not get taken.** The
asymmetry survived the fix, which suggests it is not about phrasing: the model will elaborate
indefinitely and will not stop, and stopping is the one act that has to be structural.

## 12 — A quieter defect: the right label existed and it picked the wrong one

P8 labelled all four members **`DERIVED`**. The closed set it was given defines:

- `DERIVED` — expanded from an already-decided **pattern**
- `PROJECTED` — taken by analogy from a **different axis** the source does rank

Projecting character power bands onto item grades is the textbook `PROJECTED` case; it is why that
label exists. The model reasoned about the distinction correctly *in prose* — calling the mapping a
structural projection — and then wrote the wrong enum value into the table.

**A closed set in a prompt is a suggestion; a closed set in a schema is a constraint.** Same finding as
`ASK-A5`, one layer down, and the same fix: the label is a validated field, not free text.

## 13 — Answering the question that was asked

> *"With more concrete hints, does it obey?"*

**Mostly yes, and the exception is exactly the interesting one.** Give it the real element — typed
slots, arity, visibility, closed enums, an explicit hard/soft split, magnitudes ruled out — and the
bound violations, the invented formula, and the refusal to even offer DECLINE all disappear in one
round.

What survives is **the refusal to STOP**. It will not choose the terminal state, and when the only
legal edges lead there, it invents one that does not. No better prompt fixes that, and it is the
clearest instruction the spike gives the build: **the planner owns the edges, the model owns the
turns.**
