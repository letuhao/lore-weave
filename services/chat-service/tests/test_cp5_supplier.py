"""CP-5.4 — every input declares WHO SUPPLIES IT, and the refusal says so.

🔴 **ONE SENTENCE WAS COVERING TWO OPPOSITE SITUATIONS.** Measured over 266 missing-argument
failures across 87 sessions: the single largest case is **`book_read` missing `book_id` — 78 calls
over 46 sessions** — and `book_id` is a **context** value. The runtime fills it from the ambient
book and has none outside a book studio. The model was told *"missing required argument book_id"*,
which reads as *you forgot something* when the truth is *I owe you this and do not have it* — and
the model cannot act on the difference.

The rest (`body`, `items`, `base_version`) are genuinely `model`-supplied content, and for those
that message is already right. Telling them apart is the whole row, and it is the same defect as
`ok:false` covering both a failure and a suspension (5.5), one layer up.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.toolcontract import SUPPLIERS, declared_supplier, resolve_contract

REGISTRY = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-tool-contracts.json")


def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def contract_for(tool: str) -> dict:
    block, _ = resolve_contract({"name": tool}, registry())
    return block


class TestTheSupplierIsReadableFromTheContract:

    def test_THE_DOMINANT_REAL_FAILURE_IS_A_CONTEXT_VALUE(self):
        """`book_read.book_id` — 78 calls / 46 sessions, the largest single missing-argument
        class in the corpus. If this ever reads `model`, the row's whole premise is gone."""
        assert declared_supplier(contract_for("book_read"), "book_id") == "context"

    def test_A_CONTENT_ARGUMENT_IS_THE_MODELS(self):
        assert declared_supplier(contract_for("book_list"), "kind") == "model"

    def test_A_PLAN_BOUND_ARGUMENT_READS_AS_OWED_BY_THE_RUNTIME(self):
        assert declared_supplier(contract_for("book_read"), "chapter_id") == "plan"

    def test_AN_UNDECLARED_PARAMETER_IS_NONE_NOT_A_GUESS(self):
        assert declared_supplier(contract_for("book_read"), "no_such_param") is None
        assert declared_supplier({}, "book_id") is None

    def test_EVERY_DECLARED_SUPPLIER_NAMES_A_KNOWN_SIDE(self):
        """A supplier outside the vocabulary would silently read as `model`'s opposite or as
        nothing at all, and the message would go back to being generic without anyone noticing."""
        for tool, block in registry()["contracts"].items():
            for param in (block.get("argument_supplier") or {}):
                got = declared_supplier(block, param)
                assert got in SUPPLIERS, f"{tool}.{param} declares {got!r}"

    def test_THE_RUNTIME_IS_PREFERRED_OVER_THE_MODEL_WHEN_BOTH_APPEAR(self):
        """`"context | model"` means the runtime owes it and the model may also pass it — the
        runtime wins, or the work goes back to the model exactly where it need not.

        🔴 The first version of this asserted `"context | plan"` → `context`, which is true under
        ANY ordering of the three suppliers, so the falsifier that reordered them left the guard
        green: *"the guard requires nothing"*. The case has to be one where the order DECIDES.
        """
        assert declared_supplier(
            {"argument_supplier": {"x": "context | model — either"}}, "x") == "context"
        assert declared_supplier(
            {"argument_supplier": {"x": "plan | model — either"}}, "x") == "plan"
        assert declared_supplier(
            {"argument_supplier": {"x": "model — only the caller knows"}}, "x") == "model"

    def test_PROSE_AFTER_THE_DASH_IS_NOT_PARSED_FOR_SUPPLIERS(self):
        """The declaration is `supplier — explanation`, and the explanation is for a human.

        🔴 The first version used `"context — … the model …"`, where reading the prose ALSO yields
        `context` (it sorts first), so parsing the whole string changed nothing and the guard could
        not fail. The discriminating case is a MODEL-supplied input whose prose mentions context:
        parse the prose and the answer flips to `context`, handing the runtime an argument only the
        caller can write.
        """
        got = declared_supplier(
            {"argument_supplier": {"x": "model — the caller writes this from context they hold"}},
            "x")
        assert got == "model", "the explanation is for a human and must not decide the supplier"


class TestTheRefusalTellsTheModelWhoOwesIt:

    def test_THE_MESSAGE_DISTINGUISHES_OWED_FROM_MISSING(self):
        """A source-level check on the shipped path: the branch must exist and must key off the
        DECLARED supplier, not off a list of tool names kept in the stream module."""
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert "declared_supplier(_c_block, a)" in src, (
            "the missing-argument message does not consult the declared supplier, so the two "
            "opposite situations still share one sentence"
        )
        assert "NOT yours to invent" in src
        assert 'if declared_supplier(_c_block, a) in ("context", "plan")' in src or \
               'declared_supplier(_c_block, a) in ("context", "plan")' in src

    def test_A_MODEL_SUPPLIED_ARGUMENT_KEEPS_THE_ORIGINAL_MESSAGE(self):
        """`body` and `items` are the model's to write. Rewriting their message as *"the runtime
        owes you this"* would be the same error pointed the other way."""
        block = contract_for("book_list")
        owed = [p for p in ("kind", "limit")
                if declared_supplier(block, p) in ("context", "plan")]
        assert owed == [], f"{owed} would wrongly be reported as runtime-owed"
