"""`PGN-A2` — the question set, ASSERTED total against the engine's own schema.

Doc 39 v1 claimed a ``schema_fingerprint`` made coverage *computable*. It did
not: comparing a brief's recorded version to the type's version is green for a
brief with **zero questions**, because deleting a question row moves neither
operand. ``NV-2``, the subject cannot vary.

This module is the half that can actually fail. It does **not** re-derive what
the schema contains — deriving it here would be *a second implementation of a
Rust type, a mirror nothing forces to agree*, which is ``CPL-A2``'s objection one
tier up. It reads ``contracts/progression-schema.json``, which is **generated**
from ``ruleset-core`` and drift-tested on the Rust side, and asserts:

    the brief's question key set  ==  the contract's REQUIRED path set

Set equality in both directions, which is the whole point:

* a required path with no question  → the pipeline would never ask, and the
  field would be filled by a default nobody chose;
* a question for a path that is not required  → the reviewer spends one of
  ``PGN-A11``'s ~29 decisions on something the engine will not read.

Boundaries: pure data. No DB, no LLM, no network — so no ``xdist_group`` mark is
owed by its tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "SCHEMA_CONTRACT",
    "Brief",
    "BriefCoverageError",
    "load_contract",
    "load_brief",
    "required_paths",
]

# The repo root from this file: app/gamegen/brief.py -> service -> services -> root
_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_CONTRACT = _ROOT / "contracts" / "progression-schema.json"
_BRIEFS = Path(__file__).resolve().parent / "briefs"


class BriefCoverageError(AssertionError):
    """A brief does not match the schema it claims to interrogate.

    An ``AssertionError`` subclass on purpose: this is not a user input problem
    to be surfaced in an API response, it is a **platform authoring** problem in
    a System-tier artifact, and it should stop a run the way a failed assertion
    does rather than be caught and logged.
    """


@dataclass(frozen=True)
class Question:
    """One question. ``path`` is the position in the engine schema it answers."""

    id: str
    path: str
    ask: str
    answer_shape: str
    # A closed set is carried so the S2 gate can render options rather than a
    # free text box (`PGN-A13`). `None` means prose.
    options: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Brief:
    element_kind: str
    schema_fingerprint: str
    questions: tuple[Question, ...]

    @property
    def coverage(self) -> set[str]:
        """The set of schema positions this brief asks about."""
        return {q.path for q in self.questions}


def load_contract(path: Path | None = None) -> dict:
    p = path or SCHEMA_CONTRACT
    if not p.is_file():
        raise BriefCoverageError(
            f"{p} is missing. It is GENERATED from ruleset-core - run "
            f"`REGEN_PROGRESSION_SCHEMA=1 cargo test -p ruleset-core --test schema_export`. "
            f"This service must never re-derive it: a second implementation of a Rust type "
            f"is a mirror nothing forces to agree (CPL-A2)."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def required_paths(contract: dict) -> set[str]:
    return {p["path"] for p in contract["paths"] if p["askable"] == "required"}


def load_brief(element_kind: str, *, contract: dict | None = None) -> Brief:
    """Load a System-tier brief and **assert** it covers its schema.

    The assertion runs at load, not at use. A brief that is loaded and then
    partially consulted would be a coverage claim nothing checks — which is what
    v1 shipped.
    """
    src = _BRIEFS / f"{element_kind}.json"
    if not src.is_file():
        raise BriefCoverageError(f"no brief for element_kind={element_kind!r} at {src}")
    raw = json.loads(src.read_text(encoding="utf-8"))

    brief = Brief(
        element_kind=raw["element_kind"],
        schema_fingerprint=raw["schema_fingerprint"],
        questions=tuple(
            Question(
                id=q["id"],
                path=q["path"],
                ask=q["ask"],
                answer_shape=q["answer_shape"],
                options=tuple(q["options"]) if q.get("options") else None,
            )
            for q in raw["questions"]
        ),
    )
    assert_covers(brief, contract or load_contract())
    return brief


def assert_covers(brief: Brief, contract: dict) -> None:
    """**The check that can fail.** Set equality, both directions."""
    if brief.schema_fingerprint != contract["fingerprint"]:
        raise BriefCoverageError(
            f"brief `{brief.element_kind}` was authored against schema fingerprint "
            f"{brief.schema_fingerprint[:12]}… and the engine's is "
            f"{contract['fingerprint'][:12]}…. The schema MOVED - a position was added, "
            f"removed, or reclassified. Re-read the contract and update the questions; the "
            f"fingerprint is the one thing that makes that a loud event rather than a silent "
            f"one."
        )

    want = required_paths(contract)
    have = brief.coverage

    missing = sorted(want - have)
    if missing:
        raise BriefCoverageError(
            f"brief `{brief.element_kind}` asks nothing about {missing}. Every REQUIRED "
            f"position needs a question, or the pipeline never asks and the field is filled "
            f"by a default nobody chose - which is the silent-drop class with the author's "
            f"intent in it."
        )

    extra = sorted(have - want)
    if extra:
        raise BriefCoverageError(
            f"brief `{brief.element_kind}` asks about {extra}, which the engine does not list "
            f"as required. Refused rather than ignored: a reviewer facing PGN-A11's ~29 "
            f"decisions must not spend one on a position the engine will never read. If the "
            f"schema now needs it, regenerate the contract; if it does not, drop the question."
        )

    dupes = sorted({q.path for q in brief.questions if
                    sum(1 for x in brief.questions if x.path == q.path) > 1})
    if dupes:
        raise BriefCoverageError(
            f"brief `{brief.element_kind}` asks about {dupes} more than once. Two questions "
            f"for one position give a reviewer two chances to answer it differently, and "
            f"nothing downstream can say which answer won."
        )
