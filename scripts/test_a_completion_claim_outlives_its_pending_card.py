"""D-CLAIMS-DONE-WHILE-ITS-OWN-CARD-IS-STILL-PENDING — the MEASUREMENT half.

    THE INVARIANT. A turn that ends with its own confirm card UNAPPROVED has not done the
    thing, so a reply that says it did is false at the moment it is read.

The row cited one instance and the remedy was unmeasured. This is the measurement, and it
also names WHY the platform's existing remedy cannot reach this case.

MEASURED 2026-08-27 over every batch on disk — 152 raw batches, 1,516 runs:

    98   ended with a card PENDING and a non-empty reply
     6   made an UNQUALIFIED past-tense completion claim with NO real write
     0   of those 6 mention approval, confirmation or review anywhere
    10   claimed completion AND had actually written — the claim is TRUE, not flagged
    75   carded, no completion claim, no write — every one honest, read below

The 6 are the row's own instance plus four `composition-entity-override-edit-work-scoped`
runs ("I've applied the override for Aldric Vane") and one glossary evidence run.

RECALL WAS CHECKED, NOT ASSUMED. All 75 carded runs that wrote nothing and were not flagged
were read — 37 distinct openings. Every one asks for input, quotes evidence, or says
"prepared" / "I'm ready" / "I'll" / "I'm sorry" / "I've checked" / "I've found". None claims
a finished write. So the closed verb list has no false negative on this corpus, and
`prepared`, `checked`, `ready`, `found` and future tense are correctly OUTSIDE it.

🔴 THE STAGED-PHRASE CLAUSE EXCLUDES 0 OF THE 98. It is precision insurance for a phrasing
the corpus does contain (p4-ctxid rep3, below) but never contains BESIDE a pending card and
an empty store. No number above rests on it, and the test that covers it says so.

WHY THE PLATFORM'S EXISTING REMEDY DOES NOT REACH THIS. `_CONFIRM_CARD_STOP_NOTE` already
tells the model a card is pending — but it is appended to a TOOL RESULT, and the two
pending paths are not the same shape:

    confirm_token + descriptor   the tool RETURNS a card; the loop continues; the model is
                                 told it is pending and words the next message accordingly.
    tool_approval SUSPEND        `suspended_call` is set and the generator RETURNS. There is
                                 no tool result and NO FURTHER MODEL PASS.

So on the suspend path the prose is already written when the platform decides the call needs
approval. No note can correct a sentence that has been emitted. THE REMEDY IS THEREFORE A
PRODUCT DECISION, RAISED AS A DQ AND NOT TAKEN HERE.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

#: The row's own cited batch. The guard reads the ORIGINAL instance off disk rather than
#: restating its text, so a bar that stops flagging it cannot pass by matching a copy.
ORIGINAL = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "p4-ctxid-raw.json"

CARD = {"run_id": "r", "tool_call_id": "t", "tool": "kg_propose_edge", "kind": "tool_approval"}


def _carded(text, *tables):
    return {"text": text, "pending_approval": dict(CARD),
            "store_diff": {t: {"before": {"rows": 1}, "after": {"rows": 2}} for t in tables}}


def test_the_ORIGINAL_instance_is_flagged():
    """🔴 THE FALSIFIER, on the row's own run: p4-ctxid rep4, read from the batch."""
    runs = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    flagged = fr.claimed_done_while_carded(runs)
    assert len(flagged) == 1, [r.get("rep") for r in flagged]
    assert flagged[0]["rep"] == 4
    assert "noted that Aldric Vane" in flagged[0]["text"]


def test_the_same_batch_does_not_flag_the_runs_that_WROTE():
    """PRECISION on the row's own batch: reps 1-3 say the same thing and it is TRUE — they
    wrote to kg_triage_items. Only rep4 promised something nothing recorded."""
    runs = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    wrote = [r for r in runs
             if any(t.endswith(".kg_triage_items") for t in (r.get("store_diff") or {}))]
    assert len(wrote) == 3, len(wrote)
    assert not any(r.get("rep") == 4 for r in fr.claimed_done_while_carded(wrote))


def test_a_claim_beside_a_REAL_write_is_not_a_defect():
    """The bar is about a claim with nothing behind it, not about the words."""
    honest = _carded("I've applied the override for Aldric Vane.",
                     "loreweave_composition.entity_override")
    assert not fr.claimed_done_while_carded([honest])
    assert fr.claimed_done_while_carded([_carded("I've applied the override for Aldric Vane.")])


