from app.workers.glossary_translate_prompt import (
    entity_output_budget,
    parse_translation_response,
)


def test_parse_translation_response_strips_fence():
    raw = '```json\n{"name": "Diễm Ma", "description": "Ác ma"}\n```'
    out = parse_translation_response(raw, {"name", "description"})
    assert out == {"name": "Diễm Ma", "description": "Ác ma"}


def test_parse_ignores_unknown_codes():
    out = parse_translation_response('{"name": "A", "extra": "B"}', {"name"})
    assert out == {"name": "A"}


# bug #8 — per-entity output budget.

def test_output_budget_small_entity_floors_at_4096():
    """A short entity stays at the old 4096 floor — no regression, no truncation risk."""
    attrs = [{"code": "name", "original_value": "Li Yun"}]
    assert entity_output_budget(attrs) == 4096


def test_output_budget_grows_past_floor_for_a_large_entity():
    """A long-description entity exceeds 4096 — the exact case the flat cap truncated.
    The budget must scale above the floor so the structured JSON is not cut off."""
    long_desc = "A young cultivator from the Cloud Sect. " * 400  # ~16k chars
    attrs = [
        {"code": "name", "original_value": "Li Yun"},
        {"code": "description", "original_value": long_desc},
    ]
    budget = entity_output_budget(attrs)
    assert budget > 4096
    # ~16k Latin chars / 4.0 chars-per-token ≈ 4000 source tokens × 3 expansion ≈ 12k.
    assert budget > 10000


def test_output_budget_clamped_to_ceiling():
    """A pathological entity cannot request an absurd budget — the ceiling caps it
    (true chunking across calls is #26, out of scope here)."""
    huge = "word " * 100_000  # ~125k tokens of source
    attrs = [{"code": "description", "original_value": huge}]
    assert entity_output_budget(attrs, ceiling=20000) == 20000


def test_output_budget_handles_missing_and_none_values():
    """Robust to absent/None original_value (drop-safe) — still returns the floor."""
    attrs = [{"code": "name"}, {"code": "title", "original_value": None}]
    assert entity_output_budget(attrs) == 4096


def test_output_budget_cjk_expands_more_than_latin():
    """CJK source packs ~0.67 tokens/char vs Latin ~0.25 — a CJK value of the same
    char count yields a larger budget, the script the failures were reported on (zh)."""
    n = 5000
    cjk = entity_output_budget([{"code": "description", "original_value": "界" * n}])
    latin = entity_output_budget([{"code": "description", "original_value": "a" * n}])
    assert cjk > latin
