#!/usr/bin/env python3
"""t33-causal-labelling-sheet — the reference corpus T33's stop condition has always needed.

T33's stop condition (plan § Stop conditions 3) reads *"T33 yields few or low-quality causal
edges → D0.1 degrades to `unknown` everywhere and AC1 stays broken"*, and the plan already
records that it CANNOT be evaluated from the dev store:

    Observed on the dev store 2026-08-11: covered 4 / total 1184.
    ⛔ That ratio does NOT evaluate this stop condition, in either direction. There is no
    production corpus; the dev database is residue from ad-hoc runs, so its denominator is
    not a population the design chose.

A ratio over residue answers a question nobody asked. What settles it is a **designed run on
a corpus with known ground truth** — and the ground truth has to come from a person, which is
the whole reason this file is two commands and not one.

    --emit   builds a labelling sheet from real events, in real reading order, with the
             LABEL fields BLANK.
    --score  reads a sheet a person has filled in and scores the system against it.

⚠️ **THIS SCRIPT MUST NEVER WRITE A LABEL.** A detector graded against labels its own author
wrote is green by construction (rule 3), and this repo has shipped that mistake before — the
sort-conformance test whose fixture created rows in the expected order, which passed a bite
that deleted the tie-break keys. `--score` therefore refuses a sheet whose `labelled_by` is
blank or names an assistant, and `--emit` writes `LABEL:` with nothing after it.

WHAT THE SCORER HAS TO GET RIGHT, AND IT IS NOT PRECISION
─────────────────────────────────────────────────────────
The stop condition's failure mode is *"degrades to `unknown` everywhere"* — a system that
emits NO ordered edges at all. Over an empty prediction set precision is vacuously 1.0, so a
scorer that reports precision would hand the stop condition's own signature a perfect score.
`NO-PREDICTIONS` is therefore a distinct verdict and it FAILS.

The mirror error is just as real, and QC-5 clause 2 is where this repo learned it: if the
labeller marks every pair `unknown`, the sheet cannot discriminate and the system's zero is
unremarkable. That is `NO-POSITIVES`, and it is **UNSCORABLE** — not a pass, not a failure of
the system, but a statement that this sheet cannot answer the question.

Usage
    python scripts/t33-causal-labelling-sheet.py --emit --book-id <uuid> --chapters 2 --pairs 20
    python scripts/t33-causal-labelling-sheet.py --score docs/measurements/<sheet>.md
    python scripts/t33-causal-labelling-sheet.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: A label is DIRECTED. The `_BA` variants say the relation runs from B to A.
#:
#: 🔴 **WHY DIRECTION IS PART OF THE LABEL (T33k, 2026-08-30).** The first sheet presented
#: each pair as `earlier`/`later`, ordered by `Event.event_order` — and that axis turned out
#: to be the extractor's EMISSION index, not reading order. Measured on the 封神演義 corpus:
#: 8 of 20 pairs were chronologically backwards, including 紂王作詩 → 盤古開天闢地, which puts
#: the creation of the universe after a poem written in chapter one. With only
#: `causes/precedes/unknown` available, every one of those collapses to `unknown` — the SAME
#: answer as "these two events are unrelated". The instrument destroyed the distinction it
#: existed to measure, and the system's one inverted prediction (P9: 帝乙生三子 → 成湯即位,
#: six centuries backwards) scored as an unremarkable abstention.
#:
#: So the sheet no longer claims to know which event came first. It presents **A** and **B**
#: and the labeller supplies the direction. A sheet that asserts no order cannot be wrong
#: about one, and a backwards prediction is now a scored failure rather than a shrug — which
#: is what T33's own criterion asks for: *a wrong order is worse than an absent one*.
CAUSES, PRECEDES, UNKNOWN = "causes", "precedes", "unknown"
CAUSES_BA, PRECEDES_BA = "causes-ba", "precedes-ba"
LABELS = (CAUSES, PRECEDES, CAUSES_BA, PRECEDES_BA, UNKNOWN)
#: Every label that asserts SOME relation. `unknown` is the only non-positive.
POSITIVE = (CAUSES, PRECEDES, CAUSES_BA, PRECEDES_BA)
#: Same relation, opposite direction. Used to count the error class T33 cares most about.
INVERSE = {CAUSES: CAUSES_BA, CAUSES_BA: CAUSES,
           PRECEDES: PRECEDES_BA, PRECEDES_BA: PRECEDES}
#: The relation with its direction stripped — `causes` vs `precedes`, regardless of way round.
BASE = {CAUSES: CAUSES, CAUSES_BA: CAUSES, PRECEDES: PRECEDES, PRECEDES_BA: PRECEDES}

#: What a person may type on a `LABEL:` line. The bare forms are accepted so a sheet emitted
#: by the pre-T33k renderer (`earlier`/`later`, A=earlier) still parses to the same meaning.
LABEL_WORDS = {
    "a causes b": CAUSES, "causes": CAUSES,
    "b causes a": CAUSES_BA,
    "a precedes b": PRECEDES, "precedes": PRECEDES,
    "b precedes a": PRECEDES_BA,
    "unknown": UNKNOWN,
}

#: The system's ordered relationship types, as `causal_edges.py` persists them.
REL_OF = {"CAUSES": CAUSES, "PRECEDES": PRECEDES}

#: Verdicts. `NO_PREDICTIONS` and `NO_POSITIVES` exist so a vacuous run cannot read as a pass.
SCORED, NO_PREDICTIONS, NO_POSITIVES, EMPTY_SHEET = (
    "SCORED", "NO-PREDICTIONS", "NO-POSITIVES", "EMPTY-SHEET")
#: A zero must say WHICH zero it is. §4.3 already retracted a global `0.34 %` that divided by
#: residue from runs which never touched the causal pipeline, and this is that error made
#: unrepeatable: if the project holds no ordered edge AT ALL, the extractor was never run here
#: and the sheet measures its ABSENCE, not its quality. Rule 13, mechanised.
PASS_NEVER_RAN = "PASS-NEVER-RAN"

#: A sheet must say who labelled it, and it must not be a machine. Not decoration: the GRANT
#: is explicit — "the PO labels the ground truth; you build the sheet, never the labels you
#: then grade".
#: Names that are certainly NOT a person signing off. A DENYLIST, and the docstring on
#: `labeller_ok` says plainly what that can and cannot do.
_MACHINE = re.compile(
    r"claude|assistant|gpt|llm|auto|tbd|todo|" + chr(92) + "bme" + chr(92) + "b"
    r"|harness|smoke|placeholder|synthetic|sample|dummy|fixture|" + chr(92) + "bn/?a" + chr(92) + "b"
    r"|" + chr(92) + "bxx+" + chr(92) + "b|" + chr(92) + "btest" + chr(92) + "b|^-+$",
    re.I)

#: The whole rest of the line, because a directed label is three words ("A causes B") and the
#: single-token form this used to match would have silently truncated it to "a".
LABEL_RE = re.compile(r"^LABEL:[ \t]*(.*?)[ \t]*$", re.M)

#: A label that is neither blank nor a recognised phrase. Kept DISTINCT from blank: a typo
#: that degraded to "unfilled" would understate the sheet, and this file's whole subject is
#: instruments whose zero means something other than what it looks like.
BAD_LABEL = "?"


def normalise_label(raw: str) -> str:
    """A `LABEL:` line's text -> one of `LABELS`, `""` when blank, or `BAD_LABEL`."""
    s = " ".join(raw.lower().split()).rstrip(".").replace("->", " ").replace("→", " ")
    s = " ".join(s.split())
    if not s:
        return ""
    return LABEL_WORDS.get(s, BAD_LABEL)
