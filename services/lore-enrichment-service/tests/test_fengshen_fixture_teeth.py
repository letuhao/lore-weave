"""The Fengshen ITEM fixture must still have its teeth.

WHY THIS EXISTS. ``PGN-A8``: a fixture that already contains the answers makes every
stage vacuous. The corpus in ``tests/fixtures/fengshen/`` is authored to be
answerable-but-incomplete, and every gap in it is deliberate. Nothing stops a future
editor from "improving" a page and silently disarming the stage it exists to test —
except this file.

It checks three classes of thing, and each has already caught a real defect in the
sibling wuxia fixture:

  1. **the teeth are where the answer key says they are** — every ``present`` string
     appears in the file claimed, every ``absent_everywhere`` string appears nowhere.
  2. **nothing leaked** — the answer key lives OUTSIDE the corpus, and no fixture
     metadata may appear inside it. The wuxia fixture's first draft carried its roles
     in HTML comments inside the corpus files, which DEFEATED the tooth that depended
     on a term being absent from the very page the comment named it in.
  3. **the provenance map is total** — ``PGN-A14`` lets ``says[]`` cite only
     ``is_authored_source=true``, so a corpus file with no flag is a file whose
     citations cannot be judged.

Matching folds whitespace, because the corpus is line-wrapped prose and
``interrogate._fold`` folds whitespace for exactly the same reason: a quote that
spans a line break is still the same quote. Using a stricter match here would make
this test disagree with the pipeline it guards.
"""
from __future__ import annotations

import json
import pathlib

import pytest

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "fengshen"
TEETH = json.loads((FIXTURE / "fixture_teeth.json").read_text(encoding="utf-8"))


def _fold(text: str) -> str:
    """Whitespace-insensitive projection — mirrors ``interrogate._fold``'s whitespace half."""
    return "".join(ch for ch in text if not ch.isspace())


def _corpus() -> dict[str, str]:
    return {
        p.relative_to(FIXTURE).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(FIXTURE.rglob("*.md"))
        if p.name != "README.md"
    }


CORPUS = _corpus()
FOLDED = {k: _fold(v) for k, v in CORPUS.items()}
TOOTH_IDS = [t["id"] for t in TEETH["teeth"]]


def test_the_corpus_is_not_empty_and_has_both_halves():
    assert CORPUS, "no corpus files found — the fixture path is wrong"
    assert any(k.startswith("book/") for k in CORPUS), "no authored source"
    assert any(k.startswith("wiki/") for k in CORPUS), "no derived wiki"


def test_every_corpus_file_declares_its_provenance():
    """PGN-A14 — a file with no is_authored_source flag has uncheckable citations."""
    declared = set(TEETH["provenance"]) - {"_rule"}
    assert declared == set(CORPUS), (
        f"provenance map and corpus disagree: {declared ^ set(CORPUS)}"
    )


@pytest.mark.parametrize("tooth_id", TOOTH_IDS)
def test_each_tooth_is_present_where_the_answer_key_says(tooth_id: str):
    tooth = next(t for t in TEETH["teeth"] if t["id"] == tooth_id)
    for filename, needles in tooth.get("present", {}).items():
        assert filename in CORPUS, f"{tooth_id} names a file that does not exist: {filename}"
        for needle in needles:
            assert _fold(needle) in FOLDED[filename], (
                f"{tooth_id} requires {needle!r} in {filename} and it is gone. "
                f"This tooth tests: {tooth['tests']}"
            )


@pytest.mark.parametrize("tooth_id", TOOTH_IDS)
def test_each_tooth_is_absent_where_the_answer_key_says(tooth_id: str):
    """The absence teeth are the ones an editor disarms by being helpful."""
    tooth = next(t for t in TEETH["teeth"] if t["id"] == tooth_id)
    for needle in tooth.get("absent_everywhere", []):
        hits = [f for f, txt in FOLDED.items() if _fold(needle) in txt]
        assert not hits, (
            f"{tooth_id} requires {needle!r} to appear NOWHERE, but it is in {hits}. "
            f"This tooth tests: {tooth['tests']}"
        )


def test_no_fixture_metadata_leaks_into_the_corpus():
    """Metadata about a test must never live inside the thing under test."""
    forbidden = ("fixture_teeth", "answer key", "absent_everywhere", "PGN-A", "ENR-A",
                 "ICT-A", "EPL-A", "tooth", "teeth")
    for filename, text in CORPUS.items():
        for token in forbidden:
            assert token not in text, (
                f"{token!r} leaked into {filename}. The answer key lives OUTSIDE the corpus."
            )


def test_the_grade_foreclosure_is_stated_not_merely_missing():
    """I2 is the sharpest tooth, and its value depends on being STATED.

    A corpus that merely omits a grade ladder is indistinguishable from one nobody
    asked about. This corpus says out loud that no ranking exists — which is a
    stronger and different fact, and the pipeline must be able to tell them apart.
    """
    assert _fold("寶各有用，未嘗較其次第") in FOLDED["book/ch65_zhuxian.md"]
    assert _fold("書中未嘗分品第") in FOLDED["wiki/fabao_zonglun.md"]


def test_the_corpus_states_no_treasure_ranking_vocabulary():
    """The guard behind I2. If any of these appear, the Ladder planner can cite instead
    of enrich, and the whole enrichment argument goes untested."""
    banned = ["品階", "上品", "中品", "下品", "一品", "九品", "靈寶", "先天", "後天"]
    for term in banned:
        hits = [f for f, txt in FOLDED.items() if term in txt]
        assert not hits, f"grade vocabulary {term!r} appeared in {hits} — I2 is disarmed"
