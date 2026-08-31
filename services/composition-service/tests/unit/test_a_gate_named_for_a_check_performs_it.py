"""A helper named for a check must perform it, or its callers inherit a gate that is not there.

    THE INVARIANT. Every tool whose subject exists ONLY on a derivative Work verifies
    `source_work_id` itself. No caller relies on a helper's NAME for that.

MEASURED 2026-09-01. `_require_derivative` was documented as "Gate EDIT + resolve the derivative
Work (source_work_id set) ... or a sentinel dict via raise for the not-accessible /
NOT-A-DERIVATIVE cases". Its body gated the book and fetched the Work. It never read
`source_work_id` — not once, in any version.

Three of its six callers re-checked it on the very next line, which is evidence the authors knew
the helper did not. THREE DID NOT: composition_entity_override_update, _delete and _restore. They
survived only because a canonical Work owns no override rows, so they failed late and vaguely as
"not found or not accessible" — the caller told the wrong thing about their own book.

🔴 THE READ OP HAD NO SUCH LUCK, which is how this was found: op=list on
composition_entity_override_edit has no downstream write to fail on, so a canonical project_id
returned `{"overrides": [], "ok": true}` on 5 of 5 live runs — an empty recycle bin, which is the
worst possible answer to "what did I delete".
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.mcp import server as mcp

#: The ops whose subject exists only on a derivative Work.
DERIVATIVE_ONLY = (
    "composition_entity_override_add",
    "composition_entity_override_update",
    "composition_entity_override_delete",
    "composition_entity_override_restore",
    "composition_entity_override_edit",
    "composition_divergence_spec_update",
)


def _fn(name: str) -> ast.AST:
    tree = ast.parse(pathlib.Path(inspect.getfile(mcp)).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} not found — has it been renamed?")


class TestEveryDerivativeOnlyOpChecksForItself:
    def test_each_one_reads_source_work_id(self):
        missing = []
        for name in DERIVATIVE_ONLY:
            src = ast.unparse(_fn(name))
            if "source_work_id" not in src:
                missing.append(name)
        assert not missing, (
            f"{missing} operate on a subject that exists ONLY on a derivative Work and never "
            "check source_work_id. They inherit a gate from a helper that does not perform one, "
            "and fail late as 'not found or not accessible' — or, for a READ, return an empty "
            "list that reads as 'there is nothing there'.")

    def test_each_one_answers_NOT_A_DERIVATIVE(self):
        """A check that refuses without naming the reason sends the caller nowhere."""
        silent = [n for n in DERIVATIVE_ONLY if "NOT_A_DERIVATIVE" not in ast.unparse(_fn(n))]
        assert not silent, f"{silent} check the Work kind but do not say so in the refusal"

    def test_the_refusals_name_the_tool_that_finds_the_right_id(self):
        """Measured on c-override8: naming composition_list_derivatives is what moves the model,
        and naming a tool also ARMS it. A refusal that only says 'wrong Work' is a dead end."""
        dead = [n for n in DERIVATIVE_ONLY
                if "NOT_A_DERIVATIVE" in ast.unparse(_fn(n))
                and "composition_list_derivatives" not in ast.unparse(_fn(n))
                and "composition_create_derivative" not in ast.unparse(_fn(n))]
        assert not dead, (
            f"{dead} refuse without naming how to obtain a derivative project_id")


class TestTheHelperNoLongerClaimsWhatItDoesNotDo:
    def test_it_is_not_named_for_a_check_it_does_not_make(self):
        assert not hasattr(mcp, "_require_derivative"), (
            "`_require_derivative` is back. The name promises a derivative check; if it is "
            "reintroduced it must READ source_work_id, or callers will trust it again.")
        assert hasattr(mcp, "_gate_edit_and_resolve_work")

    def test_if_it_ever_claims_the_check_it_must_perform_it(self):
        """The rule, not the rename: a helper may be called `_require_derivative` again the day
        it actually checks. This binds the two together instead of banning a word."""
        for name in ("_require_derivative", "_gate_edit_and_resolve_work"):
            fn = getattr(mcp, name, None)
            if fn is None:
                continue
            src = inspect.getsource(fn)
            body = src[src.index('"""', src.index('"""') + 3) + 3:]  # past the docstring
            claims = "derivative" in name.lower()
            performs = "source_work_id" in body
            assert not (claims and not performs), (
                f"{name} is named for the derivative check and its BODY never reads "
                "source_work_id — which is exactly the defect this guard exists for")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