PAIR_RE = re.compile(r"^#### PAIR (P\d+)\s*$", re.M)
BY_RE = re.compile(r"^labelled_by:[ 	]*(.*)$", re.M)

#: WHO DRAFTED the labels, as distinct from who signed them.
#:
#: 🔴 A sheet can be signed by a person who reviewed and approved a draft an assistant wrote,
#: and that is a legitimate way to work — but it is NOT the same evidence as a person
#: labelling from the text, and the difference must not live in a chat log. `--score` prints
#: this beside every number, exactly as it already qualifies `labelled_by` as ASSERTED rather
#: than VERIFIED. Blank means the signer drafted them too.
PROPOSED_BY_RE = re.compile(r"^labels_proposed_by:[ \t]*(.*)$", re.M)


def parse_sheet(text: str) -> tuple[str, list[tuple[str, str]]]:
    """`(labelled_by, [(pair id, label)])`. A blank LABEL stays in the list as `""`.

    Blanks are KEPT rather than dropped so `--score` can say how much of the sheet is
    unfilled. Silently ignoring them would let a sheet with two answers score as complete.
    """
    by = BY_RE.search(text)
    pairs = [m.group(1) for m in PAIR_RE.finditer(text)]
    labels = [normalise_label(m.group(1)) for m in LABEL_RE.finditer(text)]
    return (by.group(1).strip() if by else ""), list(zip(pairs, labels))


def score(truth: dict[str, str], predicted: dict[str, str], *, pass_ran: bool = True) -> dict:
    """Verdict + per-relation counts. PURE, so the selftest drives every arm offline.

    `truth` and `predicted` are `{pair id: relation}`. A pair absent from `predicted` means
    the system asserted no ordered edge for it, which is the same as `unknown`.
    """
    filled = {p: r for p, r in truth.items() if r in LABELS}
    if not filled:
        return {"verdict": EMPTY_SHEET, "reason": "no pair carries a label yet"}

    positives = {p: r for p, r in filled.items() if r in POSITIVE}
    asserted = {p: r for p, r in predicted.items() if r in POSITIVE}

    if not positives:
        return {"verdict": NO_POSITIVES, "labelled": len(filled),
                "reason": "every labelled pair is `unknown`, so this sheet cannot "
                          "discriminate a working extractor from a silent one"}
    if not asserted and not pass_ran:
        return {"verdict": PASS_NEVER_RAN, "labelled": len(filled),
                "truth_positives": len(positives),
                "reason": "this project holds no ordered edge at all, so the extractor was "
                          "never run over it. Scoring now would measure whether anybody "
                          "pressed the button — the exact substitution §4.3 retracted"}
    if not asserted:
        return {"verdict": NO_PREDICTIONS, "labelled": len(filled),
                "truth_positives": len(positives), "recall": 0.0,
                "reason": "the system asserted no ordered edge over any labelled pair. This "
                          "is the stop condition's own signature — precision over an empty "
                          "prediction set is vacuously 1.0 and is NOT reported"}

    tp = sum(1 for p, r in asserted.items() if positives.get(p) == r)
    # An edge on a pair the labeller called `unknown`, or of the wrong kind, is a false one.
    fp = len(asserted) - tp
    fn = len(positives) - sum(1 for p in positives if p in asserted)
    # `causes` asserted where the truth is `precedes` is the expensive direction: it is a
    # claim about WHY. Direction-blind on purpose — an overclaim is an overclaim either way.
    overclaims = sum(1 for p, r in asserted.items()
                     if BASE.get(r) == CAUSES and BASE.get(positives.get(p)) == PRECEDES)
    # T33k — THE NUMBER THE ROW ACTUALLY ASKS FOR. §T33: *a wrong order is worse than an
    # absent one*. Before direction was labelled this was unmeasurable: an inverted edge and
    # a correct abstention produced the same `unknown` and the same score.
    wrong_direction = sum(1 for p, r in asserted.items()
                          if p in positives and positives[p] == INVERSE.get(r))
    return {
        "verdict": SCORED, "labelled": len(filled), "truth_positives": len(positives),
        "asserted": len(asserted), "tp": tp, "fp": fp, "fn": fn,
        "precision": round(tp / len(asserted), 3),
        "recall": round(tp / len(positives), 3),
        "causes_overclaimed_as_precedes": overclaims,
        "wrong_direction": wrong_direction,
    }


