"""28 AN-9 / AN-C2 — the discovery scent must name the three orientation reads.

This is B1, the slice whose ABSENCE was the run's DR-A: the book-package RUN-STATE marked
C2/C3 [x] using C3's evidence, but C2 (the static scent naming the tools in book_context_note)
was never written — grep of chat-service for the tool names returned 0. AN-11's S06 replay gate
measures exactly this: the agent using composition_package_tree as its orientation + verification
read. This pins the scent so it can never silently regress again.
"""
from app.services.stream_service import _ORIENTATION_SCENT


def test_scent_names_all_three_orientation_tools():
    for tool in (
        "composition_package_tree",
        "composition_diagnostics",
        "composition_find_references",
    ):
        assert tool in _ORIENTATION_SCENT, f"the orientation scent must name {tool} (AN-9)"


def test_scent_carries_the_F7_verification_nudge():
    # AN-11's honesty guard: package_tree is the VERIFICATION read before an "it's set up" claim.
    assert "verify" in _ORIENTATION_SCENT.lower()
    assert "composition_package_tree" in _ORIENTATION_SCENT


def test_scent_is_static_and_tight():
    # AN-9: static text, no per-turn fetch, kept tight (steering is taxed every turn).
    assert "{" not in _ORIENTATION_SCENT and "}" not in _ORIENTATION_SCENT  # no f-string holes
    assert len(_ORIENTATION_SCENT) < 500
