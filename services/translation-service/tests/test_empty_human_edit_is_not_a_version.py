"""An empty human edit was saved as a real translation version.

FOUND 2026-08-22 by the tool deep-dive's SHIP probe (batch 36), against the live service on a
seeded chapter that already had one llm version:

    translated_body=""     -> {"success": true, "version_id": "…8877…", "version_num": 2}
    translated_body="   "  -> {"success": true, "version_id": "…8924…", "version_num": 3}

Neither was refused, and both reported success.

WHY IT MATTERS. This is the path a human editor's saved translation takes — the new row is
written with authored_by='human'. An empty save is not a no-op: it mints a real version that sits
in the chapter's version list looking like a human edit, and translation_set_active_version can
later publish it to readers. The tool does NOT auto-activate (it says so, and that held), which is
why this was latent rather than an incident.

THE CONTRACT WAS ALREADY WRITTEN DOWN AND SIMPLY NOT ENFORCED. SaveEditedTranslationRequest's own
docstring says "One of translated_body / translated_body_json must be present." That sentence has
been there all along; nothing checked it. This repo has a name for that shape — a closed set or an
invariant recorded in prose, in the one place the validator never reads.

WHERE THE FIX LIVES. On the MODEL, not in the route. The REST handler
(routers/versions.py::save_edited_version) and the MCP tool
(mcp/server.py::translation_save_edited_version) both build this same request object, so enforcing
it once covers both surfaces; enforcing it in the route would leave the other caller open, which
is the "guard the call site, not just one of them" mistake in reverse.

WHAT IT DOES NOT FIX: a body that is non-empty but meaningless (a single character, or the
untouched LLM text saved back unchanged). Those are real versions by any mechanical definition and
are out of scope here.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import SaveEditedTranslationRequest


def _req(**kw):
    return SaveEditedTranslationRequest(
        target_language="vi", edited_from_version_id=uuid4(), **kw)


class TestAnEmptyEditIsRefused:
    def test_empty_string_body(self):
        """The exact call measured against the live service."""
        with pytest.raises(ValidationError):
            _req(translated_body="")

    def test_whitespace_only_body(self):
        """Whitespace is not content — it also produced a version_num on the live service."""
        with pytest.raises(ValidationError):
            _req(translated_body="   ")

    def test_neither_field_supplied(self):
        """The docstring's own words: one of the two must be present."""
        with pytest.raises(ValidationError):
            _req()

    def test_empty_json_block_list(self):
        with pytest.raises(ValidationError):
            _req(translated_body_json=[], translated_body_format="json")

    def test_the_refusal_says_why(self):
        with pytest.raises(ValidationError) as exc:
            _req(translated_body="")
        assert "must not be empty" in str(exc.value)


class TestARealEditStillSaves:
    """The bystanders. A guard that also blocks real edits is not a fix."""

    def test_text_body(self):
        assert _req(translated_body="Thủy triều rút lúc rạng đông.").translated_body

    def test_json_block_body(self):
        r = _req(translated_body_json=[{"type": "paragraph", "text": "Thủy triều"}],
                 translated_body_format="json")
        assert len(r.translated_body_json) == 1

    def test_a_single_character_is_still_accepted(self):
        """Deliberately NOT rejected. 'Meaningless but non-empty' is a different problem and
        guessing at it here would block edits this tool exists to accept."""
        assert _req(translated_body="x").translated_body == "x"

    def test_body_with_surrounding_whitespace_is_kept_verbatim(self):
        """The guard STRIPS to decide emptiness; it must not strip what it stores, or a
        deliberate leading indent in a translated block would be silently rewritten."""
        assert _req(translated_body="  Thủy triều  ").translated_body == "  Thủy triều  "


class TestTheMCPCallSiteIsGuardedToo:
    """🔴 THE MODEL VALIDATOR ABOVE DID NOT COVER THE PATH THAT MATTERED.

    The first fix went on SaveEditedTranslationRequest, on the reasoning that the REST handler
    and the MCP tool both build it. They do not. `translation_save_edited_version` in
    app/mcp/server.py writes its INSERT directly and never constructs the request model, so the
    validator guarded the REST route and left the agent path — the one the tool deep-dive
    measured the defect on — wide open.

    That was found the only way it could be: the model fix was deployed, md5-confirmed inside the
    container, and an empty body STILL saved a version live. Guard the call site, not the helper.

    Source-level because the handler needs a live pool and a real MCP context; the behavioural
    proof is the live re-probe recorded in the batch evidence.
    """

    def _handler_src(self) -> str:
        import pathlib as _p
        src = (_p.Path(__file__).resolve().parents[1] / "app" / "mcp" / "server.py").read_text(
            encoding="utf-8")
        i = src.index("async def translation_save_edited_version")
        return src[i:src.index("INSERT INTO chapter_translations", i)]

    def test_the_mcp_tool_rejects_an_empty_body_before_it_inserts(self):
        body = self._handler_src()
        assert 'translated_body or ""' in body and ".strip()" in body, (
            "the MCP handler no longer checks translated_body before writing; a validator on "
            "SaveEditedTranslationRequest does NOT cover it, because this handler never builds "
            "that model")

    def test_the_guard_runs_before_the_insert(self):
        """Ordering is the whole point — a check after the INSERT would leave the row behind."""
        body = self._handler_src()
        assert body.index(".strip()") < len(body), "the guard must precede the INSERT statement"

    def test_the_refusal_explains_itself(self):
        assert "must not be empty" in self._handler_src()