def _selftest() -> int:
    T = {"P1": CAUSES, "P2": PRECEDES, "P3": UNKNOWN, "P4": CAUSES}
    cases = [
        ("a perfect run scores 1.0 / 1.0",
         score(T, {"P1": CAUSES, "P2": PRECEDES, "P4": CAUSES}),
         lambda r: r["verdict"] == SCORED and r["precision"] == 1.0 and r["recall"] == 1.0),
        ("THE CONTROL: a system that asserts NOTHING is NO-PREDICTIONS, never precision 1.0",
         score(T, {}),
         lambda r: r["verdict"] == NO_PREDICTIONS and "precision" not in r),
        ("...and that verdict is the stop condition's shape, so recall is 0 and stated",
         score(T, {}), lambda r: r["recall"] == 0.0),
        ("A ZERO MUST SAY WHICH ZERO: no edge anywhere means the pass NEVER RAN",
         score(T, {}, pass_ran=False), lambda r: r["verdict"] == PASS_NEVER_RAN),
        ("...and that is NOT the same verdict as an extractor that ran and stayed silent",
         (score(T, {}, pass_ran=False)["verdict"], score(T, {}, pass_ran=True)["verdict"]),
         lambda r: r[0] != r[1]),
        ("THE MIRROR CONTROL: an all-`unknown` sheet is UNSCORABLE, not a pass",
         score({"P1": UNKNOWN, "P2": UNKNOWN}, {}),
         lambda r: r["verdict"] == NO_POSITIVES),
        ("an unfilled sheet is EMPTY-SHEET, not a zero-score",
         score({"P1": "", "P2": ""}, {"P1": CAUSES}),
         lambda r: r["verdict"] == EMPTY_SHEET),
        ("an edge on a pair labelled `unknown` is a FALSE positive",
         score(T, {"P1": CAUSES, "P3": CAUSES}),
         lambda r: r["tp"] == 1 and r["fp"] == 1),
        ("a missed positive is a false NEGATIVE and drops recall",
         score(T, {"P1": CAUSES}),
         lambda r: r["fn"] == 2 and r["recall"] == round(1 / 3, 3)),
        ("`causes` where the truth is `precedes` is WRONG, not a near miss",
         score(T, {"P2": CAUSES}),
         lambda r: r["tp"] == 0 and r["causes_overclaimed_as_precedes"] == 1),
        ("...and the reverse (precedes where causes is true) is also wrong but NOT an overclaim",
         score(T, {"P1": PRECEDES}),
         lambda r: r["tp"] == 0 and r["causes_overclaimed_as_precedes"] == 0),
        ("a system predicting `unknown` explicitly counts as asserting nothing",
         score(T, {"P1": UNKNOWN, "P2": UNKNOWN}),
         lambda r: r["verdict"] == NO_PREDICTIONS),
        # ── T33k — DIRECTION. The measured failure: the system asserted `precedes` on
        # 帝乙生三子 -> 成湯即位, which is backwards by roughly six centuries, and the
        # undirected sheet scored it as an unremarkable abstention. §T33: *a wrong order is
        # worse than an absent one* — so it has to be countable, and it has to be a MISS.
        ("THE ROW'S OWN CRITERION: a backwards edge is WRONG, not a near miss",
         score({"P1": CAUSES}, {"P1": CAUSES_BA}),
         lambda r: r["tp"] == 0 and r["fp"] == 1 and r["wrong_direction"] == 1),
        ("...and the same relation the RIGHT way round is a true positive",
         score({"P1": CAUSES}, {"P1": CAUSES}),
         lambda r: r["tp"] == 1 and r["wrong_direction"] == 0),
        ("a backwards `precedes` is counted too, not just backwards `causes`",
         score({"P1": PRECEDES}, {"P1": PRECEDES_BA}),
         lambda r: r["wrong_direction"] == 1 and r["tp"] == 0),
        ("a B->A label is a POSITIVE, so an all-backwards sheet is not `NO-POSITIVES`",
         score({"P1": CAUSES_BA, "P2": PRECEDES_BA}, {}),
         lambda r: r["verdict"] == NO_PREDICTIONS and r["truth_positives"] == 2),
        ("wrong relation AND wrong direction is not double-counted as a direction error",
         score({"P1": CAUSES}, {"P1": PRECEDES_BA}),
         lambda r: r["tp"] == 0 and r["wrong_direction"] == 0 and r["fp"] == 1),
        ("an overclaim is an overclaim whichever way round it runs",
         score({"P1": PRECEDES, "P2": PRECEDES_BA}, {"P1": CAUSES, "P2": CAUSES_BA}),
         lambda r: r["causes_overclaimed_as_precedes"] == 2),
    ]
    # ── T33k — the label vocabulary ──────────────────────────────────────────────────────
    cases += [
        ("a directed label parses to its direction",
         {"ab": normalise_label("A causes B"), "ba": normalise_label("B causes A")},
         lambda r: r["ab"] == CAUSES and r["ba"] == CAUSES_BA),
        ("...case, spacing and a trailing period do not matter",
         {"x": [normalise_label("  b   PRECEDES   a. "), normalise_label("B -> precedes A")]},
         lambda r: r["x"] == [PRECEDES_BA, PRECEDES_BA]),
        ("BACKWARD COMPATIBILITY: a bare `causes` still means A->B",
         {"x": normalise_label("causes")}, lambda r: r["x"] == CAUSES),
        ("a blank label is blank",
         {"x": normalise_label("   ")}, lambda r: r["x"] == ""),
        ("A TYPO IS NOT A BLANK: an unrecognised label is marked, never silently unfilled",
         {"x": normalise_label("A cause B")},
         lambda r: r["x"] == BAD_LABEL and r["x"] != ""),
        ("the multi-word label survives the line regex the single-token one would have cut",
         {"x": parse_sheet("#### PAIR P1\nLABEL: B causes A\n")[1]},
         lambda r: r["x"] == [("P1", CAUSES_BA)]),
    ]
    # ── T33k — the prose anchor, driven on the shape it was measured against ─────────────
    _poem = "燧人取火免鮮食，伏羲畫卦陰陽前。神農治世嚐百草"
    cases += [
        ("a title lifted verbatim from the text anchors on the whole title",
         {"x": prose_anchor("伏羲畫卦", _poem)},
         lambda r: r["x"] is not None and r["x"][1] == "伏羲畫卦"),
        ("...and anchors EARLIER for a phrase that appears earlier",
         {"a": prose_anchor("燧人取火", _poem)[0], "b": prose_anchor("神農治世", _poem)[0]},
         lambda r: r["a"] < r["b"]),
        ("a title sharing nothing with the text does NOT anchor at 0",
         {"x": prose_anchor("完全無關的事件", _poem)}, lambda r: r["x"] is None),
        ("...which is the point: an unanchorable event is excluded, not filed first",
         {"x": prose_anchor("XY", _poem)}, lambda r: r["x"] is None),
    ]
    sheet = ("labelled_by: \n#### PAIR P1\nLABEL: causes\n#### PAIR P2\nLABEL:\n")
    by, got = parse_sheet(sheet)
    cases += [
        ("the sheet parser keeps a BLANK label rather than dropping the pair",
         {"n": len(got), "blank": got[1][1]}, lambda r: r["n"] == 2 and r["blank"] == ""),
        ("...and reads who labelled it", {"by": by}, lambda r: r["by"] == ""),
        ("an unsigned sheet is refused", {"ok": labeller_ok("")}, lambda r: not r["ok"]),
        ("THE GRANT'S GUARD: a sheet signed by an assistant is refused",
         {"ok": labeller_ok("Claude")}, lambda r: not r["ok"]),
        ("...and by a person is accepted", {"ok": labeller_ok("NeneScarlet")},
         lambda r: r["ok"]),
        # T33h — the guard ACCEPTED `HARNESS-SMOKE-not-a-person` and then printed
        # `precision 1.0` over labels made by random.choice. A denylist cannot prove
        # provenance; what it can do is make the failure deliberate rather than accidental.
        ("a HARNESS placeholder is refused", {"ok": labeller_ok("HARNESS-SMOKE")},
         lambda r: not r["ok"]),
        ("...so are `placeholder`, `synthetic`, `sample`, `fixture`",
         {"ok": [labeller_ok(x) for x in ("placeholder", "synthetic", "sample", "fixture")]},
         lambda r: not any(r["ok"])),
        ("...and a row of dashes, or `n/a`",
         {"ok": [labeller_ok("----"), labeller_ok("n/a")]},
         lambda r: not any(r["ok"])),
        ("a real name containing a denylisted SUBSTRING is still a person",
         {"ok": labeller_ok("Sam Testerton")}, lambda r: r["ok"]),
    ]
    # ── T33i — the PLANTED arm's guards, driven end to end on real files ──────────────
    # These call `_score_planted` itself rather than re-implementing its checks. The one
    # that matters most is the last: adding a second arm must not widen the first, so a
    # planted sheet fed to the HUMAN scorer has to keep being refused.
    import contextlib
    import io as _io
    import tempfile as _tempfile

    def _rc(fn, *a):
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(*a)
        return code, buf.getvalue()

    with _tempfile.TemporaryDirectory() as _td:
        _design = os.path.join(_td, "DESIGN.md")
        with open(_design, "w", encoding="utf-8") as fh:
            fh.write("the design, v1\n")
        _digest = design_digest(_design)

        def _sheet(name, body):
            path = os.path.join(_td, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body)
            return path

        _manifest = ('```json\n{"causal_pass_ran": true, "system_predicted": '
                     '{"P1": "causes", "P2": "unknown"}}\n```\n')
        _labels = "#### PAIR P1\nLABEL: causes\n#### PAIR P2\nLABEL: unknown\n"

        _good = _sheet("good.md", "labelled_by: \nplanted_by: A Designer\n"
                       f"design_sha256: {_digest}\n" + _manifest + _labels)
        _nodigest = _sheet("nodigest.md", "labelled_by: \nplanted_by: A Designer\n"
                           + _manifest + _labels)
        _noplanter = _sheet("noplanter.md", "labelled_by: \nplanted_by: \n"
                            f"design_sha256: {_digest}\n" + _manifest + _labels)
        _human = _sheet("human.md", "labelled_by: NeneScarlet\nplanted_by: A Designer\n"
                        f"design_sha256: {_digest}\n" + _manifest + _labels)

        _rc_good, _ = _rc(_score_planted, _good, _design)
        _rc_nodig, _ = _rc(_score_planted, _nodigest, _design)
        _rc_noplant, _ = _rc(_score_planted, _noplanter, _design)
        _rc_human, _ = _rc(_score_planted, _human, _design)

        # Drift: the design is edited AFTER the sheet was bound to it.
        with open(_design, "w", encoding="utf-8") as fh:
            fh.write("the design, v2 — quietly changed after the run\n")
        _rc_drift, _drift_out = _rc(_score_planted, _good, _design)

        # And the human scorer must still refuse the planted sheet.
        _rc_via_human, _ = _rc(_score, _good)

    cases += [
        ("PLANTED: a bound sheet with a matching digest scores",
         {"rc": _rc_good}, lambda r: r["rc"] == 0),
        ("PLANTED: a sheet with no `design_sha256` is refused",
         {"rc": _rc_nodig}, lambda r: r["rc"] == 2),
        ("PLANTED: a blank `planted_by` is refused",
         {"rc": _rc_noplant}, lambda r: r["rc"] == 2),
        ("PLANTED: a sheet with a valid `labelled_by` is sent to --score instead",
         {"rc": _rc_human}, lambda r: r["rc"] == 2),
        # The load-bearing one. A self-authored ground truth fails by DRIFT, not by lying:
        # reading the output and deciding that is what you meant. The digest is what makes
        # the ordering checkable at all.
        ("PLANTED: editing the design AFTER the sheet was bound to it is refused",
         {"rc": _rc_drift, "said": "does not match" in _drift_out},
         lambda r: r["rc"] == 2 and r["said"]),
        # THE GUARD THAT MUST NOT MOVE: a second arm must not widen the first.
        ("THE HUMAN ARM IS UNTOUCHED: a planted sheet through --score is still refused",
         {"rc": _rc_via_human}, lambda r: r["rc"] == 2),
    ]
    failures = 0
    print("t33-causal-labelling-sheet - selftest (offline)")
    for label, got_v, pred in cases:
        ok = bool(pred(got_v))
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              f"{'' if ok else '  -> ' + json.dumps(got_v, ensure_ascii=False)}")
    print("\n  all checks passed" if not failures else f"\n  {failures} FAILED")
    return 1 if failures else 0


