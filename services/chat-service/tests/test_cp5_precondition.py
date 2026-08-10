"""CP-5.8 — the state a tool requires, checked before the wire.

🔴 **MEASURED: 414 calls / 82 sessions fail on a missing or wrong scope** — the largest remaining
population by the honest denominator. And every failing tool ALREADY DECLARES what it needs:
`_meta.scope` is set on the whole catalogue (194 `book` · 65 `user` · 33 `project` · 23 `none`).
Nothing consulted it, so the model learned the requirement from a round trip and a backend error
like `no project in scope`.

🔴 **GATED ON `project` ONLY, AND THAT IS THE LOAD-BEARING DECISION.** `scope: book` is the SCOPE
KEY, not a hard precondition — `book_list` is `scope: book` and is how a model FINDS a book, so
refusing it without one would make books unreachable. Verified against the catalogue BEFORE
building: `kg_project_create` and `kg_project_list` are `scope: user`, so the path to create or
find a project stays open under this gate.
"""
from __future__ import annotations

import json
import pathlib

STREAM = (pathlib.Path(__file__).resolve().parents[1]
          / "app" / "services" / "stream_service.py")
BASELINE = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json")


def catalogue() -> list[dict]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["tools"]


def scope_of(name: str):
    for t in catalogue():
        fn = t.get("function", t)
        if fn.get("name") == name:
            return (fn.get("_meta") or {}).get("scope")
    return None


class TestTheGateCannotStarveItsOwnBootstrap:
    """The trap this row could have shipped: withhold the tools that CREATE the scope, and the
    scope becomes unreachable forever."""

    def test_THE_PROJECT_BOOTSTRAP_TOOLS_ARE_NOT_PROJECT_SCOPED(self):
        assert scope_of("kg_project_list") == "user"
        assert scope_of("kg_project_create") == "user"

    def test_BOOK_SCOPE_IS_NOT_GATED_BECAUSE_BOOK_LIST_CARRIES_IT(self):
        """`book_list` — the tool a model uses to FIND a book — declares `scope: book`. So scope
        is a KEY, not a precondition, and gating on it would make books unreachable."""
        assert scope_of("book_list") == "book"
        assert 'get("scope") == "project"' in STREAM.read_text(encoding="utf-8"), (
            "the gate must be project-only; gating `book` would starve book discovery"
        )
        assert '_scope_meta.get("scope") == "book"' not in STREAM.read_text(encoding="utf-8")


class TestThePreconditionIsCheckedBeforeTheWire:

    def test_THE_CHECK_EXISTS_AND_PRECEDES_THE_DISPATCH(self):
        s = STREAM.read_text(encoding="utf-8")
        check = s.index('_scope_meta.get("scope") == "project"')
        dispatch = s.index("envelope = await knowledge_client.mcp_execute_tool(")
        assert check < dispatch, "a precondition checked after the dispatch saves nothing"

    def test_AN_EXPLICIT_PROJECT_ID_SATISFIES_IT(self):
        """The gate is about ABSENCE of a project, not about the tool. A call that carries one
        must pass untouched, or every project-scoped tool becomes unusable."""
        s = STREAM.read_text(encoding="utf-8")
        assert 'not args_obj.get("project_id")' in s
        assert 'not (context_ids or {}).get("project_id")' in s
        assert "and not project_id" in s

    def test_A_PRECONDITION_MISS_IS_REFUSED_NOT_FAILED(self):
        s = STREAM.read_text(encoding="utf-8")
        assert '}, "precondition_unmet")}' in s
        assert '"error": "precondition_unmet"' in s

    def test_THE_REFUSAL_NAMES_THE_WAY_OUT(self):
        """`no project in scope` is loud and unactionable. This names the two tools that fix it."""
        s = STREAM.read_text(encoding="utf-8")
        msg = s[s.index("_pre_msg = ("):s.index('logger.info("CP-5.8')]
        assert "kg_project_list" in msg and "kg_project_create" in msg, (
            "the refusal itself must name the way out — the explanatory COMMENT above it also "
            "mentions both tools, so a file-wide check here could not fail"
        )

    def test_THE_DECLARATION_IS_THE_SOURCE_NOT_A_TOOL_NAME_LIST(self):
        """33 tools declare `scope: project`. A hand-kept list here would drift from the catalogue
        the first time a service added one."""
        s = STREAM.read_text(encoding="utf-8")
        assert '(cat_index.get(c["name"]) or plain_index.get(c["name"]) or {})' in s
        for n in ("kg_schema_read", "lore_ask", "memory_search"):
            assert scope_of(n) == "project", f"{n} is expected to declare scope=project"
