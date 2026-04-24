# decisions — Index

> **Purpose:** User-confirmation decision tracker for the LLM MMO RPG track — pending questions, locked history, MV5 primitives, deferred big features (DF1..DF15). Split from `OPEN_DECISIONS.ARCHIVED.md` on 2026-04-24 via `scripts/chunk_doc.py`. Every chunk is a verbatim byte-range of the archived monolith; `chunk_rules.json` + `chunk_doc.py verify` prove losslessness (`VERIFY OK`, sha256=`3f1fce3932e6295b26a8c3c46b3788757e5b993b9eb2c4557eb4e37268249b86`, 175 419 bytes, 6 chunks).

**Active:** (empty — no agent currently editing)

---

## Chunk map (source order)

| # | File | Section | Lines | Purpose | Status |
|---:|---|---|---:|---|---|
| 00 | [00_preamble.md](00_preamble.md) | H1 + "How to use" + "Pending decisions" stub | 26 | Usage contract (Locked / Default-applied / Open terminology) | STABLE |
| 01 | [pending_questions.md](pending_questions.md) | Q-RISK + Q-A1/A4/D1/E3 | 45 | Items needing explicit user input; only external-dependency items remain (A4 / D1 / E3) | PENDING — external input |
| 02 | [locked_decisions.md](locked_decisions.md) | Locked decisions (history) | 485 | Every locked decision ever made — ~430 table rows spanning L/MV/PC/R/M/C/HMP/WA/S/SR batches | LOCKED |
| 03 | [mv5_primitives.md](mv5_primitives.md) | MV5 primitives — what must be locked now | 28 | Primitives retained in V1 even though MV5 cross-reality travel is deferred | LOCKED |
| 04 | [deferred_DF01_DF15.md](deferred_DF01_DF15.md) | Deferred big features | 26 | DF1..DF15 registry (DF12 withdrawn); each gets its own `10X_*.md` when impl commits | DEFERRED |
| 05 | [99_how_to_answer.md](99_how_to_answer.md) | How to answer | 9 | Short footer — how the user provides decisions to unblock items in `pending_questions.md` | STABLE |

**Totals:** 6 chunks · 175 419 bytes · 619 lines (source had 619 lines).

---

## Exported stable IDs (authoritative owner = this subfolder)

`locked_decisions.md` owns the authoritative row for every ID below. The actual *design* lives in the referenced section of the storage / multiverse / PC / safety doc; this file is the confirmation audit trail.

- **Storage top-level:** L1 · L4 · LMV-Fork · LMV-Name · S2 · S3 · S5 · S6
- **Multiverse:** MV1..MV11 (MV4-a / MV4-a-load / MV4-b / MV7 sub-IDs · MV9 / MV10 / MV11 thresholds)
- **Player character:** PC-A1..PC-E3 (13 IDs)
- **Storage risks:** R1-L1..R1-L6 + R1-archive-bucket + R1-impl-order · same layer pattern for R2..R13 (R12 folded into R6)
- **SA+DE critical:** C1-OW-1..5 · C2-D1..D5 · C3-D1..D6 · C4-D1..D4 · C5-D1..D6
- **Adversarial review follow-ups:** H1-H6-D1 · H3-NEW-D1..D6 · M-REV-1..6-D1 · P1-P4-D1
- **Multiverse M-resolutions:** M1-D1..D7 · M3-D1..D8 · M4-D1..D6 · M7-D1..D5
- **WA / category heuristics:** WA4-D1..D5
- **Security:** S1-D1 · S2-NEW-D1..D5 · S3-NEW-D1..D8 · S4-D1..D8 · S5-D1..D8 · S6-D1..D8 · S7-D1..D7 · S8-D1..D8 · S9-D1..D10 · S10-D1..D8 · S11-D1..D10 · S12-D1..D10 · S13-D1..D10
- **SRE:** SR1-D1..D8 · SR2-D1..D10 · SR3-D1..D10 · SR4-D1..D10 · SR5-D1..D10

`deferred_DF01_DF15.md` owns: **DF1..DF15** (DF12 withdrawn) — the registry. Each entry names the feature + scope + schedule. Design docs are created when each DF graduates to implementation.

`pending_questions.md` owns: **Q-RISK / Q-A1 / Q-A4 / Q-D1 / Q-E3** — the currently-open items.

External docs link to these IDs, not to specific file paths.

---

## Pending splits / follow-ups

| File | Lines | Issue | Proposed action |
|---|---:|---|---|
| `locked_decisions.md` | 485 | Under soft cap but dense (~335 bytes/line, 430+ rows). | No split needed today. If future S/SR/DF row additions push past 500 lines, split by batch prefix (L/MV/PC/R/M/C/HMP/WA/S/SR) using row-level patterns — see `chunk_rules.json` comments for the batch-first-row ID list. |

No chunk exceeds the 1500-line hard cap. No chunk is over soft cap.

---

## How to work here

1. Claim the subfolder by setting the **Active:** line above with your agent name + ISO UTC timestamp + scope.
2. **Adding a new locked decision:** append a new row to `locked_decisions.md` (keep rows grouped by batch — insert near same-prefix rows). Update the "Exported stable IDs" list above with the new ID. Add the decision's reference section-file under `02_storage/` (or wherever the design lives) in the same commit.
3. **Moving a pending question to locked:** edit `pending_questions.md` (mark as locked or remove the row) **and** append the locked row to `locked_decisions.md` in one commit.
4. **Never renumber** locked IDs. Withdrawn IDs get a `~~strikethrough~~` treatment in-place, not a renumber.
5. Cross-ref by ID (e.g. "see S9-D3"), not by file path.
6. Clear the **Active:** line when you finish.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Regenerate from archive

If chunks are accidentally corrupted or deleted:

```bash
cd d:/Works/source/lore-weave-game
python scripts/chunk_doc.py split docs/03_planning/LLM_MMO_RPG/decisions/chunk_rules.json --force
```

Verify without rewriting:

```bash
python scripts/chunk_doc.py verify docs/03_planning/LLM_MMO_RPG/decisions/chunk_rules.json
```