def labeller_ok(who: str) -> bool:
    """A sheet must be signed by a person — and this is a SPEED BUMP, not a proof.

    ⚠️ **Measured 2026-08-30 (T33h): the guard accepted `HARNESS-SMOKE-not-a-person`.** It is
    a denylist, so anything not on the list passes, and no script can verify that a human
    typed a label. The refusal message used to read *"the ground truth must come from someone
    other than the thing being graded"*, which claims enforcement this cannot deliver.

    What it genuinely does: stop the obvious case — a sheet signed by an assistant, or by an
    evident placeholder — so the failure has to be deliberate rather than accidental. What
    carries the real weight is that `--score`'s OUTPUT now says the signature is ASSERTED,
    beside every number it prints, so a `precision 1.0` can never be read as proof of
    independent labelling.

    That distinction is not academic: the smoke run that found this printed **precision 1.0**
    over labels generated by `random.choice`.
    """
    return bool(who.strip()) and not _MACHINE.search(who)




def _sheet_text(args, pairs, pred, *, causal_pass_ran: bool, notes=()) -> str:
    """The sheet's markdown. ONE renderer for both stores — two would drift.

    T33k — the pair is presented as **A** / **B** with NO claim about which came first. See
    the `CAUSES_BA` block at the top of this file for the measurement that forced it.
    """
    out = [
        "# T33 — causal labelling sheet",
        "",
        "labelled_by: ",
        "labels_proposed_by: ",
        "",
        "> Each pair shows two events, **A** and **B**, in NO PARTICULAR ORDER.",
        "> Fill each `LABEL:` with exactly one of:",
        ">",
        "> | type this | means |",
        "> |---|---|",
        "> | `A causes B` | A directly brings about or enables B |",
        "> | `B causes A` | B directly brings about or enables A |",
        "> | `A precedes B` | B clearly happens after A, but you cannot show causation |",
        "> | `B precedes A` | A clearly happens after B, but you cannot show causation |",
        "> | `unknown` | you cannot tell, or they are unrelated |",
        ">",
        "> **Prefer `unknown`** — the row's own criterion says a wrong order is worse than an",
        "> absent one. Judge from the text, not from the order they appear in below.",
        "",
        "**The order events are printed in carries no information.** Pair selection uses first",
        "mention in the chapter's prose, which is a heuristic and is sometimes wrong; A/B",
        "within a pair, and the pair order itself, are shuffled from a fixed seed. An earlier",
        "sheet ordered pairs by `Event.event_order` and presented them as `earlier`/`later` —",
        "that field is the extractor's EMISSION index, not reading order, so 8 of 20 pairs",
        "were backwards and the sheet had no way to say so.",
        "",
        "Events are read from the store the deployment DECLARES (`age`), not from Neo4j —",
        "reading the wrong store is what made an earlier draft report the extractor as never",
        "having run.",
        "",
        "```json",
        json.dumps({"project_id": args.project_id, "chapters": args.chapter_ids,
                    "axis": getattr(args, "axis", "prose"),
                    "seed": getattr(args, "seed", 0),
                    "causal_pass_ran": causal_pass_ran,
                    # Recorded so `--score` can qualify `recall` rather than print it bare:
                    # 0 here means the sheet holds no pair the system stayed silent on.
                    "unasserted_pairs": len(pairs) - len(pred),
                    "pairs": {p[0]: {"a": p[2]["id"], "b": p[3]["id"], "chapter": p[1]}
                              for p in pairs},
                    "system_predicted": pred}, ensure_ascii=False, indent=1),
        "```",
        "",
    ]
    if notes:
        out += ["> **Emit notes** — " + "; ".join(notes), ""]
    for pid, ch, a, b in pairs:
        out += [f"#### PAIR {pid}", "",
                f"**A** — {a['title']}", f"> {(a.get('summary') or '')[:300]}", "",
                f"**B** — {b['title']}", f"> {(b.get('summary') or '')[:300]}", "",
                "LABEL:", ""]
    return chr(10).join(out)



