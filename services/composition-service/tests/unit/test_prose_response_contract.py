"""T1 / L2 — composition_get_prose reference-first contract (spec §6b, §14b).

get_prose is a SINGLE-object read (not a list), so it doesn't use
`apply_response_contract`; instead `detail=summary` drops the one heavy field (the
chapter `body`, routinely thousands of tokens) while KEEPING the `draft_version`
concurrency token + the rest of the metadata. This pins that projection: if someone
stops dropping the body at summary, or drops the version token, this goes red.
"""

from app.mcp.server import _project_prose, _PROSE_BODY_KEY


def _draft(**over) -> dict:
    base = {
        "body": {"type": "doc", "content": [{"type": "paragraph", "text": "x" * 5000}]},
        "draft_version": 7,
        "body_format": "json",
        "base_revision_id": "rev-abc",
        "word_count": 1200,
    }
    base.update(over)
    return base


class TestProseDetail:
    def test_summary_drops_the_body(self):
        out = _project_prose(_draft(), "summary")
        assert _PROSE_BODY_KEY not in out
        assert out["body_omitted"] is True
        assert out["detail"] == "summary"

    def test_summary_keeps_concurrency_token_and_metadata(self):
        out = _project_prose(_draft(), "summary")
        # the draft_version is load-bearing (write_prose requires it) — must survive
        assert out["draft_version"] == 7
        assert out["base_revision_id"] == "rev-abc"
        assert out["body_format"] == "json"
        assert out["word_count"] == 1200

    def test_full_returns_the_draft_unchanged(self):
        d = _draft()
        out = _project_prose(d, "full")
        assert out is d  # no projection at full — byte-identical, versioned default
        assert out["body"]

    def test_summary_is_materially_smaller(self):
        d = _draft()
        summ = _project_prose(d, "summary")
        assert len(str(summ)) < len(str(d)) * 0.4

    def test_missing_body_is_tolerated(self):
        # a draft with no body key still summarizes cleanly (no KeyError)
        out = _project_prose({"draft_version": 1, "base_revision_id": None}, "summary")
        assert out["draft_version"] == 1
        assert out["body_omitted"] is True
