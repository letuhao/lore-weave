from app.workers.glossary_translate_prompt import parse_translation_response


def test_parse_translation_response_strips_fence():
    raw = '```json\n{"name": "Diễm Ma", "description": "Ác ma"}\n```'
    out = parse_translation_response(raw, {"name", "description"})
    assert out == {"name": "Diễm Ma", "description": "Ác ma"}


def test_parse_ignores_unknown_codes():
    out = parse_translation_response('{"name": "A", "extra": "B"}', {"name"})
    assert out == {"name": "A"}