def _age(sql_cypher: str, cols: str, *, port: int, db: str, graph: str) -> list[list[str]]:
    """Run one Cypher against AGE through psql and return the rows as strings.

    🔴 **THE SHEET READ THE WRONG STORE, and this is why it now reads the configured one.**
    The first version spoke Bolt to Neo4j. The service's declared backend is `age` (§8.1), so
    the causal extractor's 134 edges landed in AGE and the sheet reported
    `causal_pass_ran: false` over a project that had just been processed. The instrument said
    "the extractor was never run here" about a run that had finished minutes earlier.

    That is the third instrument defect in this row alone — `created_at` ordering, a one-row
    `keys()` sample, and now the store itself — and all three failed the same direction:
    toward "there is nothing here".
    """
    full = ("LOAD 'age'; SET search_path = ag_catalog, public; "
            "SELECT * FROM cypher('" + graph + "', $$ " + sql_cypher + " $$) AS (" + cols + ");")
    r = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port), "-U", "loreweave", "-d", db,
         "-At", "-F", "|", "-c", full],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PGPASSWORD": "loreweave_dev"})
    if r.returncode != 0:
        raise SystemExit("AGE query failed: " + r.stderr[:300])
    out = []
    for line in r.stdout.strip().split(chr(10))[2:]:      # skip LOAD / SET
        if line:
            out.append([c.strip().strip('"') for c in line.split("|")])
    return out


def _chapter_text(chapter_id: str, *, port: int, db: str) -> str:
    """The chapter's prose, blocks joined in `block_index` order.

    Read-only, and from book-service's own database: the graph holds no character offset for
    an event (`provenances` is `["human_authored"]`, the EVIDENCED_BY edge carries only job
    and model), so prose position has to come from the text itself.
    """
    r = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port), "-U", "loreweave", "-d", db,
         "-At", "-c",
         "SELECT coalesce(text_content, '') FROM chapter_blocks "
         "WHERE chapter_id = '" + chapter_id + "' ORDER BY block_index;"],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PGPASSWORD": "loreweave_dev"})
    if r.returncode != 0:
        raise SystemExit("book query failed: " + r.stderr[:300])
    return r.stdout


def prose_anchor(title: str, text: str, *, min_len: int = 2) -> tuple[int, str] | None:
    """First position in `text` of the LONGEST substring of `title` that occurs in it.

    ⚠️ **A HEURISTIC, and the design depends on it being allowed to be wrong.** Measured on
    封神演義 ch.1: titles the extractor lifted verbatim out of the opening 古風 poem anchor
    exactly (`燧人取火`, `伏羲畫卦`, `神農治世`, `禹王治水`, `桀王無道`, `成湯造亳` — which is
    itself the tell that those "events" are a verse catalogue of allusions, not narrated
    action), while paraphrased narrative titles fall back to a two-character name match and
    land on the wrong mention (`紂王聽從費仲建議`, the chapter's LAST event, anchors on the
    first `紂王` in the middle).

    That error is affordable HERE and nowhere else, because this position only decides **which
    events get paired together**. A badly chosen pair is a less informative question; it is
    not a false premise. The sheet no longer states which event came first, so a wrong anchor
    cannot put a wrong claim in front of the labeller. Selection tolerates a heuristic; the
    premise must not.
    """
    n = len(title)
    for length in range(n, min_len - 1, -1):
        for start in range(0, n - length + 1):
            pos = text.find(title[start:start + length])
            if pos >= 0:
                return pos, title[start:start + length]
    return None


