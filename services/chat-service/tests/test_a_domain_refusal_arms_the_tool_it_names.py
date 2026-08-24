"""D-A-DOMAIN-REFUSAL-NAMES-A-TOOL-AND-ARMS-NOTHING.

Arming — putting a tool a refusal NAMES onto the wire so the model can obey — runs at two sites:
the missing-required-arguments interception, and D-FJ-4 on the dispatch result.

🔴 I FIRST RECORDED THIS AS "exactly ONE site", AND THAT WAS WRONG — a head-limited grep hid the
second. The substantive gap survived the correction and is narrower than the overstatement:
NEITHER site fired for a refusal reported in the RESULT BODY, because D-FJ-4 was gated on
`not ok` and `ok` is the ENVELOPE's status. The call succeeded; the body says the request did
not. composition-service uses that shape throughout:

    {"success": False, "error": "NOT_A_DERIVATIVE — … Call composition_list_derivatives …"}

MEASURED 2026-08-24, batch c-override12, K=5, gemma-4-26b-a4b-qat, from
`chat_messages.advertised_tools`:

    composition_entity_override_edit   advertised 5 of 5
    composition_list_derivatives       advertised 0 of 5   <- the tool its refusal names

The model was given that instruction on every run and could not see the tool on any of them. It
reached for `composition_list_canon_rules`, `composition_list_outline` and
`composition_package_tree` — the composition reads it COULD see — and every one refused.

These tests hold the two halves of the seam that made this invisible: a body-level refusal is
recognised, and an ordinary SUCCESS is not mistaken for one. The arming itself reuses the
missing-args site's helper unchanged, so its two safety properties — only CATALOGUE names arm
anything, and `_arm_tools` respects the context budget — are inherited rather than restated.
"""
from __future__ import annotations

from app.services.stream_service import _tools_named_in_refusal


def _cat(*names: str) -> dict:
    return {n: {"type": "function", "function": {"name": n, "description": ""}} for n in names}


NOT_A_DERIVATIVE = (
    "NOT_A_DERIVATIVE — this project_id is the book's CANONICAL Work, and an override exists "
    "only on a dị bản. Call composition_list_derivatives and pass it THIS SAME project_id — it "
    "lists every Work of the book — then retry with the project_id of the entry whose "
    "is_canonical is false. Only if that list has no derivative should you create one with "
    "composition_create_derivative."
)


class TestTheRefusalTextResolvesToRealTools:
    """The measured message must actually yield the tool it names. If this stops holding, the
    arming below fires on nothing and the fix is inert."""

    def test_it_finds_the_lookup_the_message_names(self):
        got = _tools_named_in_refusal(
            NOT_A_DERIVATIVE,
            _cat("composition_list_derivatives", "composition_create_derivative"),
            set(),
            exclude="composition_entity_override_edit",
        )
        assert "composition_list_derivatives" in got

    def test_a_name_that_is_not_in_the_catalogue_arms_nothing(self):
        """The safety property this inherits: a refusal is model-visible text, so a name that
        is not a real tool must never become one."""
        got = _tools_named_in_refusal(
            "call composition_invent_a_tool first",
            _cat("composition_list_derivatives"),
            set(),
            exclude="",
        )
        assert got == [] or "composition_invent_a_tool" not in got

    def test_a_tool_already_on_the_wire_is_not_re_armed(self):
        got = _tools_named_in_refusal(
            NOT_A_DERIVATIVE,
            _cat("composition_list_derivatives"),
            {"composition_list_derivatives"},
            exclude="",
        )
        assert "composition_list_derivatives" not in got

    def test_the_refusING_tool_never_arms_itself(self):
        """Otherwise a tool that refuses could keep itself alive on its own message."""
        got = _tools_named_in_refusal(
            "call composition_entity_override_edit again",
            _cat("composition_entity_override_edit"),
            set(),
            exclude="composition_entity_override_edit",
        )
        assert "composition_entity_override_edit" not in got


