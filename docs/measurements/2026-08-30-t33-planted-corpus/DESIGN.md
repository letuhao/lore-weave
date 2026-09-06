# T33 planted corpus — the causal design, fixed BEFORE the extractor sees the text

`planted_by: Claude Opus 5 (assistant), at the PO's direction 2026-08-30`

## What this is, and what it is NOT

T33's stop condition asks whether the causal pass *"yields few or low-quality causal edges"*.
Answering it needs a corpus whose ground truth is known. The repo's primary route for that is a
person labelling real events, and `t33-causal-labelling-sheet.py --score` **refuses a sheet
signed by an assistant** — a detector graded against labels its own author wrote is green by
construction. That refusal is correct and this file does not touch it.

This is a **planted arm**: prose written so that the causal structure is known *by
construction*, because it was designed here first. It is the same instrument QC-5 used for
clause 1a (*"planted arm — 5/5 flagged"*).

**It cannot replace the human arm.** The same agent authored the prose and this ground truth,
so it measures one thing only: *given text where causation is deliberately unambiguous, does
the causal pass recover it?* A pass here does not establish that the detector works on real
prose written by someone else. A **failure** here is much stronger evidence — a detector that
cannot find causation that was planted for it to find has little chance on genuine text.

## The mechanism that makes this honest: order, and a digest

The failure mode of a self-authored ground truth is not dishonesty, it is drift — reading the
extractor's output and quietly deciding that is what you meant. Two controls:

1. **This file is written and committed BEFORE the corpus is ingested or any pass is run.**
2. The sheet the scorer reads carries the **SHA-256 of this file**. `--score` recomputes it and
   refuses on mismatch, so the ground truth cannot be edited after the results are known.

The digest binds the labels to this commit. If a beat below turns out to be badly written, the
repair is a new design file and a new run recorded as such — never an edit to this one.

## The mapping rule, declared in advance

Extraction decides how many `:Event` nodes the prose yields; I do not. Designed beats map to
extracted events **by reading order within a chapter** — beat *n* to the *n*-th event by
`event_order`. Consequences, accepted in advance:

- If a chapter yields a different number of events than it has beats, the mapping is
  **ambiguous and the chapter is reported as such**, not silently re-aligned. That is a finding
  about extraction granularity, and it belongs in the evidence rather than being smoothed away.
- No pair is dropped for scoring badly. The sheet is emitted from whatever the store holds.

## The prose contract

Each beat is one paragraph and one clearly separated action, so that reading order is not in
doubt. Causal links are made textually explicit (*because*, *so*, *which left*) — planting them
is the point. Merely sequential beats are written with temporal connectives only (*that
evening*, *the next morning*) and **no** causal wording. Unrelated beats share neither actor
nor object.

## Chapter 1 — *The Cistern* (8 beats)

| beat | the event | intended relation to the NEXT beat | why |
|---|---|---|---|
| 1 | Mira finds the town cistern fouled with brine | **causes** → 2 | she reports it *because* she found it |
| 2 | Mira reports the fouling to Reeve Alden | **precedes** → 3 | he dismisses her, then acts on his own account |
| 3 | Alden publicly dismisses the report as panic | **causes** → 4 | he seals the well *to make the dismissal hold* |
| 4 | Alden has the north well sealed that night | **causes** → 5 | the sealing *forces* the queue at the south well |
| 5 | The town queues at the single south well | **precedes** → 6 | the smith's forge fire is unrelated to the queue |
| 6 | Tam the smith lets his forge fire go out | **unknown** → 7 | different actor, different object, no link |
| 7 | A trader's cart breaks an axle on the salt road | **causes** → 8 | the wreck *strands* the salt shipment |
| 8 | The salt shipment strands outside the walls | — | chapter end |

**Non-adjacent (gap-2) intent for chapter 1**, which is where a detector that merely copies
reading order will be caught:

| pair | intended | why |
|---|---|---|
| 1 → 3 | **causes** | the dismissal is *of* her report of the fouling |
| 2 → 4 | **causes** | the sealing answers the report |
| 3 → 5 | **precedes** | the queue follows the dismissal only through the sealing |
| 4 → 6 | **unknown** | the forge going out has nothing to do with the well |
| 5 → 7 | **unknown** | the queue does not break the axle |
| 6 → 8 | **unknown** | unrelated |

## Chapter 2 — *The Salt Road* (8 beats)

| beat | the event | intended relation to the NEXT beat | why |
|---|---|---|---|
| 1 | The stranded salt spoils in the rain | **causes** → 2 | the spoilage *is why* the price rises |
| 2 | Salt price triples in the market | **causes** → 3 | the price *drives* the crowd to the reeve's door |
| 3 | A crowd gathers at Alden's door | **precedes** → 4 | he leaves before dawn; flight is not compelled by the crowd alone |
| 4 | Alden leaves the town before dawn | **precedes** → 5 | Mira opens the well after he is gone |
| 5 | Mira breaks the seal on the north well | **causes** → 6 | breaking the seal *lets* the town draw water |
| 6 | The town draws clean water from the north well | **unknown** → 7 | the child's fever is not shown to follow from it |
| 7 | A child falls ill with fever | **precedes** → 8 | the healer arrives after, on her own rounds |
| 8 | The healer arrives on her circuit | — | chapter end |

**Non-adjacent (gap-2) intent for chapter 2:**

| pair | intended | why |
|---|---|---|
| 1 → 3 | **causes** | the spoilage brings the crowd, through the price |
| 2 → 4 | **precedes** | the price rise does not itself compel his flight |
| 3 → 5 | **precedes** | she acts after the crowd, not because of it |
| 4 → 6 | **causes** | his leaving is what makes the well reachable |
| 5 → 7 | **unknown** | the text does not link the water to the fever |
| 6 → 8 | **unknown** | unrelated |

## The distribution, and why it is not all `causes`

Across both chapters the intended labels are **10 `causes`, 8 `precedes`, 8 `unknown`**. That
mix is deliberate and it is the control:

- A detector that answers `causes` for everything scores well on recall and is useless. The
  `unknown` and `precedes` rows are what catch it.
- A sheet whose labels were **all** `unknown` cannot discriminate at all — the scorer already
  calls that `NO-POSITIVES` and treats it as UNSCORABLE. This design cannot land there.
- The gap-2 tables exist because adjacent pairs in a well-written chapter are causal more often
  than not; a detector that simply says *"adjacent ⇒ causes, distant ⇒ unknown"* would score
  respectably on gap-1 alone. Six of the twelve gap-2 pairs are deliberately **not** `unknown`.