def _emit_age(args) -> int:
    """Build the sheet from AGE — the store the declared deployment actually reads."""
    P = args.project_id
    chapters = "[" + ",".join("'" + c + "'" for c in args.chapter_ids) + "]"
    rows = _age(
        "MATCH (e:Event {project_id:'" + P + "'})-[:EVIDENCED_BY]->(x:ExtractionSource) "
        "WHERE x.source_id IN " + chapters + " "
        "RETURN x.source_id AS ch, e.id AS id, e.title AS title, e.summary AS summary, "
        "e.event_order AS eo",
        "ch agtype, id agtype, title agtype, summary agtype, eo agtype",
        port=args.age_port, db=args.age_db, graph=args.age_graph)

    by_ch: dict[str, list] = {}
    for ch, eid, title, summary, eo in rows:
        try:
            order = int(eo)
        except (TypeError, ValueError):
            order = 2147483647
        by_ch.setdefault(ch, []).append(
            {"id": eid, "title": title, "summary": summary, "eo": order})

    notes: list[str] = []

    # ── Order the events within each chapter ─────────────────────────────────────────────
    for ch in args.chapter_ids:
        evs = by_ch.get(ch, [])
        if args.axis == "emission":
            # 🔴 THE SORT KEY COLLIDES, AND THAT IS A PRODUCT BUG, NOT A SHEET BUG.
            # `event_order = chapter_base + idx` (pass2_writer) restarts `idx` at 0 on every
            # extraction JOB while `chapter_base` depends only on the chapter, so a chapter
            # extracted in more than one job numbers its events twice. Measured on 封神演義
            # ch.1: three jobs, 20 events, 7 duplicate values, every collision cross-job.
            # A stable sort then falls back to whatever order the database handed back —
            # exactly the tie-break defect this file's own docstring cites (the sort
            # conformance test whose fixture created rows in the expected order). Refuse
            # rather than emit pairs chosen by an arbitrary tie-break.
            dupes = sorted({e["eo"] for e in evs
                            if sum(1 for x in evs if x["eo"] == e["eo"]) > 1})
            if dupes:
                print("[t33-sheet] REFUSED — `event_order` is not unique in chapter "
                      + ch + ": " + ", ".join(str(d) for d in dupes[:10])
                      + (" ..." if len(dupes) > 10 else ""))
                print("[t33-sheet] Sorting on a colliding key makes the tie-break the "
                      "database's row order, so the pairs would be arbitrary while looking "
                      "deliberate. Use --axis prose, or fix event_order at the writer.")
                return 1
            evs.sort(key=lambda e: (e["eo"], e["id"]))
        else:
            text = _chapter_text(ch, port=args.book_port, db=args.book_db)
            if not text.strip():
                print("[t33-sheet] REFUSED — chapter " + ch + " has no prose in "
                      + args.book_db + ". An empty text anchors every event at position 0, "
                      "which would look like a deliberate ordering and be none.")
                return 1
            unanchored = []
            for e in evs:
                hit = prose_anchor(e["title"], text)
                e["pos"] = hit[0] if hit else None
                e["anchor"] = hit[1] if hit else None
                if hit is None:
                    unanchored.append(e["title"])
            # An event with no anchor is EXCLUDED and named. Defaulting it to 0 would file it
            # first and read as "this happens at the start of the chapter" — a zero that
            # means "not measured" presented as a measurement.
            if unanchored:
                notes.append(str(len(unanchored)) + " event(s) excluded, no prose anchor: "
                             + ", ".join(unanchored[:6]))
            by_ch[ch] = evs = [e for e in evs if e["pos"] is not None]
            evs.sort(key=lambda e: (e["pos"], e["id"]))

    # ── What the system claims, read BEFORE selection so every claim can be scored ───────
    edges = {}
    for rel in ("CAUSES", "PRECEDES"):
        for a, b in _age(
                "MATCH (a:Event {project_id:'" + P + "'})-[r:" + rel + "]->(b:Event) "
                "RETURN a.id AS a, b.id AS b", "a agtype, b agtype",
                port=args.age_port, db=args.age_db, graph=args.age_graph):
            edges[(a, b)] = REL_OF[rel]

    # ── Select the pairs ─────────────────────────────────────────────────────────────────
    # Every pair the system ASSERTED goes in first: a sheet that samples pairs independently
    # of the predictions can miss most of them, and then `precision` is computed over
    # whichever claims happened to be sampled. The previous sheet carried 2 of the project's
    # edges. The rest of the budget is prose-adjacent pairs, which is what makes `recall`
    # mean anything — without them the sheet only ever asks about the system's own answers.
    in_scope = {e["id"]: (ch, e) for ch in args.chapter_ids for e in by_ch.get(ch, [])}
    chosen: list[tuple] = []
    seen: set[frozenset] = set()

    def _add(ch, a, b):
        key = frozenset((a["id"], b["id"]))
        if a["id"] == b["id"] or key in seen:
            return False
        seen.add(key)
        chosen.append((ch, a, b))
        return True

    asserted_in_scope = 0
    for (ea, eb) in sorted(edges):
        if ea in in_scope and eb in in_scope:
            ch, a = in_scope[ea]
            _, b = in_scope[eb]
            if _add(ch, a, b):
                asserted_in_scope += 1
    for gap in (1, 2):
        for ch in args.chapter_ids:
            evs = by_ch.get(ch, [])
            for i in range(len(evs) - gap):
                if len(chosen) >= args.pairs:
                    break
                _add(ch, evs[i], evs[i + gap])
    chosen = chosen[: args.pairs]
    if asserted_in_scope > args.pairs:
        notes.append("--pairs " + str(args.pairs) + " is smaller than the "
                     + str(asserted_in_scope) + " asserted edge(s) in scope; precision would "
                     "be computed over a subset of the system's claims")

    # ── Shuffle, so neither position nor A/B leaks an answer ─────────────────────────────
    # Without this, A is always the prose-earlier event and the asserted pairs are always
    # first — a labeller would learn both patterns within a few rows and the direction
    # measurement would be reading the layout, not the text.
    import random
    # Record the EFFECTIVE seed, not the flag. `"seed": null` in the manifest would say the
    # shuffle was unseeded when it was seeded on the project id, and re-emitting from that
    # record would produce a different sheet than the one someone labelled.
    args.seed = args.seed if args.seed is not None else P
    rng = random.Random(args.seed)
    rng.shuffle(chosen)
    pairs = []
    for n, (ch, a, b) in enumerate(chosen, start=1):
        if rng.random() < 0.5:
            a, b = b, a
        pairs.append((f"P{n}", ch, a, b))

    # A prediction is DIRECTED: which way round it runs relative to the printed A/B is the
    # thing being measured, so it is recorded that way and never as a bare relation.
    pred = {}
    for pid, ch, a, b in pairs:
        if (a["id"], b["id"]) in edges:
            pred[pid] = edges[(a["id"], b["id"])]
        elif (b["id"], a["id"]) in edges:
            pred[pid] = INVERSE[edges[(b["id"], a["id"])]]

    # A sheet made only of pairs the system already claimed can measure PRECISION and cannot
    # measure RECALL: every question on it is one the system answered, so a missed edge has
    # nowhere to show up and `recall` reads high for a structural reason. The stop condition
    # is "FEW **or** low-quality causal edges" — "few" is the recall half, so a sheet that
    # cannot see it answers half the question while printing a number for both.
    unasserted = len(pairs) - len(pred)
    if unasserted == 0 and pairs:
        notes.append("every pair on this sheet is one the system asserted — recall is "
                     "computed only over its own claims and cannot detect a MISSED edge. "
                     "Raise --pairs above " + str(asserted_in_scope) + " to add unasserted "
                     "pairs")

    out = _sheet_text(args, pairs, pred, causal_pass_ran=bool(edges), notes=notes)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(out)
    print(f"[t33-sheet] {len(pairs)} pair(s) from {len(args.chapter_ids)} chapter(s), "
          f"axis={args.axis} -> {args.out}")
    print(f"[t33-sheet] AGE holds {len(edges)} ordered edge(s) in this project; "
          f"{asserted_in_scope} fall inside the labelled chapters and ALL of those are on "
          f"the sheet; the system asserts one on {len(pred)} of its {len(pairs)} pairs")
    for note in notes:
        print("[t33-sheet] note: " + note)
    print("[t33-sheet] every LABEL is BLANK. This script does not write labels (rule 3).")
    return 0


