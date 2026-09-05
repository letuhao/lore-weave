"""`skill_router_preload` — both states of the DQ-T90 A/B lever.

The repo's flag gate is explicit about why this file has to exist: "A kill-switch whose OFF path
is never exercised is an untested branch you would first run during an incident." It is also the
arm of a measurement, so an OFF path that silently still called the router would make the A/B
report the control twice and no one would see it.

WHAT THE FLAG DOES. ON (the shipped default) the Intent→Skill Router cosine-ranks the turn's
intent and preloads the top `ROUTER_MAX_ADDITIONS` skill bodies. OFF, the turn keeps its
base/pinned/mode-bound skills and the L1 index, and the model pulls a body itself with
`load_skill` — the twin of `tool_load`.

WHY THE ARM IS WORTH RUNNING (DQ-T90): all 66 of 66 pairs of distinct skills are more similar to
each other than the 0.35 floor a skill must clear to be injected, so no cap and no threshold can
rank them; meanwhile `load_skill` is advertised on 5,982 messages, has never failed (66 of 66 ok)
and is used in 7 sessions against `tool_load`'s 123.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import skill_registry  # noqa: E402

BASE_KWARGS = dict(
    # `agui` is load-bearing: resolve_skills_to_inject_async returns `base` before the
    # router on any other stream_format, so a "text" fixture would exercise an early
    # return and pass whatever the flag did. Caught by this test failing on its ON arm.
    enabled_skills=[], stream_format="agui", disable_tools=False,
    tool_calling_enabled=True, editor=False, book_scoped=True, admin=False,
    intent_text="Is my story bible out of date? Apply the standard updates if there are any.",
    user_id="00000000-0000-0000-0000-000000000001",
)


@pytest.fixture()
def router_returns_marker(monkeypatch):
    """Stand in for the router so the assertion is about the FLAG, not about embeddings.

    The real router needs an embedding provider; a test that depended on one would be measuring
    the provider's availability. The marker skill is a code the static path can never produce,
    so its presence proves the router ran and its absence proves it did not.
    """
    called: list[bool] = []

    async def _fake(**_kw):
        called.append(True)
        return ["translation"]

    import app.services.skill_router as sr
    monkeypatch.setattr(sr, "route_additional_skills", _fake)
    return called


@pytest.mark.asyncio
async def test_ON_the_router_runs_and_its_pick_is_injected(router_returns_marker, monkeypatch):
    monkeypatch.setattr(skill_registry_settings(), "skill_router_preload", True, raising=False)
    out = await skill_registry.resolve_skills_to_inject_async(**BASE_KWARGS)
    assert router_returns_marker, "the router was not consulted with the preload ON"
    assert "translation" in out, (
        f"the router returned a skill and it did not reach the injected set: {out}")


@pytest.mark.asyncio
async def test_OFF_the_router_is_NOT_consulted_at_all(router_returns_marker, monkeypatch):
    """🔴 THE ASSERTION THAT MAKES THE A/B MEAN ANYTHING. Checking only that the marker is absent
    from the output would also pass if the router ran and its result were dropped later — the arm
    would be paying for embeddings it does not use, and a token comparison between the arms would
    be wrong. So this asserts the router was never CALLED."""
    monkeypatch.setattr(skill_registry_settings(), "skill_router_preload", False, raising=False)
    out = await skill_registry.resolve_skills_to_inject_async(**BASE_KWARGS)
    assert not router_returns_marker, (
        "the preload is OFF and the router was still consulted — arm (e) would be measuring the "
        "control with extra steps")
    assert "translation" not in out, f"the router's pick reached the set with the flag off: {out}"


def test_the_default_is_ON_so_the_CONTROL_arm_is_the_shipped_path():
    """A default that flipped would silently make every run the experiment."""
    assert skill_registry_settings().skill_router_preload is True


def skill_registry_settings():
    from app.config import settings

    return settings


class TestTheContrastiveTextsAreTheOnesEmbedded:
    """`skill_contrastive_desc` — DQ-T90 arm (b), both states.

    The arm rewrites what the ROUTER embeds, not what the reader sees, so the assertion has to be
    on `_skill_embedding_text`. Getting this wrong would be invisible: the arm would run, cost a
    batch, and measure the control.
    """

    def test_OFF_the_L1_description_is_embedded(self, monkeypatch):
        from app.services import skill_router as sr

        monkeypatch.setattr(skill_registry_settings(), "skill_contrastive_desc", False,
                            raising=False)
        text = sr._skill_embedding_text("book")
        assert "save and restore draft revisions" in text, (
            "the shipped L1 description is not what the router embedded with the flag off")

    def test_ON_the_contrastive_text_replaces_it(self, monkeypatch):
        from app.services import skill_router as sr

        monkeypatch.setattr(skill_registry_settings(), "skill_contrastive_desc", True,
                            raising=False)
        text = sr._skill_embedding_text("book")
        assert "librarianship, not authorship" in text
        assert "save and restore draft revisions" not in text, (
            "the flag is on and the old description is still what gets embedded")

    def test_the_collision_that_motivated_the_arm_is_actually_addressed(self, monkeypatch):
        """🔴 NON-VACUITY. Both texts could differ while still sharing the vocabulary that made
        `book` and `translation` the closest pair in the catalogue (0.7715). The arm is worthless
        if the replacements still both say 'chapters' and 'publish', so that is asserted directly
        rather than assumed from the fact that the strings changed."""
        from app.services import skill_router as sr

        monkeypatch.setattr(skill_registry_settings(), "skill_contrastive_desc", True,
                            raising=False)
        book = sr._skill_embedding_text("book").lower()
        translation = sr._skill_embedding_text("translation").lower()
        shared = {w for w in ("chapters", "publish") if w in book and w in translation}
        assert not shared, (
            f"the contrastive texts still share {shared} — the exact tokens that put these two at "
            "0.7715 cosine, the closest pair in the catalogue")
