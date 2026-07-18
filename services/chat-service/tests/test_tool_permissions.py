"""Track C WS-3 — the tool-consent management surface (``D-C-ALLOWLIST-WRITE-ONLY``).

The defect: ``user_tool_approvals`` was INSERT-ONLY. A user could grant an autonomous
agent a standing "Always allow" to write their data or spend their money and then had no
way to see the grant, withdraw it, or refuse the tool outright. Consent without
withdrawal is broken by design.

These tests are deliberately weighted toward **effect, not storage**. Asserting that a
DELETE removed a row proves the row is gone; it does NOT prove the agent will ask again
— and "the agent asks again" is the entire promise a revoke makes to the user. So the
load-bearing cases here drive the real tool loop and assert what the USER experiences:

  * revoke  ⇒ the next Tier-A call SUSPENDS for approval again  (the withdrawal works)
  * deny    ⇒ the next call is BLOCKED and never prompts again  (the refusal is honored)
  * allow   ⇒ the call runs silently                            (the grant still works)

Plus the one inversion that would be catastrophic and silent: a ``deny`` row must never
read back as an approval.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.db import tool_approvals
from tests.fake_approvals_pool import FakeApprovalsPool

# Reuse the REAL loop fakes rather than hand-rolling a second pair. A private copy of a
# stream fake drifts from the client contract the moment the SDK changes shape — and a
# harness that has drifted tests only itself (the first hand-rolled one here silently
# lacked `aclose` and failed for a reason that had nothing to do with consent).
from tests.test_spend_gate import _fake_client, _kc

TEST_MODEL_REF = "00000000-0000-0000-0000-0000000000aa"


def _tier_a_tool(name: str = "book_create") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "create a book",
            "parameters": {"type": "object", "properties": {}},
            "_meta": {"tier": "A"},
        },
    }


async def _drive(*, decision_check, tool=None):
    """Run ONE tool-loop in write mode over a Tier-A tool."""
    import app.services.stream_service as ss

    tool = tool or _tier_a_tool()
    name = tool["function"]["name"]
    kc = _kc()
    chunks = []
    with patch.object(ss, "Client", _fake_client(name)):
        async for ch in ss._stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
            messages=[{"role": "user", "content": "make me a book"}],
            gen_params={"max_tokens": 100}, tools=[tool],
            knowledge_client=kc, session_id="s", project_id=None,
            permission_mode="write",
            decision_check=decision_check,
        ):
            chunks.append(ch)
    return chunks, kc


def _suspends(chunks):
    return [c for c in chunks if "suspend" in c]


def _tool_calls(chunks):
    return [c["tool_call"] for c in chunks if "tool_call" in c]


# ── 1. the withdrawal actually works (the slice's whole point) ────────────────

class TestRevokeIsConsumedByEffect:
    @pytest.mark.asyncio
    async def test_revoke_makes_the_next_call_prompt_again(self):
        """THE test for this slice. Not "the row is gone" — *the agent asks again*.

        A revoke that deleted the row but left the tool running would be the worst
        possible outcome for a consent surface: the user is TOLD they took the
        permission back, and the agent keeps using it."""
        pool = FakeApprovalsPool()
        await tool_approvals.approve_tool(pool, "u", "book_create")

        # granted → the loop runs it with no card
        async def _check(tool_name, kind="mutation"):
            return await tool_approvals.get_tool_decision(pool, "u", tool_name, kind)

        chunks, kc = await _drive(decision_check=_check)
        assert _suspends(chunks) == [], "a granted tool must not prompt"
        kc.mcp_execute_tool.assert_awaited()

        # the user withdraws it
        removed = await tool_approvals.revoke_tool_decision(pool, "u", "book_create")
        assert removed is True

        # …and the very next call suspends for approval again
        chunks2, kc2 = await _drive(decision_check=_check)
        kc2.mcp_execute_tool.assert_not_awaited()   # NOT executed
        suspends = _suspends(chunks2)
        assert len(suspends) == 1
        args = suspends[0]["suspend"]["pending_tool_call"]["args"]
        assert args["kind"] == "tool_approval"
        assert args["tool"] == "book_create"

    @pytest.mark.asyncio
    async def test_revoking_something_never_granted_reports_false(self):
        """No silent success: revoking a decision that does not exist must NOT report
        that a permission was withdrawn (the route turns this into a 404)."""
        pool = FakeApprovalsPool()
        assert await tool_approvals.revoke_tool_decision(pool, "u", "book_create") is False

    @pytest.mark.asyncio
    async def test_revoke_is_kind_scoped(self):
        """Withdrawing "may write" must not silently withdraw "may spend" — they are
        distinct consents and the user revoked exactly one of them."""
        pool = FakeApprovalsPool()
        await tool_approvals.approve_tool(pool, "u", "glossary_web_search", "mutation")
        await tool_approvals.approve_tool(pool, "u", "glossary_web_search", "spend")

        await tool_approvals.revoke_tool_decision(pool, "u", "glossary_web_search", "mutation")

        assert await tool_approvals.is_tool_approved(pool, "u", "glossary_web_search", "mutation") is False
        assert await tool_approvals.is_tool_approved(pool, "u", "glossary_web_search", "spend") is True


# ── 2. deny is honored — blocked, and never prompted for again ────────────────

class TestDenyIsConsumedByEffect:
    @pytest.mark.asyncio
    async def test_denied_tool_is_blocked_and_does_not_prompt(self):
        """A standing "Never allow" must BLOCK the call — not execute it, and not
        raise a card either. Re-asking for something the user permanently refused is
        the same consent defect wearing a different hat."""
        pool = FakeApprovalsPool()
        await tool_approvals.set_tool_decision(pool, "u", "book_create", "mutation", "deny")

        async def _check(tool_name, kind="mutation"):
            return await tool_approvals.get_tool_decision(pool, "u", tool_name, kind)

        chunks, kc = await _drive(decision_check=_check)

        kc.mcp_execute_tool.assert_not_awaited()     # never ran
        assert _suspends(chunks) == []               # and never nagged

        # the model is told honestly, so it can route around the tool (no silent no-op)
        tc = _tool_calls(chunks)
        assert len(tc) == 1
        assert tc[0]["ok"] is False
        assert "Never allow" in tc[0]["error"]

    @pytest.mark.asyncio
    async def test_deny_flips_an_existing_grant_in_place(self):
        """Denying a tool the user had previously allowed must OVERWRITE the decision,
        not leave an allow row and a deny row contradicting each other."""
        pool = FakeApprovalsPool()
        await tool_approvals.approve_tool(pool, "u", "book_create")
        assert await tool_approvals.is_tool_approved(pool, "u", "book_create") is True

        await tool_approvals.set_tool_decision(pool, "u", "book_create", "mutation", "deny")

        assert await tool_approvals.get_tool_decision(pool, "u", "book_create") == "deny"
        assert len([k for k in pool.rows if k[1] == "book_create"]) == 1

    @pytest.mark.asyncio
    async def test_a_deny_row_never_reads_back_as_an_approval(self):
        """The inversion that would be catastrophic AND silent. The legacy query was
        ``SELECT 1 ... WHERE user_id AND tool_name`` — existence meant "granted". With a
        decision column, that query would return TRUE for a DENIED tool. This is the
        negative control that fails if anyone reverts to existence-checking."""
        pool = FakeApprovalsPool()
        await tool_approvals.set_tool_decision(pool, "u", "book_create", "mutation", "deny")

        assert await tool_approvals.is_tool_approved(pool, "u", "book_create") is False

    @pytest.mark.asyncio
    async def test_set_tool_decision_rejects_a_bogus_decision(self):
        pool = FakeApprovalsPool()
        with pytest.raises(ValueError):
            await tool_approvals.set_tool_decision(pool, "u", "book_create", "mutation", "maybe")

    @pytest.mark.asyncio
    async def test_a_deny_blocks_a_tier_R_tool_too(self):
        """The review's HIGH, as a test. The first cut nested the deny read inside
        `if tier == "A" and permission_mode == "write"` — the PROMPT's conditions — so a
        blocked Tier-R tool ran happily while the panel showed it under "Never runs".
        A refusal is not a prompt: it must hold wherever the tool can execute."""
        pool = FakeApprovalsPool()
        await tool_approvals.set_tool_decision(pool, "u", "glossary_search", "mutation", "deny")

        async def _check(tool_name, kind="mutation"):
            return await tool_approvals.get_tool_decision(pool, "u", tool_name, kind)

        tier_r = _tier_a_tool("glossary_search")
        tier_r["function"]["_meta"]["tier"] = "R"
        chunks, kc = await _drive(decision_check=_check, tool=tier_r)

        kc.mcp_execute_tool.assert_not_awaited()
        assert _suspends(chunks) == []
        assert "Never allow" in _tool_calls(chunks)[0]["error"]

    @pytest.mark.asyncio
    async def test_a_spend_deny_blocks_the_tool(self):
        """Any deny row blocks the tool, whatever axis it was recorded under. The user was
        shown the words "Never allow" — a consent surface must mean them."""
        pool = FakeApprovalsPool()
        await tool_approvals.set_tool_decision(pool, "u", "book_create", "spend", "deny")

        async def _check(tool_name, kind="mutation"):
            return await tool_approvals.get_tool_decision(pool, "u", tool_name, kind)

        chunks, kc = await _drive(decision_check=_check)
        kc.mcp_execute_tool.assert_not_awaited()
        assert "Never allow" in _tool_calls(chunks)[0]["error"]

    @pytest.mark.asyncio
    async def test_an_unreadable_decision_is_unknown_not_denied(self):
        """A DB blip must not hard-block tool calling. Unknown ⇒ fall through to the
        normal prompt path, never to a block (and, per the gate, never to a grant)."""
        async def _boom(tool_name, kind="mutation"):
            raise RuntimeError("db down")

        chunks, kc = await _drive(decision_check=_boom)
        kc.mcp_execute_tool.assert_not_awaited()   # it asks…
        assert len(_suspends(chunks)) == 1         # …rather than blocking or running


# ── 3b. the storage key cannot be forged ─────────────────────────────────────

class TestKeyInjection:
    def test_a_tool_name_containing_the_namespace_separator_is_rejected(self):
        """`_storage_key("spend::web", "mutation")` used to return "spend::web" — i.e. the
        SPEND slot for `web`. A name arriving from a URL path (or the panel's text box)
        could therefore forge or erase a consent on an axis the caller never named. The
        encoding's invariant is now enforced, not assumed."""
        with pytest.raises(ValueError):
            tool_approvals._storage_key("spend::glossary_web_search", "mutation")

    @pytest.mark.asyncio
    async def test_the_db_helpers_refuse_a_forged_key(self):
        pool = FakeApprovalsPool()
        with pytest.raises(ValueError):
            await tool_approvals.set_tool_decision(pool, "u", "spend::web", "mutation", "deny")
        with pytest.raises(ValueError):
            await tool_approvals.get_tool_decision(pool, "u", "spend::web", "mutation")


# ── 3. listing — a permission the user cannot see is one they cannot withdraw ──

class TestListDecisions:
    @pytest.mark.asyncio
    async def test_list_decodes_the_storage_key_back_to_tool_and_kind(self):
        """The spend kind is stored namespaced (``spend::tool``). If the list surfaced
        the raw key, the panel would show a user a tool called "spend::glossary_web_search"
        that they could not match to anything — and the revoke button would miss."""
        pool = FakeApprovalsPool()
        await tool_approvals.approve_tool(pool, "u", "book_create")                      # mutation
        await tool_approvals.approve_tool(pool, "u", "glossary_web_search", "spend")     # spend
        await tool_approvals.set_tool_decision(pool, "u", "chapter_delete", "mutation", "deny")

        rows = await tool_approvals.list_tool_decisions(pool, "u")
        got = {(r["tool_name"], r["kind"], r["decision"]) for r in rows}

        assert got == {
            ("book_create", "mutation", "allow"),
            ("glossary_web_search", "spend", "allow"),
            ("chapter_delete", "mutation", "deny"),
        }

    @pytest.mark.asyncio
    async def test_list_is_owner_scoped(self):
        """Tenancy: one user must never see another's consent decisions."""
        pool = FakeApprovalsPool()
        await tool_approvals.approve_tool(pool, "u", "book_create")
        await tool_approvals.approve_tool(pool, "other", "chapter_delete")

        rows = await tool_approvals.list_tool_decisions(pool, "u")
        assert [r["tool_name"] for r in rows] == ["book_create"]

    def test_an_unknown_key_prefix_is_not_decoded_as_a_kind(self):
        """``_split_key`` must only decode KNOWN kinds. A tool literally named
        ``foo::bar`` must not be reported under a consent axis the gate never reads."""
        assert tool_approvals._split_key("book_create") == ("book_create", "mutation")
        assert tool_approvals._split_key("spend::web") == ("web", "spend")
        assert tool_approvals._split_key("bogus::web") == ("bogus::web", "mutation")


# ── 4. the HTTP surface — the panel's actual contract ────────────────────────

@pytest.fixture
async def perm_client(user_id):
    """The real router over a faithful fake table."""
    from httpx import ASGITransport, AsyncClient

    from app.deps import get_current_user, get_db
    from app.main import app

    pool = FakeApprovalsPool()
    app.dependency_overrides[get_db] = lambda: pool
    app.dependency_overrides[get_current_user] = lambda: user_id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, pool

    app.dependency_overrides.clear()


class TestToolPermissionsRoutes:
    @pytest.mark.asyncio
    async def test_grant_list_revoke_round_trip(self, perm_client, user_id):
        ac, pool = perm_client

        r = await ac.put("/v1/chat/tool-permissions/book_create",
                         json={"kind": "mutation", "decision": "allow"})
        assert r.status_code == 200, r.text
        assert r.json()["decision"] == "allow"

        r = await ac.get("/v1/chat/tool-permissions")
        assert r.status_code == 200
        perms = r.json()["permissions"]
        assert len(perms) == 1
        assert perms[0]["tool_name"] == "book_create"
        assert perms[0]["kind"] == "mutation"
        assert perms[0]["decision"] == "allow"

        r = await ac.delete("/v1/chat/tool-permissions/book_create?kind=mutation")
        assert r.status_code == 204

        r = await ac.get("/v1/chat/tool-permissions")
        assert r.json()["permissions"] == []

    @pytest.mark.asyncio
    async def test_revoking_a_nonexistent_permission_404s(self, perm_client):
        ac, _ = perm_client
        r = await ac.delete("/v1/chat/tool-permissions/never_granted")
        assert r.status_code == 404, "a revoke that took nothing back must not report success"

    @pytest.mark.asyncio
    async def test_deny_is_settable_over_http(self, perm_client):
        ac, pool = perm_client
        r = await ac.put("/v1/chat/tool-permissions/chapter_delete",
                         json={"kind": "mutation", "decision": "deny"})
        assert r.status_code == 200
        assert r.json()["decision"] == "deny"
        assert await tool_approvals.get_tool_decision(pool, "u", "chapter_delete") is None  # not that user
        r = await ac.get("/v1/chat/tool-permissions")
        assert r.json()["permissions"][0]["decision"] == "deny"

    @pytest.mark.asyncio
    async def test_closed_set_values_are_enum_validated(self, perm_client):
        """A free-string kind/decision would write a row the gate never reads — a
        setting that GETs back as effective and does nothing, forever."""
        ac, _ = perm_client
        r = await ac.put("/v1/chat/tool-permissions/book_create",
                         json={"kind": "vibes", "decision": "allow"})
        assert r.status_code == 422
        r = await ac.put("/v1/chat/tool-permissions/book_create",
                         json={"kind": "mutation", "decision": "maybe"})
        assert r.status_code == 422
        r = await ac.delete("/v1/chat/tool-permissions/book_create?kind=vibes")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_an_omitted_decision_is_a_422_never_a_silent_grant(self, perm_client):
        """`decision` used to default to "allow", so an empty/partial body quietly created
        a standing GRANT. On a consent surface the safe failure is an error, never an
        unrequested permission."""
        ac, pool = perm_client
        r = await ac.put("/v1/chat/tool-permissions/book_create", json={"kind": "mutation"})
        assert r.status_code == 422
        assert pool.rows == {}, "a rejected write must not have persisted anything"

    @pytest.mark.asyncio
    async def test_a_forged_namespace_key_is_rejected(self, perm_client):
        """PUT /tool-permissions/spend::web_search {kind: mutation} would have written the
        SPEND key for `web_search` — touching a consent the caller never named."""
        ac, pool = perm_client
        r = await ac.put("/v1/chat/tool-permissions/spend::web_search",
                         json={"kind": "mutation", "decision": "deny"})
        assert r.status_code == 422
        assert pool.rows == {}

    @pytest.mark.asyncio
    async def test_unknown_tool_is_422_when_the_catalog_is_available(self, perm_client):
        """D7 (PO sign-off) — a decision on a tool that is not in the live catalog is a
        422, so a typo cannot persist a permission the gate will never read."""
        from unittest.mock import AsyncMock, MagicMock
        ac, pool = perm_client
        fake_kc = MagicMock()
        fake_kc.get_tool_definitions = AsyncMock(return_value=[
            {"type": "function", "function": {"name": "book_create"}},
            {"type": "function", "function": {"name": "glossary_search"}},
        ])
        with patch("app.client.knowledge_client.get_knowledge_client", return_value=fake_kc):
            r = await ac.put("/v1/chat/tool-permissions/definitely_not_a_tool",
                             json={"kind": "mutation", "decision": "deny"})
        assert r.status_code == 422, r.text
        assert "unknown tool" in r.json()["detail"]
        assert pool.rows == {}, "a rejected write must persist nothing"

    @pytest.mark.asyncio
    async def test_known_tool_is_accepted_when_the_catalog_is_available(self, perm_client):
        """The membership check must not reject a REAL tool — the catalog carries it."""
        from unittest.mock import AsyncMock, MagicMock
        ac, pool = perm_client
        fake_kc = MagicMock()
        fake_kc.get_tool_definitions = AsyncMock(return_value=[
            {"type": "function", "function": {"name": "book_create"}},
        ])
        with patch("app.client.knowledge_client.get_knowledge_client", return_value=fake_kc):
            r = await ac.put("/v1/chat/tool-permissions/book_create",
                             json={"kind": "mutation", "decision": "deny"})
        assert r.status_code == 200, r.text
        assert r.json()["decision"] == "deny"

    @pytest.mark.asyncio
    async def test_write_still_succeeds_when_the_catalog_is_unavailable(self, perm_client):
        """Fail-OPEN on an unavailable catalog: get_tool_definitions returns [] on any
        fetch failure, and a gateway blip must not brick a user's ability to DENY a tool
        (the safety action). We 422 a known-unknown, never a can't-check."""
        from unittest.mock import AsyncMock, MagicMock
        ac, pool = perm_client
        fake_kc = MagicMock()
        fake_kc.get_tool_definitions = AsyncMock(return_value=[])  # [] == unavailable
        with patch("app.client.knowledge_client.get_knowledge_client", return_value=fake_kc):
            r = await ac.put("/v1/chat/tool-permissions/some_tool",
                             json={"kind": "mutation", "decision": "deny"})
        assert r.status_code == 200, r.text
        # and a hard catalog error also fails open (never blocks the consent write)
        fake_kc.get_tool_definitions = AsyncMock(side_effect=RuntimeError("gateway down"))
        with patch("app.client.knowledge_client.get_knowledge_client", return_value=fake_kc):
            r = await ac.put("/v1/chat/tool-permissions/another_tool",
                             json={"kind": "mutation", "decision": "deny"})
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_revoke_does_not_require_catalog_membership(self, perm_client, user_id):
        """Revoke stays lenient — you must be able to withdraw a decision for a tool that
        has since left the catalog, without the catalog being reachable at all."""
        from unittest.mock import AsyncMock, MagicMock
        ac, pool = perm_client
        # seed a deny under the ROUTE's user (the token owner), then revoke it with a
        # catalog that would reject the name
        await tool_approvals.set_tool_decision(pool, user_id, "gone_tool", "mutation", "deny")
        fake_kc = MagicMock()
        fake_kc.get_tool_definitions = AsyncMock(return_value=[
            {"type": "function", "function": {"name": "book_create"}},
        ])
        with patch("app.client.knowledge_client.get_knowledge_client", return_value=fake_kc):
            r = await ac.delete("/v1/chat/tool-permissions/gone_tool?kind=mutation")
        assert r.status_code == 204, r.text

    @pytest.mark.asyncio
    async def test_the_owner_comes_from_the_token_not_the_request(self, perm_client, user_id):
        """Tenancy: the caller cannot name the user whose permissions it edits. A
        consent surface that took the owner from the body would be a worse defect than
        the one this router fixes."""
        ac, pool = perm_client
        await ac.put("/v1/chat/tool-permissions/book_create",
                     json={"kind": "mutation", "decision": "allow",
                           "user_id": "somebody-else"})   # ignored (not in the model)

        # the row landed under the TOKEN's user, and nobody else's
        assert (user_id, "book_create") in pool.rows
        assert not any(uid != user_id for uid, _ in pool.rows)
