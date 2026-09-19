# Idea lifecycle — the standard

The rules every idea document follows. `SKILL.md` carries the short version; this is the source of truth.

## Where ideas live

```
docs/ideas/
├── README.md                          # this standard, for humans (created on first run)
├── INDEX.md                           # the registry — one row per idea, never deleted
└── YYYY-MM-DD-<slug>.md               # one file per idea
```

- **Date** = the day the idea was first recorded. It never changes, even when the idea is revisited.
- **Slug** = 2–6 lowercase words joined by hyphens, from the title (`cross-book-characters`).
- **Id** = `IDEA-NNN`, zero-padded to 3 digits, the next number after the highest in INDEX.
  Ids are permanent and never reused.

## Statuses

| Status | Meaning | Required before entering it |
|---|---|---|
| `seed` | recorded, not yet explored | a title and one sentence of what it is |
| `explored` | brainstormed and researched | Frame + Diverge + Research sections filled (or Research marked *not performed* with the reason) |
| `shortlisted` | a scored winner, worth building | Converge section with the scoring table, a recommendation, and a smallest test |
| `promoted` | handed to CLARIFY as a spec draft | a `docs/specs/…` file exists and is linked |
| `parked` | good idea, wrong time | a reason, and the condition that would bring it back |
| `rejected` | decided against | a reason |

## Allowed transitions

```
seed ──► explored ──► shortlisted ──► promoted
  │          │             │
  └──────────┴─────────────┴──► parked ──► (back to seed or explored, with a log line)
  └──────────┴─────────────┴──► rejected   (final; reopening means a NEW idea that links to this one)
```

- `seed → shortlisted` directly is **not** allowed. Skipping exploration is how the first idea wins by default.
- `promoted` is final for the idea doc. Everything after that happens in the spec and the plan.
- Reopening a `rejected` idea means creating a new `IDEA-NNN` that links to the old one and states what
  has changed since. The old reason stays readable.

## The Log

Every idea document ends with a **Log**, one line per change, newest last:

```
- 2026-09-18 — seed — captured from chat ("authors keep asking about series")
- 2026-09-20 — explored — /ideate session: 22 ideas, 7 sources
- 2026-09-20 — shortlisted — "series bible project" scored 4.1/5
- 2026-10-02 — promoted — docs/specs/2026-10-02-series-bible.md
```

The INDEX row and the Log change in the **same edit**. A status that only one of them shows is a bug.

## What each section must contain

| Section | Must contain | Common failure |
|---|---|---|
| Frame | the How-might-we question, the user, the pain, and the "already exists?" repo check | skipping the repo check and re-proposing a deferred item |
| Diverge | 15–30 raw ideas, each labelled with its technique, including ≥3 wild ones | five safe variations of one idea |
| Research | sources with URL and date read; what users say; what failed; ideas added from research | an unsourced "competitors do X" |
| Converge | clusters, a scoring table with a reason per score, invariant notes, a recommendation, the losers and why | a table of numbers with no reasons |
| Smallest test | one concrete, cheap way to learn whether the top idea is right | "build it and see" |

## Language and gates

- Docs are written in **English**; the repo's `scripts/doc-language-gate.py` rejects non-English prose
  in committed docs. Quote foreign-language sources briefly, and analyse in English.
- Ideas are **not** subject to the plan acceptance-criteria gate — they are not plans. A promoted spec
  enters the normal CLARIFY → PLAN flow, where the plan gates apply.

## Ownership

- Anyone may capture a seed.
- Only the PO decides `promoted`, `parked` and `rejected`. An agent may *propose* them (review mode) and
  apply them only after the PO agrees.
