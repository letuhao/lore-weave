"""A restore op must have somewhere that shows what it can restore.

    THE INVARIANT. `composition_entity_override_edit` ships an `op=restore` that takes an
    `override_id`; `op=list` with `include_archived=True` is where that id comes from. Every
    other caller of the repo keeps the live-only view.

OWNER RULING 2026-08-31, DQ-T87 (a): BUILD the composition_entity_override discovery path. It was
the LAST live restore family with none — of ten `*_restore` tools the platform ships, this was
the last whose subject could not be listed anywhere in the catalogue.

WHY IT WAS A DEFECT, in the family's own measured words: the only way to hold the id was to have
written it down BEFORE deleting. The sibling family's live run put it exactly right, from the
model itself — "Since I can't see her in the trash (the recycle bin) without an ID, I'll need you
to provide her element ID." That is the correct answer, and the tool is unreachable because of it.

🔴 THE SYNONYMS WERE CONTROLLED BEFORE THEY WERE WRITTEN, because a discovery path the author
cannot phrase is not a discovery path — and the scene_link half of this row proved that by
shipping the wiring and measuring the tool on the wire 0 of 5. Run through the SHIPPED matcher
over the live 316-tool catalogue: the recycle-bin prompts went 0/3 -> 2/3, each a SINGLETON, and
eight neighbouring requests came back BYTE-IDENTICAL. No answerability tie is manufactured.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
import typing
import uuid

from app.db.repositories.derivatives import DerivativesRepo
from app.mcp import server as mcp


def _fn_ast(name: str):
    """The named function's AST, so a guard can read the MESSAGE a wrapped literal builds."""
    tree = ast.parse(pathlib.Path(inspect.getfile(mcp)).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    raise AssertionError(f"{name} not found — has it been renamed?")


def _literal_values(annotation) -> set[str]:
    """Every string in a (possibly Annotated-wrapped) Literal."""
    out: set[str] = set()
    stack = [annotation]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            out.add(node)
            continue
        stack.extend(typing.get_args(node))
    return out


def _built_sql(*, include_archived: bool) -> str:
    """The SQL `list_overrides_for_work` actually builds, captured with a fake pool.

    Driven rather than read: a source grep for `NOT is_archived` is satisfied by the branch that
    is NEVER TAKEN, which is how a sibling guard in this repo passed while the flag was dead."""
    captured: list[str] = []

    class _Conn:
        async def fetch(self, query, *args):
            captured.append(query)
            return []

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    asyncio.run(DerivativesRepo(_Pool()).list_overrides_for_work(
        uuid.uuid4(), include_archived=include_archived))
    assert len(captured) == 1, captured
    return " ".join(captured[0].split())


class TestTheFlagReachesTheQuery:
    def test_the_default_still_hides_archived_overrides(self):
        assert "NOT is_archived" in _built_sql(include_archived=False)

    def test_include_archived_drops_the_filter(self):
        sql = _built_sql(include_archived=True)
        assert "NOT is_archived" not in sql, (
            "the flag was accepted and the query still filters — a recycle bin that shows "
            "nothing deleted is the defect, not the fix")
        assert "FROM entity_override" in sql and "work_id = $1" in sql, (
            "the archived branch lost the scoping the live branch has")

    def test_it_is_KEYWORD_ONLY_so_no_caller_passes_it_by_accident(self):
        sig = inspect.signature(DerivativesRepo.list_overrides_for_work)
        p = sig.parameters["include_archived"]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
        assert p.default is False


class TestEveryOtherCallSiteKeepsTheLiveOnlyView:
    """🔴 ASSERT EVERY CALL SITE. Two production callers must never see an archived override:
    the PACKER (an archived override must not apply to generated prose) and the works router's
    list endpoint. A default is only safe if nothing overrides it by accident."""

    @staticmethod
    def _calls_outside_the_tool() -> list[tuple[str, int, bool]]:
        root = pathlib.Path(inspect.getfile(mcp)).parents[1]   # app/
        found = []
        for py in root.rglob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "list_overrides_for_work"):
                    passes = any(k.arg == "include_archived" for k in n.keywords)
                    found.append((py.name, n.lineno, passes))
        return found

    def test_the_only_caller_passing_the_flag_is_the_discovery_op(self):
        calls = self._calls_outside_the_tool()
        assert calls, "no caller found — this guard is pointing at nothing"
        passing = [(f, ln) for f, ln, p in calls if p]
        assert [f for f, _ in passing] == ["server.py"], (
            f"a caller other than the MCP discovery op passes include_archived: {passing}. "
            "The packer and the works router must keep the live-only view.")

    def test_the_packer_never_asks_for_archived_overrides(self):
        calls = [c for c in self._calls_outside_the_tool() if c[0] == "pack.py"]
        assert calls, "the packer no longer lists overrides — has the read moved?"
        assert all(not p for _, _, p in calls), (
            "the packer would apply a DELETED override to generated prose")


