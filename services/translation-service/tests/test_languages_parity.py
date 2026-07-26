"""D-4/D13 — the translation-service language mirror (app/languages.py) must stay in exact
parity with the SSOT (contracts/languages.contract.json), and the normalize→validate write
rule must behave as specified. The frontend has the twin parity test (LANGUAGE_REGISTRY).

Hermetic (no DB / no app config) — pure data + functions.
"""
import json
from pathlib import Path

from app.languages import (
    LANGUAGE_REGISTRY,
    TRANSLATION_TARGET_CODES,
    is_translation_target,
    normalize_language,
)

_CONTRACT = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "languages.contract.json").read_text(encoding="utf-8")
)


def test_registry_matches_contract_exactly():
    """Same entries, same order, same fields as the SSOT."""
    assert LANGUAGE_REGISTRY == _CONTRACT["languages"]


def test_codes_unique():
    codes = [e["code"] for e in LANGUAGE_REGISTRY]
    assert len(set(codes)) == len(codes)


def test_translation_targets_derive_from_flag():
    expected = [e["code"] for e in _CONTRACT["languages"] if e["translationTarget"]]
    assert TRANSLATION_TARGET_CODES == expected


def test_normalize_language_canonicalizes_lenient_input():
    assert normalize_language("VI") == "vi"
    assert normalize_language("zh_CN") == "zh-CN"
    assert normalize_language("en-us") == "en-US"
    assert normalize_language("pt_br") == "pt-BR"
    # an unknown free-text string just lower-cases; the registry check rejects it downstream
    assert normalize_language("Vietnamese") == "vietnamese"


def test_write_rule_accepts_registry_rejects_free_text():
    # "VI" → normalize → "vi" → accepted
    assert is_translation_target(normalize_language("VI")) is True
    assert is_translation_target(normalize_language("zh_CN")) is True
    # the legacy free-text value that first polluted the store → rejected
    assert is_translation_target(normalize_language("Vietnamese")) is False
    # a plausible but unlisted code → rejected (add a registry row to enable)
    assert is_translation_target("pl") is False


def test_mcp_literal_in_parity_with_registry():
    """The MCP write-arg enum (Literal) must equal the registry target set — the module-level
    assert in app/mcp/server.py enforces this at import; assert it here explicitly too."""
    from app.mcp.server import TargetLangCode

    assert set(TargetLangCode.__args__) == set(TRANSLATION_TARGET_CODES)
