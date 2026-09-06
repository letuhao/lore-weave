"""A tool that refuses "EXACTLY ONE" must DECLARE the group, or the runtime will build the shape.

THE INVARIANT. Mutual exclusivity is a fact about the tool, and the only party that can act on
it is the one assembling the arguments. A tool that keeps it in prose is telling the model
something the runtime never hears.

🔴 MEASURED 2026-09-01. `composition_list_derivatives` said "give EXACTLY ONE of book_id or
project_id" in its description and in its refusal, and chat-service's `_inject_context_ids`
supplied both anyway on every studio book turn. Live K=5: 24 of 24 calls carried both and every
one was refused; store-wide, 0 done in 46 attempts. The cycle before had rewritten the refusal
to say "call it with NO ARGUMENTS" and the live run did not move, because an empty call is
exactly what the runtime fills.

This guard is the census, not the instance: it finds every tool in this server that refuses
EXACTLY ONE and requires the declaration. It found `composition_generate` — outline_node_id /
chapter_id, where chapter_id is also a runtime-filled context id — which nothing had reported.
"""
from __future__ import annotations

import ast
import inspect
import re
import pathlib

from app.mcp import server as mcp

TREE = ast.parse(pathlib.Path(inspect.getfile(mcp)).read_text(encoding="utf-8"))

#: Arguments chat-service's `_inject_context_ids` can supply. A group made only of arguments the
#: runtime never touches cannot be completed by it — the declaration is still correct to have,
#: but this file's failure mode does not apply.
RUNTIME_FILLED = {"book_id", "chapter_id", "project_id"}


def _tools():
    """(name, decorator meta kwargs, function node) for every @mcp_server.tool in the module."""
    for n in ast.walk(TREE):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in n.decorator_list:
            if not (isinstance(dec, ast.Call) and ast.unparse(dec.func).endswith("tool")):
                continue
            name, meta = None, None
            for kw in dec.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    name = kw.value.value
                elif kw.arg == "meta":
                    meta = kw.value
            if name:
                yield name, meta, n


def _declared_groups(meta_node) -> list[list[str]]:
    if not isinstance(meta_node, ast.Call):
        return []
    for kw in meta_node.keywords:
        if kw.arg == "exclusive_args":
            try:
                return [list(g) for g in ast.literal_eval(kw.value)]
            except Exception:  # noqa: BLE001 — a non-literal is a failure to declare
                return []
    return []


#: Every args-model class in the module, by name, with its field names.
_MODELS = {n.name: {t.target.id for t in n.body
                    if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)}
           for n in ast.walk(TREE) if isinstance(n, ast.ClassDef)}


def _accepted_args(fn) -> set[str]:
    """Every argument name the tool ACCEPTS: direct parameters, plus the fields of the args
    model it is annotated with (this server uses both shapes)."""
    names: set[str] = set()
    for a in list(fn.args.args) + list(fn.args.kwonlyargs):
        names.add(a.arg)
        if a.annotation is not None:
            names |= _MODELS.get(ast.unparse(a.annotation).strip(), set())
    return names


def _own_exclusive_pairs(fn) -> list[tuple[str, str]]:
    """The EXACTLY-ONE rules this tool states about ITS OWN arguments.

    🔴 THE FIRST VERSION OF THIS FUNCTION REPORTED FIVE TOOLS AND EVERY ONE WAS WRONG.
    It searched for the phrase "EXACTLY ONE OF" anywhere in the body, and the four
    composition_entity_override_* tools plus the unified edit tool all carry it inside a
    refusal that describes ANOTHER tool's rule ("call composition_list_derivatives ... it takes
    EXACTLY ONE of book_id or project_id"). A census that counts a tool for quoting someone
    else's contract is measuring its own pattern.

    The discriminator is ownership: the pair is this tool's own only if this tool ACCEPTS both
    arguments. The override tools do not declare book_id at all.

    Reads string CONSTANTS rather than source text, so a reflow cannot break the match.
    """
    joined = " ".join(
        c.value for c in ast.walk(fn)
        if isinstance(c, ast.Constant) and isinstance(c.value, str))
    joined = " ".join(joined.split())
    mine = _accepted_args(fn)
    pairs = []
    for m in re.finditer(r"EXACTLY ONE of ([a-z_]+)\s*(?:or|/)\s*([a-z_]+)", joined, re.I):
        a, b = m.group(1), m.group(2)
        if a in mine and b in mine:
            pairs.append(tuple(sorted((a, b))))
    return sorted(set(pairs))


class TestExclusivityIsDeclaredNotJustDescribed:
    def test_every_tool_that_refuses_exactly_one_declares_the_group(self):
        undeclared = [name for name, meta, fn in _tools()
                      if _own_exclusive_pairs(fn) and not _declared_groups(meta)]
        assert not undeclared, (
            f"{undeclared} refuse 'EXACTLY ONE of ...' in their own body and declare no "
            "exclusive_args. The runtime assembling the call cannot read prose, so it fills "
            "both and the tool refuses a shape no caller chose — measured 24/24 on "
            "composition_list_derivatives.")

    def test_the_census_still_SEES_the_two_it_was_built_from(self):
        """🔴 A TIGHTENED CENSUS CAN TIGHTEN TO NOTHING. The first version matched the
        phrase anywhere and reported five tools, all of them quoting another tool's rule. The
        fix — require the tool to accept both arguments — could equally well have matched zero,
        and then the guard above would pass forever while declaring nothing.

        So the detector is asserted against the two instances the live runs actually paid for."""
        owns = {name: _own_exclusive_pairs(fn) for name, _, fn in _tools()}
        assert owns.get("composition_list_derivatives") == [("book_id", "project_id")]
        assert owns.get("composition_generate") == [("chapter_id", "outline_node_id")]
        quoting = [n for n in ("composition_entity_override_add", "composition_entity_override_edit")
                   if owns.get(n)]
        assert not quoting, (
            f"{quoting} are counted as owning an EXACTLY-ONE rule. They only QUOTE "
            "composition_list_derivatives' rule in a refusal, and neither takes book_id — the "
            "over-match this detector was corrected for")

    def test_a_declared_group_names_arguments_the_tool_actually_has(self):
        """A typo in a group is silent: the guard never fires and the fill goes through."""
        wrong = []
        for name, meta, fn in _tools():
            groups = _declared_groups(meta)
            if not groups:
                continue
            accepted = _accepted_args(fn)
            for g in groups:
                for a in g:
                    if a not in accepted:
                        wrong.append((name, a))
        assert not wrong, (
            f"{wrong} declare an exclusive argument the tool does not take — the group can "
            "never be satisfied, so the guard silently never fires")

    def test_the_two_measured_groups_are_the_ones_on_the_wire(self):
        """Names the instances, so a rename cannot quietly drop a declaration the live runs paid
        for. Both groups are made of RUNTIME-FILLED ids, which is what made them reachable."""
        got = {name: _declared_groups(meta) for name, meta, _ in _tools() if _declared_groups(meta)}
        assert got.get("composition_list_derivatives") == [["book_id", "project_id"]]
        assert got.get("composition_generate") == [["outline_node_id", "chapter_id"]]
        for name, groups in got.items():
            assert any(set(g) & RUNTIME_FILLED for g in groups), (
                f"{name} declares a group the runtime cannot complete — harmless, but check it "
                "was not meant to name a context id")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