class TestTheToolExposesIt:
    def test_op_list_is_in_the_enum(self):
        """Shape-tolerant on purpose: `op` is declared `Annotated[Literal[...], Field(...)]`, and
        whether pydantic hands back the Annotated or the bare Literal is a library detail. An
        extraction that assumed one shape reported an EMPTY enum and would have read as the tool
        shipping no ops at all."""
        allowed = _literal_values(
            mcp._EntityOverrideEditArgs.model_fields["op"].annotation)
        assert allowed, "no Literal values found — the extraction, not the tool, is broken"
        assert "list" in allowed, (
            f"op=list is not selectable; the enum offers {sorted(allowed)}")
        for op in ("add", "update", "delete", "restore"):
            assert op in allowed, f"adding op=list dropped op={op}"

    def test_include_archived_is_an_argument_of_the_tool(self):
        f = mcp._EntityOverrideEditArgs.model_fields["include_archived"]
        assert f.default is False
        assert "restore" in (f.description or "").lower(), (
            "the argument does not say it is where the restore id comes from, which is the "
            "whole reason it exists")

    def test_the_dispatch_HANDLES_list_rather_than_falling_through_to_restore(self):
        """Before this change the function ENDED with an unguarded op=restore fallthrough. Adding
        a value to the enum without a branch would have sent op=list into restore — and restore
        without an override_id raises, so the failure would have read like a bad argument."""
        src = inspect.getsource(mcp.composition_entity_override_edit)
        i = src.find('args.op == "restore"')
        assert i != -1, "the restore branch is no longer explicit"
        assert 'op == "list"' in src or "op == \"list\"" in src or "list_overrides_for_work" in src[i:], (
            "op=list has no branch of its own and would fall through to restore")

    def test_the_description_names_op_list_as_the_source_of_the_restore_id(self):
        """R1 answerability and the model both read the description. A shipped op nobody is told
        about is the same defect one level up."""
        desc = _tool_meta_description()
        assert "op=list" in desc
        assert "override_id" in desc and "restore" in desc

    def test_the_discovery_synonyms_ship(self):
        syn = _tool_synonyms()
        assert "deleted entity overrides" in syn
        assert "archived entity overrides" in syn

    def test_it_does_NOT_claim_the_restore_phrasings_it_already_owns(self):
        """`restore entity override` was already declared for op=restore. The discovery
        additions must not duplicate an existing phrasing — the tie DQ-T70 measured."""
        syn = _tool_synonyms()
        assert len(syn) == len(set(syn)), f"duplicate synonym: {syn}"


