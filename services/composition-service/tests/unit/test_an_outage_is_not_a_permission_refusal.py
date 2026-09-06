"""A refusal must name its precondition — and an outage is not a fact about the caller.

    THE INVARIANT. When the grant AUTHORITY cannot be reached, the deny stays fail-closed and
    the caller is told the check could not be MADE — never that they lack permission.

OWNER RULING 2026-08-31, DQ-T66 (a): bring the Python SDK up to the Go SDK's `ErrUnavailable`.

🔴 WHERE THE INFORMATION DIED. `loreweave_grants._fetch` returned `(GrantLevel.NONE, "", None)`
for BOTH "this user has no grant" and "the authority could not be reached" — it LOGGED the reason
and then collapsed it. Measured live: a real confirm token, minted through the real service on a
throwaway fixture and redeemed against an isolated instance whose book-service was unreachable:

    POST /v1/composition/actions/confirm?token=<real gate token>
    -> 403 {"detail": {"code": "action_error"}}

a bare refusal naming no precondition, while the SDK's own log one frame away said "grant
authority unavailable (fail-closed deny): All connection attempts failed".

THE GO SDK HAS CARRIED THE DISTINCTION ALL ALONG — `grantclient.ErrUnavailable`, and
agent-registry already branches on it. This is one SDK catching up with its sibling.

🔴 THE DENY DOES NOT SOFTEN. Fail-closed on an unreachable authority is correct and stays
byte-identical; only the caller's ability to ASK is new. And no oracle is created: the authority
was down, so NOBODY could have been resolved — the answer discloses nothing about this book.
"""
from __future__ import annotations

import inspect
from uuid import uuid4

import pytest

from app import grant_deps
from app.grant_deps import GrantAuthorityUnavailable, GrantLevel, authorize_book
from app.packer.pack import OwnershipError


class _Grant:
    """A GrantClient stand-in: denies, and answers the new question however the test says."""

    def __init__(self, *, unavailable: bool, level=GrantLevel.NONE):
        self._unavailable = unavailable
        self._level = level
        self.asked = 0

    async def resolve_grant(self, book_id, caller):
        return self._level

    def last_denial_was_unavailable(self, book_id, caller):
        self.asked += 1
        return self._unavailable


class TestTheOutageIsDistinguishable:
    @pytest.mark.asyncio
    async def test_an_unreachable_authority_raises_the_named_exception(self):
        with pytest.raises(GrantAuthorityUnavailable):
            await authorize_book(_Grant(unavailable=True), uuid4(), uuid4(), GrantLevel.EDIT)

    @pytest.mark.asyncio
    async def test_a_GENUINE_no_grant_is_unchanged(self):
        """The half that must not move. A real denial keeps raising the base class and the
        routers keep mapping it to the uniform 404."""
        g = _Grant(unavailable=False)
        with pytest.raises(OwnershipError) as ei:
            await authorize_book(g, uuid4(), uuid4(), GrantLevel.EDIT)
        assert not isinstance(ei.value, GrantAuthorityUnavailable)

    @pytest.mark.asyncio
    async def test_the_question_is_asked_ONLY_on_the_deny_path(self):
        """A granted caller must not pay for it, and no grant may be softened by it."""
        g = _Grant(unavailable=True, level=GrantLevel.EDIT)
        assert await authorize_book(g, uuid4(), uuid4(), GrantLevel.EDIT) == GrantLevel.EDIT
        assert g.asked == 0, "the outage question was asked on a SUCCESSFUL resolve"

    @pytest.mark.asyncio
    async def test_a_client_without_the_capability_still_works(self):
        """The SDK and the service deploy separately. An older client that cannot answer must
        degrade to today's behaviour, never crash."""
        class _Old:
            async def resolve_grant(self, book_id, caller):
                return GrantLevel.NONE
        with pytest.raises(OwnershipError):
            await authorize_book(_Old(), uuid4(), uuid4(), GrantLevel.EDIT)


class TestTheBlastRadiusIsZero:
    def test_it_SUBCLASSES_OwnershipError(self):
        """🔴 THE SAFETY OF THE WHOLE CHANGE. 63 sites across 28 files catch OwnershipError /
        InsufficientGrant. A new exception type none of them named would escape every handler and
        turn a book-service outage into a 500 across the service — worse than the bare refusal
        this row is about."""
        assert issubclass(GrantAuthorityUnavailable, OwnershipError)

    def test_the_confirm_route_catches_the_SUBCLASS_FIRST(self):
        """An `except (OwnershipError, ...)` placed first would swallow it silently — the branch
        would be unreachable and the fix inert. Same ordering rule this repo records for SDK
        errors."""
        from app.routers import actions
        src = inspect.getsource(actions)
        i = src.index("except GrantAuthorityUnavailable")
        j = src.index("except (OwnershipError, InsufficientGrant)")
        assert i < j, "the base class is caught before the subclass — the branch is dead"

    def test_the_route_answers_RETRYABLE_and_names_the_reason(self):
        from app.routers import actions
        src = inspect.getsource(actions)
        assert "grant_authority_unavailable" in src
        assert "status_code=503" in src
        assert "Retry-After" in src
        assert "permission service is " in src, "the detail does not say what went wrong"

    def test_every_confirm_deny_site_got_it(self):
        """Four sites in the confirm route deny on a grant. A fix applied to one of them leaves
        the others answering a bare action_error to an outage."""
        from app.routers import actions
        src = inspect.getsource(actions)
        assert src.count("except GrantAuthorityUnavailable") == \
            src.count("except (OwnershipError, InsufficientGrant) as exc:")


class TestTheSDKRecordsTheReason:
    def test_both_collapse_sites_mark_it(self):
        """The two arms that used to discard the reason: a non-200 and a transport error."""
        import loreweave_grants
        src = inspect.getsource(loreweave_grants.GrantClient._fetch)
        assert src.count("_mark_unavailable") == 2

    def test_a_successful_resolve_CLEARS_it(self):
        """A recovered authority must stop reporting an outage that is over."""
        import loreweave_grants
        src = inspect.getsource(loreweave_grants.GrantClient._fetch)
        assert "self._unavailable.discard" in src
        assert src.index("discard") < src.index("_mark_unavailable")

    def test_the_memory_is_BOUNDED(self):
        """An unbounded set is a memory leak on a service whose authority is down — precisely
        when it fills fastest."""
        import loreweave_grants
        assert loreweave_grants._UNAVAILABLE_MAX > 0
        src = inspect.getsource(loreweave_grants.GrantClient._mark_unavailable)
        assert "_UNAVAILABLE_MAX" in src and "clear()" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