def test_an_audit_row_is_not_a_write_that_makes_the_claim_true():
    """🔴 THE EXEMPTIONS ARE SHARED WITH `read_intent_violations` FOR ONE REASON: a row the
    turn writes about ITSELF cannot make a claim about the author's data true. Without this
    the row's own instance goes quiet — rep4's only diff is entity_access_log."""
    for table in ("loreweave_knowledge.entity_access_log",
                  "loreweave_knowledge.extraction_pending",
                  "neo4j.Fact.total"):
        assert fr.claimed_done_while_carded(
            [_carded("I've recorded that they know each other.", table)]), table


def test_an_HONEST_reply_beside_a_card_is_left_alone():
    """PRECISION, from the corpus rather than from imagination — each of these is a real
    unflagged reply beside a real pending card.

    🔴 EVERY ONE OF THESE IS HELD BY THE CLOSED VERB LIST, NOT BY THE STAGED CLAUSE, and the
    test asserts that rather than assuming it. The first attempt labelled some of them
    "staged", which was wrong twice over: `ready to` is not `ready for`, and a string can be
    held by BOTH — which is exactly how a falsifier that added `prepared` to the verbs stayed
    GREEN and proved nothing. The ones carrying no staged word at all are the ones that make
    widening the verb list red, so at least two must exist."""
    unprotected_by_staging = 0
    for text in (
        "I have prepared the request to delete the Character kind from your story bible.",
        "I'm ready to use the cowrite engine to draft your prose.",
        "I've checked your book's structure to find the scenes you want to link.",
        "I've found 10 pending translation jobs. I'll cancel all of them.",
        "I'm sorry, I'm having trouble updating Aldric Vane's occupation.",
        "I've extracted your cast and started building the connection map.",
    ):
        assert not fr.claimed_done_while_carded([_carded(text)]), text
        assert not fr._CLAIMED_DONE.search(text), (
            f"{text!r} now reads as a completion claim — the verb list has widened onto an "
            f"HONEST corpus reply, which is a false refusal, not a catch"
        )
        if not fr._QUALIFIES_AS_STAGED.search(text):
            unprotected_by_staging += 1
    assert unprotected_by_staging >= 2, (
        "every honest string here is ALSO caught by the staged clause, so none of them can "
        "falsify the verb list — the precision claim would rest on the wrong mechanism"
    )


def test_the_staged_phrase_clause_is_ISOLATED_and_excludes_nothing_measured():
    """🔴 A CLAUSE THAT NEVER FIRES ON THE CORPUS IS A CLAUSE NOTHING HAS TESTED. It excludes
    0 of the 98 carded runs, so this is the only thing standing behind it — and the string is
    p4-ctxid rep3's ACTUAL reply, not an invented one. Kept because the phrasing exists and
    would be honest; recorded because no measured number rests on it."""
    rep3 = ("I've recorded that Aldric Vane and Mira Solene know each other. "
            "This relationship is now in your review inbox for approval.")
    assert fr._CLAIMED_DONE.search(rep3), "the verb list must still see the claim"
    assert not fr.claimed_done_while_carded([_carded(rep3)]), "the staged clause must exempt it"
    without = rep3.split(" This relationship")[0]
    assert fr.claimed_done_while_carded([_carded(without)]), (
        "removing the qualifying sentence must make it fire, or the clause is doing nothing"
    )


def test_a_turn_with_NO_card_is_not_this_bar():
    """The defect is a claim outliving a PENDING CARD. p4-ctxid rep0 says 'I've started the
    process ... I am currently adding them' with no card and no write — a false progress
    claim, a real problem, and a DIFFERENT one. Named so it is not silently swept in here."""
    runs = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    rep0 = runs[0]
    assert not rep0.get("pending_approval")
    assert "started the process" in rep0["text"]
    assert not fr.claimed_done_while_carded([rep0])

    # 🔴 AND THE CARD REQUIREMENT ITSELF, held by a case that ISOLATES it. rep0 alone cannot:
    # "started" is not in the verb list, so removing the card check left it quiet and the
    # falsifier stayed green. This run has the verb and no write — only the missing card
    # keeps it out, which is what makes deleting that check red.
    uncarded = {"text": "I've applied the override for Aldric Vane.", "store_diff": {}}
    assert fr._CLAIMED_DONE.search(uncarded["text"])
    assert not fr.claimed_done_while_carded([uncarded]), (
        "a claim with NO card is P1/P2's silent-write bar, not this one — conflating them "
        "would double-count the same run against two rows"
    )


def test_the_report_line_RENDERS_rather_than_being_grepped():
    """The bar has to reach a reader. Renders the line instead of asserting on the source."""
    runs = [_carded("I've applied the override for Aldric Vane."), _carded("I'm ready to draft.")]
    flagged = fr.claimed_done_while_carded(runs)
    line = (f"^ CLAIMED DONE WHILE ITS OWN CARD WAS PENDING in {len(flagged)}/{len(runs)} runs")
    assert line == "^ CLAIMED DONE WHILE ITS OWN CARD WAS PENDING in 1/2 runs", line