class TestAnEmptyListIsNotAnAnswer:
    """🔴 THE FIRST LIVE RUN CALLED THE OP PERFECTLY AND STILL TOLD THE AUTHOR THE WRONG THING.

    K=5, on the wire 19/19 passes, called 5/5, `include_archived=true` on 5/5 — and every reply
    said some version of "the system reported that no archived overrides exist for this work"
    while the fixture's override sat there archived.

    The model passed the book's AMBIENT (canonical) project_id, which is the wrong Work: an
    override exists only on a DERIVATIVE. `_require_derivative` does not check that despite its
    name, and op=list has no downstream write to fail on, so the canonical project answered
    `{"overrides": [], "ok": true}`. A recycle bin that reports EMPTY when it was handed the
    wrong drawer is worse than one that refuses, because the author stops looking.
    """

    def test_op_list_refuses_a_canonical_work_instead_of_listing_nothing(self):
        src = inspect.getsource(mcp.composition_entity_override_edit)
        i = src.find('op == "list"')
        assert i != -1, "op=list has no branch"
        after = src[i:]
        assert "source_work_id is None" in after, (
            "op=list does not check that the Work is a DERIVATIVE, so a canonical project_id "
            "returns an empty list — which reads to the author as 'nothing was deleted'")
        assert "NOT_A_DERIVATIVE" in after

    def test_the_refusal_NAMES_the_tool_that_finds_the_right_project_id(self):
        """A refusal the caller cannot act on is a dead end. Naming the lookup also ARMS it —
        chat-service's `_tools_named_in_refusal` runs on dispatch results."""

        after = " ".join(n.value for n in ast.walk(_fn_ast("composition_entity_override_edit"))
                        if isinstance(n, ast.Constant) and isinstance(n.value, str))
        assert "composition_list_derivatives" in after, (
            "the refusal does not say how to obtain a derivative project_id")

    def test_the_refusal_names_a_shape_the_runtime_can_actually_deliver(self):
        """🔴 THIS GUARD ASSERTED THE WRONG REMEDY WHEN I WROTE IT THIS MORNING, and the
        measurement that afternoon corrected it. It demanded the refusal warn "do NOT also pass
        book_id", on the belief that passing project_id was right and book_id was the intruder.

        It is the other way round. `composition_list_derivatives` takes EXACTLY ONE of the two —
        probed on the deployed service: book_id alone ACCEPTED, project_id alone ACCEPTED, BOTH
        REFUSED — and chat-service's `_inject_context_ids` fills `book_id` into any tool that
        declares it whenever the turn has a book, which a book-scoped tool always does. So a
        model told to pass project_id sends BOTH and is refused, and no wording about book_id
        can stop the runtime adding it. The store agrees: BOTH is 0 done in 46 attempts.

        The instruction that CAN be followed is to pass nothing and let the ambient book
        through, so that is what the refusal now says and what this asserts."""
        # 🔴 AND IT READ THE SOURCE TEXT, WHICH IS WHY IT WENT RED ON A CORRECT REFUSAL.
        # The message is a wrapped implicit concatenation, so the raw source carries `Do NOT pass
        # " "project_id` — the closing and opening quotes land INSIDE the phrase. Joining the
        # string CONSTANTS is what the model actually receives, and it is immune to rewrapping.
        fn = _fn_ast("composition_entity_override_edit")
        joined = " ".join(n.value for n in ast.walk(fn)
                          if isinstance(n, ast.Constant) and isinstance(n.value, str))
        joined = " ".join(joined.split())
        assert "NO ARGUMENTS" in joined, (
            "the refusal names composition_list_derivatives without saying how to call it in a "
            "way the runtime can deliver")
        assert "Do NOT pass project_id" in joined, (
            "it does not name the thing that breaks the call — passing project_id alongside the "
            "book_id the runtime adds")

    def test_it_says_NOTHING_WAS_LISTED_is_not_nothing_to_list(self):
        """The distinction the whole cycle turns on, stated to the model in words.

        Anchored on a fragment that survives LINE WRAPPING: the sentence is split across two
        adjacent string literals in the source, so the full phrase is not contiguous and an
        assertion on it fails while the shipped message is perfectly correct. A source-level
        guard has to match text the formatter cannot break."""

        after = " ".join(n.value for n in ast.walk(_fn_ast("composition_entity_override_edit"))
                        if isinstance(n, ast.Constant) and isinstance(n.value, str))
        joined = "".join(after.split())
        assert "notthesameasthereben" in joined or "notthesameastherebeingnothingto" in joined, (
            "the refusal does not distinguish 'nothing was listed' from 'nothing to list', "
            "which is the whole reason it refuses instead of returning []")


def _decorator_kwargs():
    """The `meta=require_meta(...)` / description passed at registration, read from the AST so no
    import-time server wiring is needed."""
    src = pathlib.Path(inspect.getfile(mcp)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if n.name != "composition_entity_override_edit":
            continue
        for dec in n.decorator_list:
            if isinstance(dec, ast.Call):
                return dec
    raise AssertionError("the tool registration was not found")


def _tool_meta_description() -> str:
    for kw in _decorator_kwargs().keywords:
        if kw.arg == "description":
            return ast.literal_eval(kw.value)
    raise AssertionError("no description on the registration")


def _tool_synonyms() -> list[str]:
    for kw in _decorator_kwargs().keywords:
        if kw.arg == "meta" and isinstance(kw.value, ast.Call):
            for inner in kw.value.keywords:
                if inner.arg == "synonyms":
                    return list(ast.literal_eval(inner.value))
    raise AssertionError("no synonyms on the registration")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
