"""22 SC4 — the REST write mirror must accept every field the repo can write.

Root cause of a shipped silent-no-op (caught by adversarial review 2026-07-11): the
scene-inspector's Craft/Cast&Setting edits and the bulk retarget-words go through the REST
`PATCH /outline/nodes/{id}` -> `NodePatch`. Pydantic's default `extra='ignore'` SILENTLY DROPS
any undeclared key, so a body like `{"target_words": 900, "conflict": "..."}` parsed to an empty
patch and the GUI edit no-op'd — while the MCP tool (which declares the fields) worked. The repo's
`_UPDATABLE_COLUMNS` already writes them; only the REST mirror lagged (the CF-9 "one repo method,
two front doors" divergence). This guards the mirror so the drift cannot silently recur.

`exit_state` is intentionally EXCLUDED from the REST models: SC12 mandates a validated envelope
({v:1,...}), so it is written only through the MCP surface, never as a free-form REST blob.
"""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import OutlineNode
from app.db.repositories.outline import _UPDATABLE_COLUMNS
from app.routers.outline import NodeCreate, NodePatch

# The one column the repo can write but the REST mirror deliberately does not expose (SC12).
_MCP_ONLY = {"exit_state"}

_USER = UUID("00000000-0000-0000-0000-0000000000aa")
_PROJECT = UUID("00000000-0000-0000-0000-0000000000bb")
_BOOK = UUID("00000000-0000-0000-0000-0000000000cc")
_NODE = UUID("00000000-0000-0000-0000-0000000000dd")


def _node(**over) -> OutlineNode:
    base = dict(
        id=_NODE, created_by=_USER, project_id=_PROJECT, book_id=_BOOK, parent_id=None,
        kind="scene", rank="a0", title="A scene", goal="", status="drafting", synopsis="",
        version=3, story_order=1,
    )
    base.update(over)
    return OutlineNode.model_validate(base)


def test_nodepatch_covers_every_writable_column_except_the_mcp_only_envelope():
    patch_fields = set(NodePatch.model_fields)
    must_accept = _UPDATABLE_COLUMNS - _MCP_ONLY
    missing = must_accept - patch_fields
    assert not missing, (
        f"NodePatch drops writable columns {sorted(missing)} — a REST edit of them silently no-ops "
        f"(extra='ignore'). Declare them on NodePatch or, if intentionally MCP-only, add to _MCP_ONLY."
    )


def test_arcpatch_covers_the_structure_repo_writable_columns():
    # The sibling write mirror (arc router → structure repo). Currently correct; this locks it so
    # widening the structure repo without touching ArcPatch reds instead of silently no-op'ing the
    # Hub's arc edits (the same class as the NodePatch bug).
    from app.db.repositories.structure import _UPDATABLE_COLUMNS as _ARC_UPDATABLE
    from app.routers.arc import ArcPatch
    missing = _ARC_UPDATABLE - set(ArcPatch.model_fields)
    assert not missing, f"ArcPatch drops writable arc columns {sorted(missing)} (silent-no-op class)"


def test_nodecreate_also_accepts_the_sc4_craft_fields():
    create_fields = set(NodeCreate.model_fields)
    for f in ("location_entity_id", "story_time", "conflict", "outcome", "stakes",
              "value_shift", "target_words"):
        assert f in create_fields, f"NodeCreate must accept {f} (else a REST create drops it)"


def test_sc4_fields_survive_parse_and_are_not_dropped():
    # The exact failure mode: build the model from a dict and confirm the SC4 keys are kept in
    # the exclude_unset dump the handler forwards to update_node.
    body = NodePatch(
        target_words=900, conflict="a real conflict", location_entity_id=uuid4(), value_shift=-40,
    )
    dumped = body.model_dump(exclude_unset=True)
    assert dumped["target_words"] == 900
    assert dumped["conflict"] == "a real conflict"
    assert "location_entity_id" in dumped
    assert dumped["value_shift"] == -40


def test_exit_state_stays_off_the_rest_mirror():
    # SC12 — a validated envelope, never a free-form REST blob.
    assert "exit_state" not in NodePatch.model_fields
    assert "exit_state" not in NodeCreate.model_fields


# ── round-trip: the effect the mock-only FE tests could not see ──────────────────────────────
# The FE unit tests assert patchNode is CALLED with {target_words} etc., but mock the transport, so
# they cannot see the BE drop the fields. This drives the REAL HTTP body through NodePatch parse to
# update_node and asserts the fields ARRIVE — the round-trip that was silently broken.

class _StubOutline:
    def __init__(self):
        self.patch_seen: dict | None = None

    async def get_node(self, node_id):
        return _node()  # for _gate_node's row-scope resolution

    async def update_node(self, node_id, patch, *, expected_version=None):
        self.patch_seen = dict(patch)
        return _node(**{k: v for k, v in patch.items() if k in OutlineNode.model_fields}, version=4)


class _StubWorks:
    async def get(self, project_id):
        from types import SimpleNamespace
        return SimpleNamespace(book_id=_BOOK)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_grant_client_dep, get_outline_repo, get_works_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    holder: dict = {"repo": _StubOutline()}
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_works_repo] = lambda: _StubWorks()
    app.dependency_overrides[get_outline_repo] = lambda: holder["repo"]
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, holder
    app.dependency_overrides.clear()


def test_patch_sc4_fields_reach_update_node_over_http(client):
    c, holder = client
    loc = str(uuid4())
    r = c.patch(
        f"/v1/composition/outline/nodes/{_NODE}",
        json={"target_words": 900, "conflict": "the duel", "location_entity_id": loc, "value_shift": -40},
        headers={"If-Match": "3"},
    )
    assert r.status_code == 200, r.text
    seen = holder["repo"].patch_seen
    # The whole point: these arrive at the repo instead of being dropped by extra='ignore'.
    assert seen["target_words"] == 900
    assert seen["conflict"] == "the duel"
    assert str(seen["location_entity_id"]) == loc
    assert seen["value_shift"] == -40
