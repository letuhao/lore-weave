#!/usr/bin/env python3
"""Emit the `/goal` condition for the WHOLE-LEDGER defect loop (every class, not just contract).

    python scripts/toolloop/goal_prompt_all_defects.py --check && \
        python scripts/toolloop/goal_prompt_all_defects.py

Third sibling. `goal_prompt.py` drives the blocked-TOOL loop; `goal_prompt_defects.py` drives the
CONTRACT-only defect loop; this one drives every open defect regardless of class. One generator
per goal — they are not merged, because merging them would mean one QUEUE serving three different
finish lines and no session could tell which one it was running.

WHY THIS EXISTS, and it is the owner's decision of 2026-08-28: fourteen deferred questions were
answered in one sitting, and the work they release does NOT sit in one class. T33 is infra,
T54/T55/T59 are model, T57/T58 are platform, T50/T51/T52 are instrument, and only the rest are
contract. A contract-only goal would have left most of those decisions unbuilt while reporting
itself finished — the exact staleness the goal-prompt command exists to prevent.

CONTRACT STILL SORTS FIRST inside the queue, on the owner's original evidence: GPT-4 mini failed
architecture v1 too — model swapped, architecture held constant, still failed — so a `contract`
defect is one a STRONGER MODEL FAILS IDENTICALLY. That is an ordering, not a filter; nothing is
excluded any more.

QUEUE is emitted LAST because it is the elastic section and `/goal` caps the condition at 4000
characters. Losing open items to an overflow is recoverable; losing STOP is not.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gate  # noqa: E402  — ONE home for the state vocabulary; see DEFECT_OPEN_STATES

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
BUDGET = 4000
#: How many rows to NAME. The rest are counted and pointed at, never silently dropped.
#: 3 -> 2 on 2026-08-28: this goal's row KEYS are longer than the contract-only sibling's (they
#: carry a class tag) and the condition landed at 4162/4000. QUEUE is the elastic section exactly
#: so an overflow is paid for HERE and never by trimming a rule.
DQ_NAMED = 8   # blocking questions named inline; the rest are counted and linked
#: 2 -> 1 on 2026-08-31. The new objective's STOP block is longer (it enumerates the four ways a
#: row may leave `open`, and bars re-blocking a ruled row) and the condition landed at 4187/4000.
#: QUEUE is the elastic section precisely so an overflow is paid HERE: NEXT still names the resume
#: pointer, and every open row is counted in the header, so nothing is dropped — only unnamed.
#: A ruled-but-unbuilt question gets a SHORT excerpt: it is a pointer to the ruling,
#: which is the spec. The full text is on the question.
#: 🔴 SCOPED TO THIS ROUND, BECAUSE THE FIRST VERSION MEASURED ITSELF. Without this the
#: stream reported THIRTY questions "ruled but unbuilt" -- every ruling ever answered, including
#: two dozen whose remedies shipped weeks ago. They lacked a `built_*` stamp only because the
#: stamp convention was invented the same hour as this function. Backfilling it across history
#: would have asserted two dozen builds nobody re-verified, which is the ledger defect this whole
#: goal exists to avoid. So the stream carries the rulings THIS round commissioned; earlier ones
#: are out of scope for this goal and stay that way until someone checks them one at a time.
ROUND_KEY = "answer_2026_08_31_round4"
DQ_EXCERPT = 58
RULED_NAMED = 2   # ruled-unbuilt shown inline; the rest counted
NAMED = 1
#: Characters of each named row's invariant to show. Enough to RECOGNISE the row, not to
#: understand it — a row needing more than this has narration where its invariant should be.
EXCERPT = 24
#: Class order inside the queue. Contract first (see the module docstring); the rest follow by how
#: directly they block a user-visible behaviour. A class missing here sorts last, never vanishes.
CLASS_ORDER = ("contract", "platform", "infra", "model", "instrument")

DURABLE = """\
BUILD THE REMEDY EACH OPEN ROW HAS BEEN RULED, in contracts/tool-deep-dive-ledger.json.

