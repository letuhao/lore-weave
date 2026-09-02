#!/usr/bin/env python
"""Emit the open-decision digest — every question waiting on the owner, ranked by what it frees.

WHY THIS EXISTS. The tool-loop's queue reached a state where all 24 open defects are blocked on
owner decisions and none is actionable. At that point the bottleneck is not engineering; it is
that a person has to read 32 questions scattered through a 1.5MB ledger and rule on them. This
turns that into one ordered page.

DERIVED, NEVER TYPED — the same rule the `/goal-prompt` skill enforces on the queue it emits, and
for the same reason: a hand-written digest is stale the first time a question is answered, and a
stale digest is worse than none because it gets believed. Everything below is read from
`contracts/tool-deep-dive-ledger.json` at emit time.

RANKING. By rows unblocked, then by whether a correction is outstanding. A question blocking three
defects is worth reading before one blocking none — but a question whose premise this loop has
RETURNED CORRECTED is called out regardless of rank, because ruling on a refuted premise is the
one outcome that wastes the owner's decision entirely.

Usage:  python scripts/toolloop/dq_digest.py [--out docs/sessions/OPEN_DECISIONS.md]
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"


def _gen():
    """Reuse the queue generator's own open-DQ predicate rather than re-implementing it.

    A second copy of "which questions are still open" is a second chance to disagree with the
    queue, and the queue is what decides whether a defect is actionable. One home.
    """
    spec = importlib.util.spec_from_file_location(
        "goalgen", ROOT / "scripts" / "toolloop" / "goal_prompt_all_defects.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _first(d: dict, *prefixes: str) -> str:
    for k, v in d.items():
        if any(str(k).startswith(p) for p in prefixes):
            return str(v)
    return ""


def _trim(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def build() -> str:
    g = _gen()
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    dqs = led["deferred_questions"]
    open_names = g._open_dq_names(led)

    blocks: dict[str, list[str]] = collections.defaultdict(list)
    open_rows = {k: v for k, v in led["defects"].items()
                 if isinstance(v, dict) and v.get("state") == "open"}
    for name, row in open_rows.items():
        b = row.get("blocked_by_dq")
        for n in ([b] if isinstance(b, str) else list(b or [])):
            if n in open_names:
                blocks[n].append(name)

    ranked = sorted(
        open_names,
        key=lambda n: (-len(blocks.get(n, [])), not g._returned_corrected(dqs[n]), n),
    )

    out: list[str] = []
    w = out.append
    # The title branches for the same reason the summary does: "waiting on these" contradicts
    # its own body once nothing is open, and a heading is the part a reader trusts fastest.
    w("# Open decisions — the tool-loop is waiting on these" if open_rows
      else "# Open decisions — standing questions, none blocking")
    w("")
    w(f"*Generated {_dt.date.today().isoformat()} by `scripts/toolloop/dq_digest.py`. "
      "Derived from the ledger at emit time — do not hand-edit; re-run it.*")
    w("")
    # 🔴 THIS SENTENCE USED TO BE UNCONDITIONAL and asserted "nothing else moves until
    # some of these are ruled on". On 2026-09-02 the last open defect was withdrawn, and the
    # digest went on telling the reader the loop was decision-blocked with ZERO defects open —
    # a header that contradicted its own body two lines below. A generated summary that cannot
    # describe the empty case is a stale artefact waiting to happen, so it now branches.
    if open_rows:
        w(f"**{len(open_rows)} defect(s) are open and {len(blocks)} of these questions are what "
          f"hold them.** The loop's own check reports every open defect as decision-blocked, so "
          f"nothing else moves until some of these are ruled on.")
    else:
        w(f"**No defect is open.** The {len(ranked)} question(s) below hold no work: each is a "
          f"standing question kept as a record, and answering one releases nothing that is "
          f"currently blocked. They are still worth ruling on when convenient — a question left "
          f"open is analysis nobody has decided to act on, not analysis that was wrong.")
    w("")
    w("A ruling goes on the question's row as an `answer_<date>` field. The loop reads it there "
      "and builds it **as worded** — if it cannot be built, the question comes back with the "
      "measurement showing why, rather than a substituted mechanism.")
    w("")

    corrected = [n for n in ranked if g._returned_corrected(dqs[n])]
    if corrected:
        w("## ⚠ Read these first — their premise was refuted")
        w("")
        w("Each of these carries a ruling or a premise that this loop measured and found wrong. "
          "Ruling on the question as originally worded would spend a decision on something that "
          "is not true.")
        w("")
        for n in corrected:
            q = dqs[n]
            w(f"- **{n}** — {_trim(q.get('question', ''), 150)}")
            w(f"  - *what changed:* {_trim(_first(q, 'returned_corrected'), 260)}")
        w("")

    w("## All open questions, by how many defects they release")
    w("")
    for n in ranked:
        q = dqs[n]
        rows = blocks.get(n, [])
        w(f"### {n} — releases {len(rows)} defect{'' if len(rows) == 1 else 's'}")
        w("")
        w(f"**Asked:** {_trim(q.get('question', ''), 700)}")
        w("")
        # 🔴 SURFACE THE CORRECTIONS BESIDE THE QUESTION, and this was added because the first
        # version of this digest did not. DQ-T71's question TEXT still quotes "28 of 1,786 runs
        # (1.57%)"; the re-derivation that showed the real figure is 1.73% on the trigger
        # population — and that the OTHER direction is 2.5x larger, not smaller — lives in a
        # separate field. A digest that prints the question and hides the correction hands the
        # owner the stale number in the most authoritative-looking place on the page.
        # 🔴 SURFACE BY DATE, NOT BY TOPIC WORD — and the topic-word list is why. The first
        # version matched keys containing "corrected", "re_derived", "premise" and a handful of
        # others. Checked against its own output on 2026-08-30 and it was MISSING the session's
        # biggest results: the pipeline tool's 0-of-80, its five-call protocol, the 1.3M-id
        # census, a p=0.048 batch, and the tie population falling from 25 to 13. Every one of
        # those lives in a field this page exists to show, and every one has a DATE in its key.
        #
        # A hand-kept vocabulary of interesting-sounding words cannot keep up with what gets
        # measured, and when it falls behind it fails SILENTLY — the page still renders, just
        # without the finding. Keying on the date stamp instead means a field written today is
        # shown today, whatever it is called.
        _DATED = re.compile(r"20\d\d[_-]\d\d[_-]\d\d")
        for k in q:
            kl = str(k).lower()
            if _DATED.search(str(k)) or any(t in kl for t in (
                    "corrected", "re_derived", "rederived", "premise",
                    "is_static", "moved_the", "verified_unchanged",
                    "blast_radius", "not_be_reproduced", "established")):
                # 1600, not 600: a correction's POINT is usually its numbers, and they sit
                # after the sentence that sets them up. At 600 the DQ-T71 entry showed the
                # framing and cut off before "4.32%" — the figure that reverses which half
                # of the question is larger.
                w(f"**⚠ Correction on record ({k}):** {_trim(q[k], 1600)}")
                w("")
        rec = _first(q, "my_recommendation", "recommendation")
        if rec:
            w(f"**My recommendation:** {_trim(rec, 700)}")
            w("")
        if q.get("why_it_is_the_owners"):
            w(f"**Why it is yours, not mine:** {_trim(q['why_it_is_the_owners'], 400)}")
            w("")
        if rows:
            w("**Blocks:** " + ", ".join(f"`{r}`" for r in sorted(rows)))
            w("")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--check", action="store_true",
                    help="emit nothing; exit 1 if any open question lacks a recommendation")
    a = ap.parse_args()

    if a.check:
        g = _gen()
        led = json.loads(LEDGER.read_text(encoding="utf-8"))
        dqs = led["deferred_questions"]
        missing = [n for n in sorted(g._open_dq_names(led))
                   if not any("recommend" in str(k).lower() for k in dqs[n])]
        if missing:
            print("OPEN QUESTIONS WITH NO RECOMMENDATION FROM THE LOOP — the standing rule is that "
                  "every one carries one before the owner sees it:", file=sys.stderr)
            for n in missing:
                print(f"  {n}", file=sys.stderr)
            return 1
        print("every open question carries a recommendation")
        return 0

    text = build()
    if a.out:
        p = ROOT / a.out
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {a.out} ({len(text.splitlines())} lines)")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
