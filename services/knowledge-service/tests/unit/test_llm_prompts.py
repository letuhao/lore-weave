"""K17.1 — unit tests for the LLM extraction prompt loader.

Pure-python, no LLM calls. Exercises substitution, strict-missing-key
behavior, unknown-prompt rejection, and the closed-set guard.
"""

from __future__ import annotations

import pytest

from app.extraction.llm_prompts import (
    ALLOWED_PROMPT_NAMES,
    load_prompt,
)


# ── happy path: every prompt loads and substitutes ───────────────────


@pytest.mark.parametrize("name", sorted(ALLOWED_PROMPT_NAMES))
def test_k17_1_load_every_prompt(name):
    out = load_prompt(
        name,
        text="Kai left Harbin.",
        known_entities='["Kai", "Harbin"]',
    )
    assert "Kai left Harbin." in out
    assert "{text}" not in out
    assert "{known_entities}" not in out
    # Each prompt must instruct "return only the JSON object" so
    # K17.3 parser can rely on a stable marker.
    assert "Return only the JSON object" in out or "return only the JSON object" in out.lower()


# ── strict-missing-key ───────────────────────────────────────────────


def test_k17_1_missing_substitution_raises():
    with pytest.raises(KeyError, match="not provided"):
        load_prompt("entity", text="hello")  # missing known_entities


def test_k17_1_extra_substitution_is_ignored():
    """Extra kwargs not referenced by the template are silently
    ignored — format_map only pulls the keys it finds in the
    template. This is a deliberate relaxation so callers can pass
    a superset without knowing each template's exact vars."""
    out = load_prompt(
        "entity",
        text="x",
        known_entities="[]",
        unused_extra="should not raise",
    )
    assert "x" in out


# ── unknown-name guard ───────────────────────────────────────────────


def test_k17_1_unknown_prompt_raises():
    with pytest.raises(KeyError, match="unknown prompt"):
        load_prompt("does_not_exist", text="x", known_entities="[]")


def test_k17_1_path_traversal_rejected():
    """The closed ALLOWED_PROMPT_NAMES set prevents a caller from
    loading an arbitrary file via ../ tricks."""
    with pytest.raises(KeyError, match="unknown prompt"):
        load_prompt("../../../etc/passwd", text="x", known_entities="[]")


# ── JSON fence integrity (no accidental format_map expansion) ───────


# ── R1/I3: every prompt must declare both placeholders ────────────


@pytest.mark.parametrize("name", sorted(ALLOWED_PROMPT_NAMES))
def test_k17_1_every_prompt_has_required_placeholders(name):
    """A future edit that accidentally deletes `{text}` or
    `{known_entities}` from a template would let `load_prompt`
    silently return a half-substituted string. Catch that drift
    by asserting both placeholders appear in the pre-substitution
    source."""
    from app.extraction.llm_prompts import _load_raw
    raw = _load_raw(name)
    assert "{text}" in raw, f"{name}: missing {{text}} placeholder"
    assert "{known_entities}" in raw, (
        f"{name}: missing {{known_entities}} placeholder"
    )


@pytest.mark.parametrize("name", sorted(ALLOWED_PROMPT_NAMES))
def test_k17_1_json_fences_survive_substitution(name):
    """The markdown examples contain `{` and `}` which MUST be
    escaped as `{{` `}}` so format_map leaves them as literal
    braces. If a prompt author forgets the escape, format_map
    raises KeyError when the placeholder happens to look like a
    valid key — this test catches that regression."""
    out = load_prompt(
        name,
        text="probe",
        known_entities="[]",
    )
    # Output should contain literal single `{` from the JSON
    # example blocks (post-unescape) and no double-brace artifacts.
    assert "{{" not in out
    assert "}}" not in out
    assert "{" in out
    assert "}" in out