OBJECTIVE. Every open row carries an owner ruling; nothing waits on a \
decision. DONE = invariant NAMED, fixed at ONE chokepoint, a falsifier RED on an \
ORIGINAL instance, the WHOLE owning suite green, and a LIVE run through the real chat path. \
Then `fixed`, with evidence.

THE RULING IS THE SPEC: read it BEFORE building, build it AS WORDED. If it cannot be, \
the question goes BACK CORRECTED with the measurement showing why — never substitute a \
mechanism quietly, nor re-open a settled question to dodge the work.

THE RUN ENDS ONLY WHEN `goal_prompt_all_defects.py --check` reports NO OPEN DEFECT and \
NOTHING RULED-BUT-UNBUILT, and `gate.py audit` is clean. NOTHING ELSE ENDS IT. One fix \
is ONE CYCLE, never the run: when a row reaches `fixed`, open the next IN THE SAME TURN.

A ROW LEAVES `open` FOUR WAYS, THREE NOT `fixed`: `withdrawn` (never a defect), \
`superseded` (folded into a row naming its mechanism), `cannot_reproduce` (gone — \
needs the ORIGINAL INSTANCE, the re-run WITH ITS COUNT, and what was never shown; \
audit refuses it otherwise). Blocking is an ESCAPE HATCH: only on a question \
filed IN THIS RUN with the measurement that forced it.

NEVER STOP FOR: asking whether to go on; a finished cycle; a green suite; a long report. \
A turn that has not moved a row MUST END IN A TOOL CALL. Reporting is not progress.

UNIT. ONE defect per cycle — a floor on rigour, not a cap on effort. DO NOT BATCH ON A \
BROKEN PLATFORM: the batch then measures the platform.

METHOD. 1 INVESTIGATE BEFORE THEORISING: service logs, chat_messages \
tool_calls/advertised/withheld, batch JSON, store diffs. Read, then reason. 2 NAME THE \
INVARIANT, FIX THE CLASS at ONE chokepoint — prefer where the information DIES; \
check FIRST if the mechanism exists and is merely EMPTY. 3 RUN THE CONTROL THAT REFUTES \
YOU before writing the fix. 4 DEPLOY AND VERIFY BY CONTENT: sha256 from INSIDE the \
container; restart ai-gateway on a description change. 5 PROVE IT LIVE: real provider, \
K>=5, throwaway fixture, CONCURRENCY 1 (parallel batches starve the local GPU and every \
run dies of no_output_timeout, which reads like a refuted remedy).

EVIDENCE. Proven by a RUN, never by code looking right, never by a helper test — \
ASSERT EVERY CALL SITE, not the one you edited. A CLEAN ARM PROVES \
NOTHING UNTIL YOU SHOW IT REACHED THE PATH. Run the whole owning suite. A failed attempt is \
RECORDED. Every fix states what it does NOT cover.

CHECK YOUR INSTRUMENT BEFORE REPORTING IT: a census with a shocking number is \
usually measuring itself.

ANTI-CHEAT. Never weaken a bar, scenario or expectation to fit; a wrong bar stays RED \
and you say so. A baseline may only SHRINK. Never split a defect to inflate the count. \
Never write `fixed` when the live run exercised only part of it — say which part is \
unproven. When your own control refutes your row, WITHDRAW IT and record what misled \
you. Re-derive every number; a ledger claim is a lead, not a fact.

