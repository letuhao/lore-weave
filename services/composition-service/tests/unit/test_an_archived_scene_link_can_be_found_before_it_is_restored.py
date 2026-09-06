"""A restore op must have somewhere that shows what is restorable.

    THE INVARIANT. `composition_list_outline`'s `include_archived` reaches the scene-links as
    well as the nodes, so an author (or the model) can SEE an archived edge before asking for it
    back. Every other caller keeps the live-only view.

OWNER RULING 2026-08-31, DQ-T44 (a): "wire `include_archived` through to
scene_links.list_by_project. One existing flag reaching one more query."

WHY IT WAS A DEFECT. `composition_scene_link_edit` ships ops ['create','delete','restore'] and
NOTHING lists what `restore` can act on — `list_by_project` is repo/router-only, never MCP — so
the only way to hold the id is to have written it down before deleting. Measured live on the
sibling family: the model correctly answers "I can't see her in the trash without an ID".

🔴 THE FLAG ANSWERS THE ENDPOINT QUESTION IT WOULD OTHERWISE RAISE, and that is the whole reason
this is one argument rather than a design. The defect row warned that a recycle-bin listing must
decide whether to show an edge whose endpoint is archived — `list_by_project`'s docstring is
explicit that filtering on endpoints is what keeps archive/restore symmetric, and that an edge
pointing at a hidden node once rendered as `deadbeef…` to the author. The only caller passing
True is the outline tool, which passes the SAME flag to `list_tree`: the archived endpoints are
in the response beside the edge, so the symmetry holds in both directions.
"""
from __future__ import annotations

import inspect
import typing

from app.db.repositories.scene_links import SceneLinksRepo
from app.mcp import server as mcp


def _built_sql(*, include_archived: bool) -> str:
    """The SQL `list_by_project` actually builds, captured by driving it with a fake pool.

    Reading the source instead was measurably not enough — see the guard below."""
    import asyncio
    import uuid

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

    repo = SceneLinksRepo(_Pool())
    asyncio.run(repo.list_by_project(uuid.uuid4(), include_archived=include_archived))
    assert captured, "the method never issued a query"
    return captured[0]


class TestTheFlagReachesTheEdges:
    def test_the_lister_takes_it_and_defaults_to_live_only(self):
        sig = inspect.signature(SceneLinksRepo.list_by_project)
        p = sig.parameters.get("include_archived")
        assert p is not None, "the lister cannot be asked for archived edges"
        assert p.default is False, "the default changed — every existing caller just moved"
        assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
            "a positional flag here would be set by argument ORDER at three call sites")

    def test_the_default_query_still_filters_BOTH_endpoints(self):
        """The symmetry the archive/restore pair is built on. Dropping either EXISTS clause
        brings back the edge that pointed at a node the tree no longer showed.

        🔴 THIS COUNTED THE SOURCE TEXT AND WAS VACUOUS. Neutralising the branch — replacing
        `if include_archived` with `if True`, so the live-only view NEVER filters — left every
        clause present in the dead `else` and the guard stayed GREEN. A guard that asserts a
        string exists in a function cannot tell whether the function USES it. It now drives the
        method and reads the SQL it actually built.
        """
        assert "NOT sl.is_archived" in _built_sql(include_archived=False)
        assert "NOT f.is_archived" in _built_sql(include_archived=False)
        assert "NOT t.is_archived" in _built_sql(include_archived=False)

    def test_asking_for_archived_edges_drops_every_archived_filter(self):
        """Scoped to the WHERE clause on purpose: `is_archived` is a SELECTED COLUMN and must
        stay one — a recycle-bin listing has to tell the author which edges are archived. My
        first version asserted the word was absent from the whole statement and failed on the
        select list, which would have been a real regression if I had 'fixed' the code."""
        sql = _built_sql(include_archived=True)
        where = sql[sql.index("WHERE"):]
        assert "is_archived" not in where, (
            f"an archived-inclusive read still filters archived rows — the flag is inert: {where}")
        assert "sl.project_id = $1" in where, "the tenancy scope was dropped with the filters"
        assert "sl.is_archived" in sql[:sql.index("WHERE")], (
            "the caller can no longer tell WHICH edges are archived")

    def test_the_outline_tool_passes_it_THROUGH(self):
        """GUARD THE CALL SITE. The flag reached the NODES and stopped — that WAS the defect,
        and a lister that merely accepts the argument changes nothing."""
        src = inspect.getsource(mcp.composition_list_outline)
        assert "list_by_project(pid, include_archived=include_archived)" in src
        assert "list_tree(pid, include_archived=include_archived)" in src

    def test_the_tool_SAYS_what_the_flag_is_for(self):
        """A discovery path nobody is told about is not a discovery path — the row this closes
        is about a restore op with no way to see its own candidates.

        🔴 READ THE ARGUMENT'S DECLARED DESCRIPTION, WHICH IS WHAT THE MODEL SEES. This first
        searched the docstring PLUS `inspect.getsource`, and stripping the description left it
        GREEN — my own code COMMENT about the restore op satisfied it. A comment is invisible to
        the model; the `Annotated` metadata is the surface.
        """
        hints = typing.get_type_hints(
            mcp.composition_list_outline.fn
            if hasattr(mcp.composition_list_outline, "fn")
            else mcp.composition_list_outline,
            include_extras=True)
        meta = " ".join(str(m) for m in getattr(hints["include_archived"], "__metadata__", ()))
        assert meta, "include_archived carries no description at all"
        assert "scene-link" in meta or "scene_link" in meta, (
            f"the flag does not tell the model it reaches the EDGES: {meta!r}")
        assert "restore" in meta, (
            f"nothing connects the flag to the op it exists to serve: {meta!r}")


