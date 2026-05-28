# Cycle <N>: <Title>

> **TEMPLATE** — canonical brief structure per RAID_WORKFLOW.md §12.6 (P6) +
> CYCLE_DECOMPOSITION.md §4. brief-structure-validator.sh asserts every brief
> contains all 10 sections + ≤ 4000 tokens + ≥ 3 🔴 lines in REMINDERS.

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** <one paragraph>
- **Acceptance gate:** `scripts/raid/verify-cycle-<N>.sh` exits 0
- **Top 3 LOCKED decisions consumed:** <Q-ID>, <Q-ID>, <Q-ID>
- **DPS count:** <N>
- **Estimated wall time:** <hours>

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: <list>
- Files expected to exist (grep-able paths): <list>

## Scope (IN)
- <bullet list of artifacts to build>

## Scope (OUT — explicitly)
- <bullet list of what NOT to touch in this cycle>

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: <list with paths>
- Lints pass: <list>
- Integration smoke: <description>

## DPS parallelism plan
- DPS 1: <slice + worktree files> (return budget: 1500 tokens summary)
- DPS 2: <slice + worktree files>
- ...

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- <what the cold-start adversary should specifically check>
- <known pitfalls / common mistakes for this kind of cycle>

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present
- No OUT items touched
- All acceptance criteria met
- Cross-cycle invariants not violated

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Layer plan: [L<N>_*.md](../../plans/2026-05-29-foundation-mega-task/L<N>_*.md)
- Kernel chunks: <list with §-anchors>
- LOCKED decisions consumed (full list): <all Q-IDs>

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** <Q-ID> → <one-line resolution>
- 🔴 **Top LOCKED 2:** <Q-ID> → <one-line resolution>
- 🔴 **Top LOCKED 3:** <Q-ID> → <one-line resolution>
- 🔴 **Acceptance MUST include:** <key gate that's easiest to forget>
- 🔴 **Do NOT touch:** <out-of-scope items most likely to drift>
- 🔴 **Fresh session reminder:** this is a new `/raid <N>` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