SAFETY. Never write to the dogfood book: one throwaway fixture per scenario, torn down. A \
read-only TOOL is not a read-only TURN. Auth only via /v1/auth/login using the \
git-ignored docs/dev/LOCAL_TEST_ENV.md; never scrape a token or invent one. SELECT \
before any DML. Every open DQ gets a RECOMMENDATION and is DECIDED BY THE OWNER — never \
decide or close one yourself to unblock a defect."""


#: A deferred question NAME, matched whole. `DQ-T4` and `DQ-T45` are different questions and one
#: is a prefix of the other, so a bare substring test conflates them — the inert-repair bug this
#: generator's sibling records at length.
_DQ_TOKEN = re.compile(r"DQ-T\d+")


def _open_dq_names(led: dict) -> set[str]:
    """The deferred questions STILL WAITING on the owner.

    `blocked_by_dq` records WHICH question a row waits on, never whether the answer arrived. A
    row is blocked only while its question is genuinely open, so answering one releases its rows
    with no second edit — and therefore no second place to forget.

    🔴 AND `state` IS NOT WHERE THE ANSWER ARRIVES. The owner writes a ruling into an `answer_*`
    field; flipping `state` is a separate bookkeeping act that nobody is obliged to perform, and
    on 2026-08-30 FOUR rulings — DQ-T44, T53, T58, T64 — had been sitting behind `state: open`
    with their answers written. This function called all four "waiting on the owner", every row
    they block read as DQ-blocked, and the generator printed "NEXT. No unblocked work. Every open
    row waits on a decision above" while seven rows had a ruling ready to build.

    A queue that reports no work while work exists is worse than a wrong queue: nobody looks
    again. So ANSWERED means answered — the presence of a ruling releases the rows, exactly as
    flipping `state` would, and the two no longer have to agree for the queue to be right.
    """
    dqs = led.get("deferred_questions") or {}
    return {name for name, q in dqs.items()
            if isinstance(q, dict) and q.get("state") == "open"
            and (not _has_ruling(q) or _returned_corrected(q))}


def _has_ruling(q: dict) -> bool:
    """Has the owner written a ruling on this question, whatever its `state` says?

    Keyed on the FIELD PREFIX the owner actually uses (`answer_2026_08_28`), because that is what
    the ledger contains — not on a status word this loop would then have to keep in sync.
    """
    return any(str(k).startswith("answer") for k in q)


def _returned_corrected(q: dict) -> bool:
    """Has this ruling been SENT BACK because it could not be built as worded?

    🔴 A RULING SENT BACK IS A QUESTION AGAIN. The standing rule is "if it cannot be built, the
    question goes BACK CORRECTED with the measurement showing why", and a corrected question is
    waiting on the owner exactly as an unanswered one is. Without this, a row whose ruling was
    refuted by its own equivalence check sits at the head of the queue as WORK whose only
    completion is building the thing the measurement just showed must not be built.

    Kept SEPARATE from `_has_ruling` on purpose: the ruling still exists and is still worth
    reading. What changed is whether it is actionable.
    """
    return any(str(k).startswith("returned_corrected") for k in q)


def ruled_unbuilt(led: dict) -> list[tuple[str, str]]:
    """Questions the owner has RULED that no open defect row represents.

    🔴 THE GAP THIS CLOSES, FOUND 2026-08-31 THE DAY IT WOULD HAVE COST A WHOLE STREAM.
    The queue was derived from `defects` alone, so a ruling whose remedy has no defect row was
    invisible to it: twelve questions were answered that morning and SIX of them
    (DQ-T1, T34, T35, T37, T40, T43) had no open row anywhere. The generator would have reported
    a queue of fifteen, the run would have finished it, and `--check` would have said DONE while
    six ruled remedies had never been built. A queue that cannot see a work stream reports the
    run complete when it is not.

    A ruling counts as OUTSTANDING until the cycle that builds it stamps a `built_*` (or
    `shipped_*`) key on the question. That stamp is the ONLY thing that retires it here — not
    the answer, which is what commissioned the work in the first place.
    """
    out: list[tuple[str, str]] = []
    open_rows = {k: json.dumps(v, ensure_ascii=False)
                 for k, v in (led.get("defects") or {}).items()
                 if isinstance(v, dict) and v.get("state") in gate.DEFECT_OPEN_STATES}
    for name, q in (led.get("deferred_questions") or {}).items():
        if not isinstance(q, dict) or q.get("state") != "answered":
            continue
        if ROUND_KEY not in q:
            continue
        if any(k.startswith(("built", "shipped")) for k in q):
            continue
        if any(name in blob for blob in open_rows.values()):
            continue  # an open row already carries this work; it is queued as that row
        out.append((name, " ".join(str(q[ROUND_KEY]).split())[:DQ_EXCERPT]))
    return sorted(out)


def rows() -> tuple[list[tuple], collections.Counter]:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    still_open = _open_dq_names(led)
    counts: collections.Counter = collections.Counter()
    out: list[tuple] = []
    for k, v in (led.get("defects") or {}).items():
        if not isinstance(v, dict):
            continue
        # 🔴 THE QUEUE ASKS THE VOCABULARY, IT DOES NOT GUESS. This read `state != "open"` and
        # skipped the rest, which silently dropped 25 rows at `proven` — not fixed, not
        # withdrawn, and by this goal's own bar not finished. An unknown token RAISES rather
        # than falling out, for the reason `recompute_progress` records at length: a row that
        # matches nothing must be noticed, never absorbed.
        st = v.get("state")
        if st not in gate.DEFECT_STATES:
            raise ValueError(
                f"defect {k!r} has state {st!r}, which is not one of {gate.DEFECT_STATES}. "
                "The queue cannot decide whether it is work.")
        if st not in gate.DEFECT_OPEN_STATES:
            continue
        cls = v.get("defect_class") or "unclassified"
        counts[cls] += 1
        # Several rows carry their substance under neither `invariant` nor `what`. Falling
        # through the whole row beats emitting a blank line into a 4000-char budget.
        inv = next((str(v[f]) for f in
                    ("invariant", "what", "measured", "status", "severity") if v.get(f)), "")
        # `blocked_by_dq` may name several in prose ("DQ-T56 (and DQ-T53 for the root cause)"),
        # so the names are TOKENISED and the row is blocked if ANY is still open — releasing a
        # row whose second question is unanswered sends the next session at work it cannot
        # finish.
        named = v.get("blocked_by_dq")
        mentioned = set(_DQ_TOKEN.findall(str(named or "")))
        blocked = bool(mentioned & still_open)
        rank = CLASS_ORDER.index(cls) if cls in CLASS_ORDER else len(CLASS_ORDER)
        # 🔴 COERCED, because a single bad value CRASHED the generator that ends the run.
        # `out.sort()` compares this element across rows, so one row carrying a STRING where the
        # convention is an int 1-4 raised TypeError and the whole queue became unreadable —
        # 🔴 COERCED, because a single bad value CRASHED the generator that ends the run.
        # `out.sort()` compares this element across rows, so one row carrying a STRING where the
        # convention is an int 1-4 raised TypeError and the whole queue became unreadable —
        # measured 2026-08-31, from a row I had just filed with queue_group="composition". The
        # crash needs a TIE on (blocked, rank) to surface, which is why it hid until two rows of
        # one class were open at once. A malformed priority must cost that row its ordering,
        # never everyone else's queue.
        _qg = v.get("queue_group")
        _qg = _qg if isinstance(_qg, int) else 4
        out.append((blocked, rank, _qg,
                    not v.get("queue_anchor"), k, cls,
                    " ".join(inv.split())[:EXCERPT], named if blocked else None))
    # DQ-blocked LAST and never NEXT: they cannot be closed without an owner decision, and a
    # resume pointer aimed at one sends the next session to wait rather than to work.
    out.sort()
    return out, counts


def build() -> tuple[str, list[tuple], collections.Counter]:
    all_rows, counts = rows()
    total = sum(counts.values())
    by_class = " · ".join(f"{counts[c]} {c}" for c in CLASS_ORDER if counts.get(c))
    extra = " · ".join(f"{n} {c}" for c, n in sorted(counts.items()) if c not in CLASS_ORDER)
    head = (f"QUEUE, derived. {total} open: {by_class}"
            + (f" · {extra}" if extra else "")
            + ". Contract first; nothing excluded.")
    free = [r for r in all_rows if not r[0]]
    if free:
        named = "\n".join(f"  [{cls}] {k}\n    {inv}"
                          for _b, _r, _g, _a, k, cls, inv, _dq in all_rows[:NAMED])
        nxt = f"NEXT. {free[0][4]}  ({free[0][5]})"
    else:
        # TERMINAL STATE — every row is blocked, so naming three of them with their invariants
        # spends the budget on work nobody can start. The OPEN ITEMS here are the DECISIONS:
        # one line each, every blocking question and how many rows wait on it.
        waiting: dict[str, int] = {}
        for _b, _r, _g, _a, _k, _cls, _inv, dq in all_rows:
            if dq:
                waiting[dq] = waiting.get(dq, 0) + 1
        # 🔴 TRIMMED, NOT TRUNCATED. Enumerating every blocking question grew past the 4000-char
        # budget on 2026-08-31 (4023) as the DQ list reached 22 names. The skill's rule is to
        # shorten the SOURCE or trim QUEUE and LINK the rest — never to cut upward from the
        # bottom, because what sits at the bottom is STOP. So the questions blocking the MOST
        # rows are named (they are where a single ruling frees the most work) and the tail is
        # counted and pointed at the generated digest, which carries all of them in full.
        _ranked = sorted(waiting.items(), key=lambda x: (-x[1], x[0]))
        _shown, _rest = _ranked[:DQ_NAMED], _ranked[DQ_NAMED:]
        named = "  " + " · ".join(f"{dq}({n})" for dq, n in _shown)
        if _rest:
            named += (f" · +{len(_rest)} more ({sum(n for _, n in _rest)} rows) — all of them, "
                      "with recommendations, in docs/sessions/OPEN_DECISIONS.md")
        nxt = ("NEXT. No unblocked work. Every open row waits on a decision above; "
               "take those first.")
    # RULED, NOT YET BUILT — the second work stream. Emitted after the defect queue because
    # a defect row is the more specific unit, but counted by `check` exactly the same: the run
    # is not finished while either stream has entries.
    ruled = ruled_unbuilt(json.loads(LEDGER.read_text(encoding="utf-8")))
    tail = ""
    if ruled:
        shown, rest = ruled[:RULED_NAMED], ruled[RULED_NAMED:]
        tail = ("\n\nRULED, NOT YET BUILT — no open row carries these; the ruling IS the spec. "
                f"{len(ruled)} left. Stamp `built_*` on the question when done.\n"
                + "\n".join(f"  {q} — {a}" for q, a in shown))
        if rest:
            tail += "\n  +" + ", ".join(q for q, _ in rest)
        if not free:
            nxt = f"NEXT. {ruled[0][0]} (ruled, unbuilt)"
    return (f"/goal {DURABLE}\n\n{head}\n{named}{tail}\n\n{nxt}\n",
            all_rows, counts)


def check(text: str, all_rows: list, counts: collections.Counter) -> int:
    bad = []
    if len(text) > BUDGET:
        bad.append(f"OVER BUDGET: {len(text)} > {BUDGET} chars. Shorten the SOURCE, never cut "
                   f"upward from the bottom — STOP sits above QUEUE for that reason.")
    if counts.get("unclassified"):
        bad.append(f"{counts['unclassified']} open defect(s) have no `defect_class`. They are "
                   f"still QUEUED (this goal excludes nothing) but they sort last and their "
                   f"class should be set in the ledger, not here.")
    _ruled = ruled_unbuilt(json.loads(LEDGER.read_text(encoding="utf-8")))
    if not all_rows and not _ruled:
        bad.append("no defect is open and nothing is ruled-unbuilt — is that true, or did the "
                   "state field drift?")
    if not all_rows and _ruled:
        # NOT a failure: the defect queue is empty and the other stream is not. Said out loud
        # because "no open defect" used to read as "done".
        print(f"CHECK: 0 open defects, but {len(_ruled)} ruled remedies are unbuilt: "
              + ", ".join(q for q, _ in _ruled), file=sys.stderr)
    if all_rows and all(r[0] for r in all_rows):
        bad.append("every open defect is DQ-blocked; NEXT would point at a decision, not work.")
    for w in bad:
        print(f"CHECK: {w}", file=sys.stderr)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text, all_rows, counts = build()
    if a.check:
        return check(text, all_rows, counts)
    print(text, end="")
    print(f"\n[{len(text)} / {BUDGET} chars]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
