"""An edit tool must accept the key its own sibling list already showed the caller.

    THE INVARIANT. `composition_arc_template_edit` resolves `code` — the human-readable key
    `composition_arc_template_list` displays — to `arc_id` for every op that needs an id, and
    refuses rather than guessing when the code does not identify exactly one row.

OWNER RULING 2026-08-31, DQ-T34: "an *_edit tool that requires an opaque id must ALSO accept the
human-readable key its own sibling lists (e.g. `code`)."

THE MEASUREMENT: op=archive required `arc_id` and refused `code`, and on 5 of 5 runs the model
would not resolve the name — it asked the AUTHOR for a UUID instead. `code` is already what
op=create takes and what the list tool already shows. Across the loop, measured 2026-08-23 with
world_* excluded, 48% of every tool-call failure is a required argument the model could not
supply, and 45 of 86 id-requiring tools name no supplier tool at all.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import uuid

import pytest

from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.mcp import server as mcp


class _Pool:
    """Captures the SQL and returns whatever the case needs."""

    def __init__(self, rows):
        self.rows = rows
        self.sql: list[str] = []
        self.args: list[tuple] = []

    async def fetch(self, query, *args):
        self.sql.append(" ".join(query.split()))
        self.args.append(args)
        return self.rows


@pytest.mark.asyncio
class TestTheResolverItself:
    async def test_it_returns_every_match_not_the_first(self):
        """🔴 A LIST, ON PURPOSE. The constraint is UNIQUE(owner, code, lang), so `code` alone is
        not unique BY SCHEMA even though it is in today's data (57 rows, 57 distinct owner+code
        pairs). A resolver returning the first match would one day archive a translation the
        author never named."""
        a, b = uuid.uuid4(), uuid.uuid4()
        pool = _Pool([{"id": a}, {"id": b}])
        got = await ArcTemplateRepo(pool).ids_for_code(uuid.uuid4(), "some-code")
        assert got == [a, b]

    async def test_it_is_scoped_to_the_CALLER(self):
        """Resolving a name into somebody else's id is a tenancy hole dressed as a convenience."""
        pool = _Pool([])
        caller = uuid.uuid4()
        await ArcTemplateRepo(pool).ids_for_code(caller, "c")
        assert "owner_user_id = $1" in pool.sql[0], pool.sql[0]
        assert pool.args[0][0] == caller

    async def test_it_matches_on_code_not_name(self):
        pool = _Pool([])
        await ArcTemplateRepo(pool).ids_for_code(uuid.uuid4(), "c")
        assert "code = $2" in pool.sql[0], pool.sql[0]
        assert "name" not in pool.sql[0].lower().split("where")[1]


class TestTheDispatchResolvesOnceForEveryIdTakingOp:
    @staticmethod
    def _src() -> str:
        return inspect.getsource(mcp.composition_arc_template_edit)

    def test_the_resolution_happens_BEFORE_any_op_branch(self):
        """🔴 ONE CHOKEPOINT. update, archive and restore all need an id; resolving inside each
        branch is three chances to forget the fourth op somebody adds later."""
        src = self._src()
        i = src.index("ids_for_code")
        j = src.index('if args.op == "create"')
        assert i < j, (
            "the code resolution runs after the first op branch, so at least one op still "
            "cannot take a code")

    def test_it_does_not_hijack_op_create(self):
        """create TAKES a code and mints a new row — resolving it to an existing id there would
        turn a create into a silent no-op or a wrong-row edit."""
        src = self._src()
        window = src[:src.index("ids_for_code")] + src[src.index("ids_for_code"):
                                                       src.index("ids_for_code") + 400]
        assert 'args.op != "create"' in window, (
            "op=create is not excluded from the code resolution")

    def test_an_explicit_arc_id_still_wins(self):
        """A caller that passed the id must not have it re-derived from a code they also sent."""
        assert "not args.arc_id and args.code" in self._src()

    def test_an_AMBIGUOUS_code_refuses_rather_than_picking(self):
        # Anchored on text that survives LINE WRAPPING: the sentence is split across adjacent
        # string literals in the source, so the full phrase is not contiguous and an assertion
        # on it fails while the shipped message is perfectly correct.
        src = " ".join(self._src().split())
        assert "not identify one" in src, (
            "more than one match is resolved silently — the schema permits it and the data will "
            "eventually contain it")
        assert "len(_matches) > 1" in src, "the ambiguity is not even detected"

    def test_an_UNKNOWN_code_says_where_to_look(self):
        src = self._src()
        i = src.index("no arc template of yours has code")
        assert "composition_arc_template_list" in src[i:i + 300], (
            "the refusal does not name the sibling that shows the codes")


class TestEveryIdTakingRefusalAdvertisesTheKey:
    """🔴 ASSERT EVERY CALL SITE. Three refusals told the model 'arc_id — NOT a name'. Fixing one
    would leave the other two teaching the caller that an id is the only way in."""

    @staticmethod
    def _messages() -> list[str]:
        src = pathlib.Path(inspect.getfile(mcp)).read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "composition_arc_template_edit")
        out = []
        for n in ast.walk(fn):
            if (isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
                    and getattr(n.exc.func, "id", "") == "ValueError"):
                for a in n.exc.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        out.append(a.value)
        return out

    def test_no_refusal_still_says_an_id_is_the_only_way(self):
        stale = [m for m in self._messages() if "requires arc_id — NOT a name" in m]
        assert not stale, (
            f"{len(stale)} refusal(s) still tell the caller an id is the only way in: {stale}")

    def test_each_id_op_refusal_names_code(self):
        needing = [m for m in self._messages() if "requires arc_id" in m]
        assert len(needing) >= 3, (
            f"expected the update/archive/restore refusals, found {len(needing)}")
        for m in needing:
            assert "`code`" in m, f"this refusal does not offer the key: {m!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