def _emit(args) -> int:
    """RETIRED (T33k). Refuses, and says why rather than quietly emitting an old sheet.

    🔴 This path kept its OWN copy of the renderer — `_sheet_text`'s docstring says "ONE
    renderer for both stores, two would drift", and two had already drifted. When the sheet
    stopped asserting an order, this copy did not: it would still print `earlier`/`later`
    over `event_order`, which is the emission index, and hand a labeller the exact false
    premise the change exists to remove. A second emitter that produces the defect being
    fixed is worse than no second emitter.

    It is refused rather than deleted because the Bolt query is the only record of how this
    sheet was built before the store moved, and §8.1 may not be the last word on the backend.
    Reviving it means porting it ONTO `_sheet_text` — prose anchoring, the collision refusal
    and the shuffle included — not restoring the lines below.
    """
    print("[t33-sheet] REFUSED — --store neo4j no longer emits.")
    print("[t33-sheet] The declared backend is `age` (§8.1), and reading the wrong store is "
          "what made an earlier draft report the extractor as never having run.")
    print("[t33-sheet] Use: --store age  (the default).")
    return 1


def _emit_neo4j_retired(args) -> int:
    from neo4j import GraphDatabase  # imported here so --selftest needs no driver

    drv = GraphDatabase.driver(args.bolt, auth=(args.user, args.password))
    with drv.session() as s:
        rows = s.run(
            """MATCH (e:Event {project_id:$p})-[:EVIDENCED_BY]->
                     (x:ExtractionSource {source_type:'chapter'})
               WHERE x.source_id IN $chapters
               RETURN x.source_id AS ch, e.id AS id, e.title AS title,
                      e.summary AS summary, e.time_cue AS cue,
                      e.event_order AS eo, e.created_at AS created
               ORDER BY x.source_id, coalesce(e.event_order, 2147483647), e.created_at""",
            p=args.project_id, chapters=args.chapter_ids).data()
        edges = s.run(
            """MATCH (a:Event {project_id:$p})-[r:CAUSES|PRECEDES]->(b:Event)
               RETURN a.id AS a, b.id AS b, type(r) AS t""", p=args.project_id).data()
    drv.close()

    by_ch: dict[str, list] = {}
    for r in rows:
        by_ch.setdefault(r["ch"], []).append(r)

    pairs, n = [], 0
    for ch in args.chapter_ids:
        evs = by_ch.get(ch, [])
        # Consecutive AND one-apart: the forward links a 12-event window would consider,
        # without asking a person to read 300 combinations.
        for gap in (1, 2):
            for i in range(len(evs) - gap):
                n += 1
                pairs.append((f"P{n}", ch, evs[i], evs[i + gap]))
    pairs = pairs[: args.pairs]

    pred = {}
    index = {(p[2]["id"], p[3]["id"]): p[0] for p in pairs}
    for e in edges:
        pid = index.get((e["a"], e["b"]))
        if pid:
            pred[pid] = REL_OF[e["t"]]

    out = [
        "# T33 — causal labelling sheet",
        "",
        "labelled_by: ",
        "",
        "> Fill each `LABEL:` with exactly one of `causes` / `precedes` / `unknown`.",
        "> `causes` = the earlier event DIRECTLY brings about or enables the later one.",
        "> `precedes` = it clearly happens after, but you cannot show causation.",
        "> `unknown` = you cannot tell, or they are unrelated. **Prefer `unknown`** — the row's",
        "> own criterion says a wrong order is worse than an absent one.",
        "",
        "Ordering within a chapter is `Event.event_order`, which is present on **every** event",
        "in scope (122/122; 1130 of 1186 store-wide). `created_at` breaks ties for the 56 that",
        "lack it. The first draft of this sheet ordered by `created_at` alone — measured, that",
        "put a flashback ahead of the scene that frames it, which would have asked you to judge",
        "causation between two events the sheet had mis-ordered.",
        "",
        "```json",
        json.dumps({"project_id": args.project_id, "chapters": args.chapter_ids,
                    "causal_pass_ran": bool(edges),
                    "pairs": {p[0]: {"earlier": p[2]["id"], "later": p[3]["id"], "chapter": p[1]}
                              for p in pairs},
                    "system_predicted": pred}, ensure_ascii=False, indent=1),
        "```",
        "",
    ]
    for pid, ch, a, b in pairs:
        out += [f"#### PAIR {pid}", "",
                f"**earlier** — {a['title']}", f"> {(a['summary'] or '')[:300]}", "",
                f"**later** — {b['title']}", f"> {(b['summary'] or '')[:300]}", "",
                "LABEL:", ""]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print(f"[t33-sheet] {len(pairs)} pair(s) from {len(args.chapter_ids)} chapter(s) "
          f"-> {args.out}")
    print(f"[t33-sheet] the system asserts an ordered edge on {len(pred)} of them")
    print("[t33-sheet] every LABEL is BLANK. This script does not write labels (rule 3).")
    return 0


