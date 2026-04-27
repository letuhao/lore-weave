"""K17.1 — unit tests for the LLM extraction prompt loader.

Phase 4b-α: prompt loader moved from knowledge-service into the
``loreweave_extraction`` library; this test moved alongside.

Pure-python, no LLM calls. Exercises substitution, strict-missing-key
behavior, unknown-prompt rejection, and the closed-set guard.
"""

from __future__ import annotations

import pytest

from loreweave_extraction.prompts import (
    ALLOWED_PROMPT_NAMES,
    load_prompt,
)

# Phase 4a-α-followup + 4a-β — *_system templates are SYSTEM-message-only
# without `{text}` (the chapter text rides as the user message via the
# SDK path). Tests that assume `{text}` substitution need to skip them.
SYSTEM_ONLY_PROMPT_NAMES = sorted(
    {n for n in ALLOWED_PROMPT_NAMES if n.endswith("_system")}
)
TEXT_BEARING_PROMPT_NAMES = sorted(ALLOWED_PROMPT_NAMES - set(SYSTEM_ONLY_PROMPT_NAMES))


# happy path: every prompt loads and substitutes


@pytest.mark.parametrize("name", TEXT_BEARING_PROMPT_NAMES)
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


@pytest.mark.parametrize("name", SYSTEM_ONLY_PROMPT_NAMES)
def test_k17_1_load_system_only_prompt_substitutes_known_entities_only(name):
    """Phase 4a-α-followup + 4a-β — *_system prompts have no {text}
    placeholder. The chapter text rides as the user message; the
    system message only declares instructions + known_entities."""
    out = load_prompt(name, known_entities='["Kai", "Harbin"]')
    assert '["Kai", "Harbin"]' in out
    assert "{known_entities}" not in out
    # MUST NOT have {text}: that placeholder would silently leak as
    # literal `{text}` in the prompt sent to the LLM.
    assert "{text}" not in out
    # Still has the JSON-only directive.
    assert "Return only the JSON object" in out or "return only the JSON object" in out.lower()


# strict-missing-key


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


# unknown-name guard


def test_k17_1_unknown_prompt_raises():
    with pytest.raises(KeyError, match="unknown prompt"):
        load_prompt("does_not_exist", text="x", known_entities="[]")


def test_k17_1_path_traversal_rejected():
    """The closed ALLOWED_PROMPT_NAMES set prevents a caller from
    loading an arbitrary file via ../ tricks."""
    with pytest.raises(KeyError, match="unknown prompt"):
        load_prompt("../../../etc/passwd", text="x", known_entities="[]")


# R1/I3: every prompt must declare both placeholders


@pytest.mark.parametrize("name", TEXT_BEARING_PROMPT_NAMES)
def test_k17_1_every_prompt_has_required_placeholders(name):
    """A future edit that accidentally deletes `{text}` or
    `{known_entities}` from a template would let `load_prompt`
    silently return a half-substituted string. Catch that drift
    by asserting both placeholders appear in the pre-substitution
    source."""
    from loreweave_extraction.prompts import _load_raw
    raw = _load_raw(name)
    assert "{text}" in raw, f"{name}: missing {{text}} placeholder"
    assert "{known_entities}" in raw, (
        f"{name}: missing {{known_entities}} placeholder"
    )


@pytest.mark.parametrize("name", SYSTEM_ONLY_PROMPT_NAMES)
def test_system_only_prompt_has_known_entities_but_no_text_placeholder(name):
    """Phase 4a-α-followup + 4a-β — pin the SYSTEM-only contract per
    extractor: known_entities placeholder MUST be present; text
    placeholder MUST be absent. Drift in either direction is a
    regression."""
    from loreweave_extraction.prompts import _load_raw
    raw = _load_raw(name)
    assert "{known_entities}" in raw, f"{name} missing {{known_entities}}"
    assert "{text}" not in raw, (
        f"{name} must NOT have {{text}} — text rides as user message"
    )


@pytest.mark.parametrize("name", SYSTEM_ONLY_PROMPT_NAMES)
def test_system_only_load_silently_drops_text_kwarg_documented_behavior(name):
    """Phase 4a-α-followup /review-impl LOW#4 + 4a-β — `load_prompt`
    accepts `**substitutions` and silently ignores keys the template
    doesn't reference. For *_system prompts (which have no `{text}`),
    a future maintainer might pass `text=...` thinking it gets
    substituted somewhere — it would be silently dropped.

    This test PINS the silent-drop behavior so the contributor reading
    the test file sees the explicit warning. If we ever decide to add
    a strict mode (`load_prompt(..., strict=True)`) that rejects
    unknown keys, this test should flip to assert that mode."""
    out = load_prompt(
        name,
        known_entities="[]",
        text="THIS WILL BE SILENTLY DROPPED",  # not in template
    )
    # Confirm the dropped text is NOT in the output (no surprise leak).
    assert "THIS WILL BE SILENTLY DROPPED" not in out
    # The intended use site (extractors._extract_via_llm_client) passes
    # `text` as the user message content, NOT as a load_prompt kwarg —
    # so this drop is benign in production. The test exists purely to
    # document the gotcha.


@pytest.mark.parametrize("name", TEXT_BEARING_PROMPT_NAMES)
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
