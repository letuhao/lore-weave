"""R5 — a standing "always allow" must not fire on a turn that asked to LOOK.

🔴 MEASURED 5/5, 2026-08-13, five independent sessions through the real FE path
(scripts/toolloop/fe_runner.py). The author asked:

    "Show me the outline I've planned for this book — what chapters and scenes are in it?"

Every run called `composition_outline_node_edit` — tier **A** — two to three times, and the owning
store went from 7 outline nodes to 10. **Three chapters were created by a question that only asked
to see them**, and the reply then described that invented structure as "your current plan".

No confirm card was shown, because `user_tool_approvals` held an `allow` for that tool from
2026-07-30: a grant made two weeks earlier, in a session that was genuinely building. A standing
consent is granted in one context and then applies in every context — which is the defect. The
author allowed the tool to write *while asking it to write*. Nothing in that grant covers a turn
that asked to look.

This is the last line of defence in the surface-answerability plan: even if the wrong tools are on
the wire (R1/R2) and the wrong rail claims the turn (R4), this stops the write from LANDING.
"""
import pytest

from app.services.request_mood import (
    CONSTRUCT,
    INSPECT,
    UNKNOWN,
    request_mood,
    standing_grant_applies,
)

LIVE_PROMPT = "Show me the outline I've planned for this book — what chapters and scenes are in it?"


class TestTheLiveRequest:
    def test_the_prompt_that_created_three_chapters_reads_as_INSPECT(self):
        assert request_mood(LIVE_PROMPT) == INSPECT

    def test_and_so_the_standing_write_grant_does_not_apply(self):
        """THE FALSIFIER. Before this, the 07-30 grant applied and the write ran silently."""
        assert standing_grant_applies(request_mood(LIVE_PROMPT), kind="mutation") is False

    def test_the_call_is_ASKED_not_blocked(self):
        """Setting the grant aside must route to the Tier-A card, never to a refusal. The gate
        reads `!= "allow"` and raises a card, so returning "not allowed" is exactly right — the
        author still gets to say yes, they just get to see it."""
        assert standing_grant_applies(INSPECT, kind="mutation") is False
        # …and nothing here denies: a deny is a separate decision the caller passes through.


class TestItDoesNotGetInTheWayOfRealWork:
    """A mood classifier that guesses would put a card in front of writes the author plainly asked
    for, which trains them to click through cards — the opposite of consent. These are the cases
    that must stay untouched."""

    @pytest.mark.parametrize("msg", [
        "Add a chapter called The Salt Ledger",
        "Create three scenes for chapter 2",
        "Update the book description",
        "Delete the last scene",
        "Rewrite this paragraph",
        "Translate this book into Vietnamese",
    ])
    def test_a_plain_write_request_keeps_its_standing_grant(self, msg):
        assert request_mood(msg) == CONSTRUCT
        assert standing_grant_applies(request_mood(msg), kind="mutation") is True

    @pytest.mark.parametrize("msg", [
        "Show me the outline and add a chapter",
        "What scenes do I have? Create one more",
        "List my canon rules and delete the second",
    ])
    def test_a_MIXED_request_is_unknown_and_keeps_its_grant(self, msg):
        """The rule is two-sided on purpose: an inspect marker AND no construct verb. A mixed
        request is not an inspect turn, and suppressing the grant there would prompt for work the
        author explicitly asked for in the same sentence."""
        assert request_mood(msg) == UNKNOWN
        assert standing_grant_applies(request_mood(msg), kind="mutation") is True

    @pytest.mark.parametrize("msg", ["ok", "yes please", "go on", "", None])
    def test_an_assent_or_empty_message_is_unknown_and_changes_nothing(self, msg):
        assert request_mood(msg) == UNKNOWN
        assert standing_grant_applies(request_mood(msg), kind="mutation") is True

    def test_a_question_that_is_really_a_write_is_not_inspect(self):
        """"Can you add a chapter?" is interrogative and is a WRITE. Anchoring on '?' instead of
        on verbs would have caught it — which is why the matcher is verb-anchored."""
        assert request_mood("Can you add a chapter for me?") == CONSTRUCT


class TestTheSpendAxisIsUntouched:
    """The two consents are orthogonal by design (see db/tool_approvals). A paid READ is a normal
    thing to do on an inspect turn; moderating that grant would prompt for exactly what the author
    asked for."""

    @pytest.mark.parametrize("mood", [INSPECT, CONSTRUCT, UNKNOWN])
    def test_a_standing_spend_grant_always_applies(self, mood):
        assert standing_grant_applies(mood, kind="spend") is True


class TestItIsActuallyWiredToTheGate:
    """A rule that is never consulted is a dead mechanism — this loop has shipped that twice."""

    @pytest.mark.parametrize("needle", [
        "_turn_mood = request_mood(user_message_content)",
        "standing_grant_applies(_turn_mood, kind=kind)",
        "from app.services.request_mood import request_mood, standing_grant_applies",
    ])
    def test_the_chain_from_the_message_to_the_decision_exists(self, needle):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert needle in src

    def test_only_a_standing_ALLOW_is_moderated_never_a_DENY(self):
        """A standing refusal must hold in every mood — re-asking for something the user already
        refused forever is the consent defect this table was built to close."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
        assert 'if _decision == "allow" and not standing_grant_applies(' in src