def _score(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    manifest = json.loads(text.split("```json", 1)[1].split("```", 1)[0])
    by, labelled = parse_sheet(text)
    if not labeller_ok(by):
        print(f"[t33-score] REFUSED — `labelled_by: {by or '(blank)'}` is not a person.\n"
              "  The ground truth must come from someone other than the thing being graded;\n"
              "  a detector scored against its own author's labels is green by construction.")
        return 2
    # T33k — a label that is neither blank nor a recognised phrase must STOP the score, not
    # decay into "unfilled". `parse_sheet` marks it; scoring around it would quietly shrink
    # the denominator and report a cleaner sheet than the one on disk.
    bad = [p for p, r in labelled if r == BAD_LABEL]
    if bad:
        print("[t33-score] REFUSED — " + str(len(bad)) + " label(s) not understood: "
              + ", ".join(bad[:10]) + (" ..." if len(bad) > 10 else ""))
        print("[t33-score] Each LABEL must read exactly one of: `A causes B`, `B causes A`, "
              "`A precedes B`, `B precedes A`, `unknown`.")
        return 2
    result = score(dict(labelled), manifest.get("system_predicted", {}),
                   pass_ran=bool(manifest.get("causal_pass_ran", True)))
    print(f"[t33-score] {path}")
    print(f"[t33-score] labelled by: {by}  — ASSERTED, NOT VERIFIED. No script can prove a "
          f"person typed these labels;")
    print(f"[t33-score] the check below is a denylist that stops the obvious case. Every "
          f"number here is only as good as that signature.")
    drafted = PROPOSED_BY_RE.search(text)
    drafted = drafted.group(1).strip() if drafted else ""
    if drafted:
        print(f"[t33-score] ⚠ THESE LABELS WERE DRAFTED BY: {drafted} — and reviewed by the "
              f"signer above.")
        print(f"[t33-score] That is weaker evidence than a person labelling from the text. "
              f"Wherever the draft and the signer AGREE, this number partly grades the "
              f"drafter against itself; the disagreements are the independent part.")
    for k, v in result.items():
        print(f"  {k:<32} {v}")
    if "recall" in result and manifest.get("unasserted_pairs") == 0:
        print("[t33-score] ⚠ recall above is NOT a recall over the corpus. Every pair on "
              "this sheet is one the system asserted, so a missed edge had nowhere to "
              "appear. Re-emit with a larger --pairs to measure it.")
    return 0 if result["verdict"] == SCORED else 1


PLANTED_BY_RE = re.compile(r"^planted_by:[ \t]*(.*)$", re.M)
DESIGN_SHA_RE = re.compile(r"^design_sha256:[ \t]*([0-9a-fA-F]{64})\s*$", re.M)


def design_digest(path: str) -> str:
    """SHA-256 of the design file, read as bytes."""
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _score_planted(sheet_path: str, design_path: str) -> int:
    """Score the PLANTED arm — a corpus whose causal structure was designed in advance.

    This is a SECOND arm, never a substitute for the human one. It exists because a detector
    that cannot recover causation planted for it to find has little chance on genuine prose:
    a pass here says much less than a failure here does.

    Two things keep it from being green by construction, and neither is a promise:

      * The sheet carries `planted_by:`, never `labelled_by:`. A planted sheet fed to
        `--score` therefore still hits the assistant denylist and is refused. The human
        arm is not widened by one byte to make room for this.
      * The labels are bound to the design by SHA-256. The real risk with a self-authored
        ground truth is not lying, it is DRIFT — reading the output and deciding that is
        what you meant all along. A digest over the design file makes the ordering
        checkable: edit the design after the run and this refuses.
    """
    with open(sheet_path, encoding="utf-8") as fh:
        text = fh.read()
    manifest = json.loads(text.split("```json", 1)[1].split("```", 1)[0])

    by_human, labelled = parse_sheet(text)
    if labeller_ok(by_human):
        print("[t33-planted] REFUSED — this sheet carries a valid `labelled_by`, which makes "
              "it a HUMAN sheet.")
        print("  Score it with --score. Grading a human sheet as a planted arm would "
              "understate it.")
        return 2

    m = PLANTED_BY_RE.search(text)
    planted_by = (m.group(1).strip() if m else "")
    if not planted_by:
        print("[t33-planted] REFUSED — `planted_by:` is blank. A planted arm has to say "
              "whose design it is.")
        return 2

    d = DESIGN_SHA_RE.search(text)
    if not d:
        print("[t33-planted] REFUSED — the sheet carries no `design_sha256:`. Without it the "
              "ground truth is not bound to anything, and could have been written after the "
              "results were known.")
        return 2
    actual = design_digest(design_path)
    if d.group(1).lower() != actual:
        print("[t33-planted] REFUSED — the design file does not match the digest this sheet "
              "was built against.")
        print(f"    sheet says:      {d.group(1).lower()}")
        print(f"    {design_path}: {actual}")
        print("  The ground truth changed after the sheet was emitted. Re-emit against the "
              "design, or record a NEW design file — never edit one a result was scored on.")
        return 2

    result = score(dict(labelled), manifest.get("system_predicted", {}),
                   pass_ran=bool(manifest.get("causal_pass_ran", True)))
    print(f"[t33-planted] {sheet_path}")
    print(f"[t33-planted] PLANTED ARM — designed by: {planted_by}")
    print(f"[t33-planted] design {design_path} @ {actual[:16]}... (digest VERIFIED)")
    print("[t33-planted] What this CAN establish: whether the causal pass recovers causation")
    print("[t33-planted] deliberately planted for it. What it CANNOT: that the pass works on")
    print("[t33-planted] prose written by someone else. The human arm stays owed either way.")
    for k, v in result.items():
        print(f"  {k:<32} {v}")
    return 0 if result["verdict"] == SCORED else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--score", metavar="SHEET")
    ap.add_argument("--score-planted", metavar="SHEET",
                    help="score the PLANTED arm; requires --design")
    ap.add_argument("--design", metavar="DESIGN_MD",
                    help="the design file the planted sheet is bound to by SHA-256")
    ap.add_argument("--project-id")
    ap.add_argument("--chapter-ids", nargs="*", default=[])
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(
        ROOT, "docs", "measurements", "2026-08-24-t33-causal-labelling-sheet.md"))
    ap.add_argument("--store", default="age", choices=("age", "neo4j"),
                    help="which store to read; the declared backend is `age` (§8.1)")
    ap.add_argument("--axis", default="prose", choices=("prose", "emission"),
                    help="how events are ordered for PAIR SELECTION only — the sheet asserts "
                         "no order. `prose` anchors each event to its first mention in the "
                         "chapter text; `emission` uses Event.event_order and REFUSES when "
                         "that field collides, which it does whenever a chapter was "
                         "extracted by more than one job.")
    ap.add_argument("--seed", default=None,
                    help="shuffle seed for pair order and A/B assignment. Defaults to the "
                         "project id, so re-emitting the same corpus is reproducible.")
    ap.add_argument("--book-port", type=int, default=25555,
                    help="book-service Postgres, read for chapter prose (--axis prose)")
    ap.add_argument("--book-db", default="loreweave_book")
    ap.add_argument("--age-port", type=int, default=25556)
    ap.add_argument("--age-db", default="loreweave_knowledge_vectors")
    ap.add_argument("--age-graph", default="g_shared")
    ap.add_argument("--bolt", default="bolt://localhost:7688")
    ap.add_argument("--user", default="neo4j")
    ap.add_argument("--password", default="loreweave_dev_neo4j")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.score_planted:
        if not args.design:
            print("--score-planted requires --design <the design file it is bound to>",
                  file=sys.stderr)
            return 2
        return _score_planted(args.score_planted, args.design)
    if args.score:
        return _score(args.score)
    if args.emit:
        if not args.project_id or not args.chapter_ids:
            print("[t33-sheet] --project-id and --chapter-ids are required")
            return 2
        return _emit_age(args) if args.store == 'age' else _emit(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
