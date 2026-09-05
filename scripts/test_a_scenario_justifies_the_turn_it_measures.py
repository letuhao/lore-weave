"""D-FE-RUNNER-MEASURES-THE-LAST-TURN-SO-A-PROMPT-EDIT-CAN-MISS.

fe_runner measures `turns[-1]`. Editing `prompt` on a scenario that declares follow_ups
therefore changes a turn NOBODY READS, and it fails silently: on 2026-08-23 catalog_get_book's
and translation_job_control's prompts were rewritten to ask for the tool's real action, both
runs still measured 'Open the first one and show me its detail.' and 'Cancel that job.', and
the batch read as a refutation of the edit. jobs_cancel/jobs_pause have no follow_ups, which is
why the same edit moved them 0/5 -> 5/5 — the difference looked like the tools and was the
harness.

TWO THINGS MAKE IT SILENT, and both are closed here.

1. NOTHING PRINTED THE SENTENCE THAT WAS ACTUALLY ASKED. The report showed a scenario id and
   two fractions. It now prints the measured turn, and says `prompt` is setup that no bar
   reads, for every scenario that declares follow_ups.

2. THE JUSTIFICATION COULD DESCRIBE A TURN NOBODY MEASURES. `prompt_source` exists to say why
   the sentence is the right sentence. Measured over the corpus 2026-08-27: of 124 scenarios
   with follow_ups, 119 already name the measured turn — "Turn 1 is jobs_list's own purpose;
   the MEASURED turn is jobs_cancel's synonyms ['stop job'] ... verbatim". Five do not, and
   all five justify turn 1 while measuring a bare affirmative:

       composition-arc-apply        "_meta.synonyms['apply arc template'] ... verbatim"
                                    measured: 'Yes, go ahead and do it.'

   That is the defect stated in the scenario's own metadata, and it is checkable.

WHAT THIS IS NOT. It does not say a bare affirmative is a bad thing to measure — proving the
model carries intent across a confirmation is a real question and has its own row
(D-AFFIRMATIVE-FOLLOW-UP-LOSES-THE-PRIOR-INTENT). It says the justification must describe the
turn that is measured, so that an author editing the wrong turn is told.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

from fe_runner import measured_turn  # noqa: E402

BASELINE = ROOT / "contracts" / "justifies-the-unmeasured-turn-baseline.json"

#: Ways a justification can name the turn that is measured. Read from what the 119 compliant
#: scenarios actually write, not invented: they say "the MEASURED turn is …", "turn 2 is …",
#: "the re-ask", or they quote the sentence.
_NAMES_THE_TURN = ("measured", "follow", "turn 2", "turn 3", "turn 4", "re-ask", "reask")


def justifies_the_measured_turn(sc: dict) -> bool:
    """Does `prompt_source` describe the turn the bars read?

    Single-turn scenarios are trivially yes — `prompt` IS the measured turn."""
    if not sc.get("follow_ups"):
        return True
    src = (sc.get("prompt_source") or "").lower()
    if not src:
        return False
    if any(k in src for k in _NAMES_THE_TURN):
        return True
    # Or it quotes the measured sentence.
    # Trailing whitespace stripped AFTER the cut: an 18-character window lands mid-sentence,
    # and a quote that closes at that word boundary ("'Yes, go ahead and'") would otherwise miss
    # on the space alone.
    head = measured_turn(sc).strip("\"'. ")[:18].strip().lower()
    return bool(head) and head in src


def scenarios():
    for f in sorted((ROOT / "scripts" / "toolloop").glob("scenarios-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            yield f.name, s


def offenders() -> set[str]:
    return {f"{fn}::{s.get('id')}" for fn, s in scenarios()
            if not justifies_the_measured_turn(s)}


def test_the_scan_sees_the_corpus():
    """ANTI-VACUITY. If the glob or the schema moves, everything below passes for free."""
    all_ = list(scenarios())
    assert len(all_) >= 400, f"only {len(all_)} scenarios found"
    multi = [s for _, s in all_ if s.get("follow_ups")]
    assert len(multi) >= 100, f"only {len(multi)} declare follow_ups — nothing to check"


def test_the_predicate_REJECTS_a_justification_aimed_at_turn_one():
    """The discrimination itself, on a constructed pair. If it accepted both, the baseline
    below would be a list of names with no test behind it."""
    bad = {"follow_ups": ["Yes, go ahead and do it."],
           "prompt": "Apply arc template — use my library arc template 'X' on this book.",
           "prompt_source": "_meta.synonyms['apply arc template'] + ['apply library arc'], verbatim"}
    assert not justifies_the_measured_turn(bad)
    good = dict(bad, prompt_source=(
        "Turn 1 is the request; the MEASURED turn is the confirmation, which is the thing "
        "under test."))
    assert justifies_the_measured_turn(good)
    assert justifies_the_measured_turn(dict(bad, prompt_source="quotes it: 'Yes, go ahead and'"))


def test_a_single_turn_scenario_is_never_an_offender():
    """PRECISION. `prompt` IS the measured turn when nothing follows it, and most of the
    corpus is that shape — flagging them would drown the signal."""
    assert justifies_the_measured_turn({"prompt": "Cancel that job.", "prompt_source": "x"})
    assert justifies_the_measured_turn({"prompt": "Cancel that job."})


def test_no_NEW_scenario_justifies_a_turn_it_does_not_measure():
    """THE GATE. The baseline may only SHRINK."""
    base = set(json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"])
    new = sorted(offenders() - base)
    assert not new, (
        "these scenarios declare follow_ups, so the MEASURED turn is the last one — but "
        "`prompt_source` justifies a different turn, which is how an edit to `prompt` goes "
        "silently nowhere:\n  " + "\n  ".join(new)
        + "\nSay which turn is measured and why that sentence is the right one, the way the "
          "other 119 do."
    )


def test_the_baseline_only_shrinks():
    base = set(json.loads(BASELINE.read_text(encoding="utf-8"))["scenarios"])
    fixed = sorted(base - offenders())
    assert not fixed, f"no longer offenders, remove them from {BASELINE.name}: {fixed}"


def test_the_report_PRINTS_the_measured_turn():
    """🔴 THE CALL SITE. The gate stops a new one being authored; it does nothing for the
    author reading a batch that already ran, which is where the 2026-08-23 instance was
    misread. The runner has to say the sentence out loud."""
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    assert "MEASURED TURN is turn" in src, "the report never prints the measured turn"
    at = src.index("MEASURED TURN is turn")
    seg = src[max(0, at - 400):at + 400]
    assert 'sc.get("follow_ups")' in seg, "it prints unconditionally, so it says nothing"
    assert "is SETUP and no bar above reads it" in seg, (
        "it shows the measured turn without saying that `prompt` is not it — which is the "
        "half the author got wrong"
    )


def test_the_runner_and_the_gate_cannot_drift():
    """One rule, one home. The turn loop asserts itself against `measured_turn`, so a change to
    either side fails at run time rather than producing two different answers."""
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    assert "assert turns[-1] == fx.substitute_text(measured_turn(sc))" in src
    assert measured_turn({"prompt": "a", "follow_ups": ["b", "c"]}) == "c"
