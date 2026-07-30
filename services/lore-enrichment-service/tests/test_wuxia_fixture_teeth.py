"""The 武俠 POC-1 corpus fixture must stay ABLE TO DEFEAT the pipeline.

``PGN-A8`` — *a fixture that already contains the answers makes every stage vacuous.*
That is ``NV-1`` applied to test **data** rather than to a check, and it has the same
failure mode: a corpus quietly "improved" into completeness makes every downstream stage
pass while proving nothing, and **nothing goes red**.

So the gaps are assets, and this module guards them. Each ``R*`` row in
``fixtures/wuxia/fixture_teeth.json`` names a stage of doc 39's pipeline and the exact
token whose presence — or **absence** — is what makes that stage's test non-vacuous.

Why the answer key is a sidecar and not a header comment
--------------------------------------------------------
The first draft of this fixture carried its role notes as ``<!-- fixture role: ... -->``
inside each corpus file. That **defeated R6**: the comment in ``neigong.md`` named 罡元,
and 罡元's whole job is to be a realm no page places in sequence — so the answer was
sitting inside the one page it had to be absent from. Every file also carried
``<!-- source: ... is_authored_source = FALSE -->``, handing the model the provenance
``PGN-A14`` exists to test.

Metadata about a test must never live inside the thing under test.
``test_no_fixture_metadata_leaks_into_the_corpus`` is the mechanism, because noticing it
once is not one.

No DB, no port, no network — deliberately no ``xdist_group`` mark.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "wuxia"
TEETH = json.loads((FIXTURE_DIR / "fixture_teeth.json").read_text(encoding="utf-8"))

CORPUS_FILES = sorted(k for k in TEETH["provenance"] if not k.startswith("_"))


def _read(rel: str) -> str:
    return (FIXTURE_DIR / rel).read_text(encoding="utf-8")


def _tooth(tid: str) -> dict:
    for t in TEETH["teeth"]:
        if t["id"] == tid:
            return t
    raise AssertionError(f"no tooth {tid}")


# ── the corpus is intact ─────────────────────────────────────────────────────


def test_every_declared_corpus_file_exists() -> None:
    missing = [f for f in CORPUS_FILES if not (FIXTURE_DIR / f).is_file()]
    assert not missing, f"fixture_teeth.json declares files that do not exist: {missing}"


def test_no_undeclared_corpus_file() -> None:
    """A file added to the corpus without a provenance row is a file whose
    ``is_authored_source`` nobody decided — and ``PGN-A14`` says ``says[]`` may cite only
    authored sources. An undeclared file is therefore uncitable *or* silently trusted,
    and which one it is would be an accident."""
    on_disk = {
        f"{d}/{p.name}"
        for d in ("book", "wiki")
        for p in (FIXTURE_DIR / d).glob("*.md")
    }
    undeclared = sorted(on_disk - set(CORPUS_FILES))
    assert not undeclared, (
        f"corpus files with no provenance row in fixture_teeth.json: {undeclared}. "
        "Add one — is it an authored source, or somebody's summary?"
    )


# ── the answer key stays OUT of the corpus ───────────────────────────────────


@pytest.mark.parametrize("rel", CORPUS_FILES)
def test_no_fixture_metadata_leaks_into_the_corpus(rel: str) -> None:
    """The defect this fixture actually shipped, and the reason the sidecar exists.

    In-world ``<!-- 待補 -->`` markers are legitimate content — a real reader wiki has
    them, and their presence is part of what makes the corpus honestly incomplete. What
    may never appear is metadata *about the test*.
    """
    body = _read(rel)
    for banned in ("fixture role", "is_authored_source", "PGN-A", "R6", "answer key"):
        assert banned not in body, (
            f"{rel} contains test metadata ({banned!r}). The corpus is the thing under "
            "test; the answer key belongs in fixture_teeth.json. This exact leak broke "
            "R6 once — the comment naming 罡元 sat inside the page 罡元 must be absent from."
        )


# ── each tooth is still sharp ────────────────────────────────────────────────


@pytest.mark.parametrize("tooth", TEETH["teeth"], ids=lambda t: t["id"])
def test_required_tokens_are_present(tooth: dict) -> None:
    for rel, tokens in tooth.get("present", {}).items():
        body = _read(rel)
        for tok in tokens:
            assert tok in body, (
                f"{tooth['id']} is blunt: {tok!r} is gone from {rel}. "
                f"That tooth tests: {tooth['tests']}"
            )


@pytest.mark.parametrize("tooth", TEETH["teeth"], ids=lambda t: t["id"])
def test_required_absences_hold(tooth: dict) -> None:
    """**The half that actually rots.** A missing token is loud — a stage stops finding
    what it needs. An *added* token is silent: the corpus simply becomes more helpful,
    and the stage it was meant to defeat starts passing for the wrong reason."""
    for rel, tokens in tooth.get("absent", {}).items():
        body = _read(rel)
        for tok in tokens:
            assert tok not in body, (
                f"{tooth['id']} is DEFEATED: {tok!r} appeared in {rel}, where it must "
                f"not be. That tooth tests: {tooth['tests']}. {tooth.get('note','')}"
            )

    for tok in tooth.get("absent_everywhere", []):
        hits = [rel for rel in CORPUS_FILES if tok in _read(rel)]
        assert not hits, (
            f"{tooth['id']} is DEFEATED: {tok!r} appears in {hits}. It must appear "
            f"NOWHERE — {tooth.get('note','')}"
        )


@pytest.mark.parametrize("tooth", TEETH["teeth"], ids=lambda t: t["id"])
def test_present_once_is_actually_once(tooth: dict) -> None:
    """``R2``'s pattern is load-bearing precisely because it is stated **once**. Stated
    twice, an S2 answer could cite either occurrence and the fold's expansion would no
    longer be the only path to 15 tier names."""
    for rel, tok in tooth.get("present_once", {}).items():
        n = _read(rel).count(tok)
        assert n == 1, f"{tooth['id']}: {tok!r} appears {n}× in {rel}, expected exactly 1"


# ── the corpus states no rule-shaped magnitude ───────────────────────────────


def test_the_progression_page_states_no_arabic_number() -> None:
    """``PGN-A5``'s subject. 內功 is the page a generator would mine for tier caps, and
    it must offer none. Section headings are stripped first — ``## 2.`` is document
    structure, not content.

    Chinese numerals are deliberately NOT banned: 三重 is *cardinality* (how many
    sub-levels), which ``PGN-A5`` explicitly permits. What must be absent is a magnitude
    — and in this corpus every magnitude that exists is narrative (``R8``) and lives in
    the book, never in the rules page.
    """
    body = _read("wiki/neigong.md")
    content = "\n".join(
        ln for ln in body.splitlines() if not ln.lstrip().startswith(("#", ">", "1.", "2.", "3.", "4."))
    )
    digits = [c for c in content if c.isdigit()]
    assert not digits, (
        f"wiki/neigong.md contains Arabic digits {digits} outside its structure. "
        "A number on the progression page is a magnitude the model can copy instead of "
        "the policy computing it — which is exactly the leak PGN-A5 forbids."
    )