class TestTheSeamThatMadeItInvisible:
    """A body-level refusal arrives with the envelope reporting SUCCESS. That is the whole
    reason this class of message never reached the arming site, so it is asserted directly
    rather than left implicit in the dispatch code."""

    @staticmethod
    def _refusal_text(ok: bool, envelope: dict, payload) -> str:
        """The exact classification the dispatch site performs."""
        if not ok:
            return str(envelope.get("error") or "")
        if isinstance(payload, dict) and payload.get("success") is False:
            return str(payload.get("error") or "")
        return ""

    def test_a_body_level_refusal_on_an_ok_envelope_is_recognised(self):
        text = self._refusal_text(
            True, {}, {"success": False, "error": NOT_A_DERIVATIVE})
        assert "composition_list_derivatives" in text

    def test_an_envelope_error_is_still_recognised(self):
        text = self._refusal_text(False, {"error": NOT_A_DERIVATIVE}, None)
        assert "composition_list_derivatives" in text

    def test_an_ordinary_SUCCESS_is_not_treated_as_a_refusal(self):
        """The control. Arming off a successful result would put tools on the wire because a
        payload happened to mention them — the opposite of what this is for."""
        assert self._refusal_text(
            True, {}, {"success": True, "works": [{"project_id": "x"}]}) == ""

    def test_a_payload_that_is_not_a_dict_is_not_a_refusal(self):
        for payload in ("some prose", ["a", "list"], None, 7):
            assert self._refusal_text(True, {}, payload) == ""

    def test_success_absent_is_not_a_refusal(self):
        """Most read tools never set `success` at all. Only an explicit False counts, or every
        read result would be scanned as a refusal."""
        assert self._refusal_text(True, {}, {"items": [], "error": "unused"}) == ""


class TestTheDispatchSiteActuallyDoesIt:
    """The half that makes the rest matter: a helper nobody calls is a mechanism that never
    runs, and this loop has shipped one of those before."""

    # 🔴 THESE USED TO SLICE A CHAR WINDOW AFTER THE MARKER, AND IT BROKE TWICE ON EDITS
    # NEARBY — each time tempting a widen-without-reading, which is how a window ends up
    # covering the whole file and asserting nothing. The block is now delimited STRUCTURALLY,
    # from the marker to the `working.append` that ends the dispatch step, so it grows with the
    # code instead of against it.
    @staticmethod
    def _block(marker: str) -> str:
        src = TestTheDispatchSiteActuallyDoesIt._src()
        i = src.find(marker)
        assert i != -1, f"{marker!r} is gone from stream_service"
        j = src.find('working.append({', i)
        assert j > i, "the dispatch step's end marker moved"
        return src[i:j]

    @staticmethod
    def _src() -> str:
        import inspect

        from app.services import stream_service

        return inspect.getsource(stream_service)

    def test_the_dispatch_result_still_resolves_AND_arms(self):
        """Resolving names without arming them is the original bug in miniature, so both halves
        are asserted in the same block."""
        block = self._block("D-A-DOMAIN-REFUSAL-NAMES-A-TOOL-AND-ARMS-NOTHING")
        assert "_tools_named_in_refusal(" in block, "it no longer resolves names"
        assert "_arm_tools(" in block, "it resolves names and arms nothing"
        assert "[SYSTEM] " in block, (
            "it arms silently — the [SYSTEM] note is what actually tells the model the tool is "
            "now callable"
        )

    def test_the_dispatch_site_is_no_longer_gated_on_the_envelope_alone(self):
        """The actual defect, asserted where it lived. An earlier version of this test counted
        CALL SITES and passed against the unfixed tree — the second site already existed, so the
        count was never the defect. What was wrong is the CONDITION."""
        block = self._block("D-FJ-4 — ARM THE TOOLS THE REFUSAL NAMED")
        assert 'tool_payload.get("success") is False' in block, (
            "the dispatch arming still fires only on an envelope error, so a tool that reports "
            "its refusal in the result body arms nothing"
        )
        assert "if _refusal_text and discovery:" in block

    def test_it_did_not_grow_a_third_arming_site(self):
        """My first attempt added one beside D-FJ-4, which duplicated the envelope case and
        armed silently — without the [SYSTEM] note that is what actually tells the model."""
        src = self._src()
        calls = src.count("_tools_named_in_refusal(") - src.count("def _tools_named_in_refusal(")
        assert calls == 2, f"{calls} call sites — arming should have exactly two homes"