class TestTheDiscoveryPathIsREACHABLE:
    """🔴 THE FIX WORKED AND THE TURN COULD NOT GET TO IT. Live K=5 with the wiring deployed,
    `composition_list_outline` was on the wire 0 of 5 runs for "Show me the deleted scene links
    on this work" — nothing in its declared vocabulary answered that request. A discovery path
    the author cannot reach is not a discovery path, which is this row's whole subject."""

    def test_the_recycle_bin_phrasing_is_declared(self):
        meta = mcp.composition_list_outline
        syns = None
        for attr in ("meta", "_meta", "annotations"):
            m = getattr(meta, attr, None)
            if isinstance(m, dict) and m.get("synonyms"):
                syns = m["synonyms"]
                break
        if syns is None:
            src = inspect.getsource(mcp)
            i = src.index('tool_name="composition_list_outline"')
            syns = src[max(0, i - 900):i]
            assert "deleted scene links" in syns and "archived scene links" in syns
            return
        low = " ".join(s.lower() for s in syns)
        assert "deleted scene links" in low and "archived scene links" in low

    def test_it_does_NOT_claim_the_restore_verb(self):
        """`composition_scene_link_edit` owns the op and already declares 'restore scene link'.
        This tool answers WHERE IS IT, not RESTORE IT — declaring the verb here would manufacture
        a tie, which is the cost DQ-T70 measured for the wider case."""
        src = inspect.getsource(mcp)
        i = src.index('tool_name="composition_list_outline"')
        block = src[max(0, i - 900):i]
        decl = block[block.index("synonyms=["):] if "synonyms=[" in block else block
        assert "restore" not in decl.split("]")[0]


class TestEVERYOTHERCallerKeepsTheLiveOnlyView:
    """AUDIT ALL CALL SITES. Three call `list_by_project`; only one should have moved."""

    def test_the_packer_lens_and_the_router_do_not_pass_it(self):
        import pathlib
        root = pathlib.Path(mcp.__file__).resolve().parents[1]
        callers = []
        for f in root.rglob("*.py"):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if "list_by_project(" in line and "def " not in line:
                    callers.append((f.name, n, line.strip()))
        assert len(callers) >= 3, f"call sites moved — found {callers}"
        passing = [c for c in callers if "include_archived" in c[2]]
        assert len(passing) == 1, (
            f"exactly one caller should ask for archived edges, found {len(passing)}: {passing}")
        assert passing[0][0] == "server.py", passing


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
