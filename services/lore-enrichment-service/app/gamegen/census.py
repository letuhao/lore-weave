"""The provenance census — **where every field in a shipped manifest came from.**

This module exists to answer one question with a number instead of an impression:

> *Is a generated progression system detailed enough to use, or must a human fill
> it in by hand afterwards?*

It is deliberately **not** a quality score. There is no single number for *"is this
a good cultivation system"*, and inventing one would be the shape this pipeline
refuses everywhere else: a figure that looks like evidence and answers a question
nobody asked. What it produces is a **census** — five counts that are each a
different fact, and two ratios that each answer a different question.

## The five origins

``BOOK``    a verified citation — the book says it, and a span proves it
``MODEL``   the model proposed it and a human approved the proposal
``POLICY``  a magnitude from a human-authored band (`PGN-A5`)
``ENGINE``  **nobody chose it.** The engine will fill it because no stage did
``SILENT``  ``not_stated`` — an accountable gap, not a value

## The two ratios, and why one number would not do

**Completeness** = ``1 - ENGINE/total``. *"How much of this manifest did somebody
choose?"* This is the one that answers the user's question: a low value means the
human has to go and fix things by hand at the manifest step, which is exactly the
outcome that makes the pipeline not worth having.

**Groundedness** = ``BOOK / (BOOK + MODEL)``. *"Of what was chosen, how much came
from the book rather than from the model?"* A manifest can be 100% complete and
entirely invented — complete and ungrounded. Collapsing these two into one score
would hide precisely the difference the whole document is about.

`SILENT` is counted apart from both. It is neither chosen nor defaulted: it is a
human saying *"the book does not say"*, which `PGN-A4` makes a complete answer and
S5 makes a refusal on a required field. Folding it into `ENGINE` would read as
*"the engine handled it"*; folding it into the chosen counts would read as *"a
decision was made"*. Neither is true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["Census", "Origin", "census_of"]


class Origin:
    BOOK = "book"
    MODEL = "model"
    POLICY = "policy"
    ENGINE = "engine"
    SILENT = "silent"


@dataclass
class Census:
    book: int = 0
    model: int = 0
    policy: int = 0
    engine: int = 0
    silent: int = 0
    #: ``pointer -> origin`` so a low ratio can be read as *which* fields, not
    #: only *how many*. A census that reported totals alone would tell an author
    #: the manifest is 60% chosen and nothing about what to do next.
    by_field: dict[str, str] = field(default_factory=dict)

    @property
    def chosen(self) -> int:
        return self.book + self.model + self.policy

    @property
    def total(self) -> int:
        return self.chosen + self.engine + self.silent

    @property
    def completeness(self) -> float:
        """How much of the manifest somebody chose. 1.0 = nothing defaulted."""
        return 0.0 if not self.total else round(self.chosen / self.total, 4)

    @property
    def groundedness(self) -> float:
        """Of what was chosen by a person or a model, how much the BOOK supports.

        Excludes ``policy`` deliberately: a magnitude is never in the book
        (`PGN-A5`), so counting it against groundedness would penalise a pipeline
        for obeying its own axiom.
        """
        authored = self.book + self.model
        return 0.0 if not authored else round(self.book / authored, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "book": self.book, "model": self.model, "policy": self.policy,
            "engine_defaulted": self.engine, "not_stated": self.silent,
            "total_fields": self.total,
            "completeness": self.completeness,
            "groundedness": self.groundedness,
        }


def census_of(
    *,
    body: Mapping[str, Any],
    answers_by_id: Mapping[str, Mapping[str, Any]],
    magnitudes: Mapping[str, int],
    default_provenance: Mapping[str, str],
) -> Census:
    """Count the origins of every field in a folded structure + its artifact.

    ``answers_by_id`` maps ``answer_id`` to at least ``{"grounded": bool}`` —
    whether that answer carried a verified citation. The structure records which
    answer produced each cell, so origin is a lookup rather than a guess.
    """
    c = Census()

    def visit(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            if "state" in node and "answer_id" in node:
                if node["state"] == "not_stated":
                    c.silent += 1
                    c.by_field[pointer] = Origin.SILENT
                elif node["state"] == "refused":
                    # An out-of-scope requirement is not a field the engine will
                    # fill — it is a field nothing can fill yet. Counted as
                    # SILENT because that is what it is to a player: absent, and
                    # for a stated reason.
                    c.silent += 1
                    c.by_field[pointer] = Origin.SILENT
                else:
                    a = answers_by_id.get(str(node["answer_id"]), {})
                    if a.get("grounded"):
                        c.book += 1
                        c.by_field[pointer] = Origin.BOOK
                    else:
                        c.model += 1
                        c.by_field[pointer] = Origin.MODEL
                return
            for k, v in node.items():
                visit(v, f"{pointer}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                visit(v, f"{pointer}/{i}")

    visit(dict(body), "")

    for path in magnitudes:
        c.policy += 1
        c.by_field[f"magnitude:{path}"] = Origin.POLICY
    for path in default_provenance:
        c.engine += 1
        c.by_field[f"default:{path}"] = Origin.ENGINE

    return c
