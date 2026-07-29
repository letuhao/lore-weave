"""scripts/motif_translate.py — the parts that decide what gets translated and what
gets written. No model calls; the LLM loop itself is i18n_translate's, already proven
in production use on the FE locales.

What is worth guarding here is everything that could LOSE work silently:
  · gap-fill must CARRY an existing good translation, never re-spend on it and never
    clobber a hand-corrected string
  · a key that failed every heal round must ship as its English source, never blank
  · a drifted beat/role key must fail LOUDLY at assembly, because at runtime it would
    merely fail to merge while the file on disk still looks complete
  · a human-authored language must be unreachable without an explicit override
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO / "scripts"))

import motif_translate as mt  # noqa: E402
from app.motif_i18n import TranslationFileError  # noqa: E402


def _motif(code="mystery.witness", **over):
    m = {
        "code": code,
        "kind": "sequence",
        "category": "mystery.testimony",
        "genre_tags": ["mystery"],
        "tension_target": 3,
        "name": "The Witness Who Lies",
        "summary": "a statement contradicts one small checkable thing",
        "emotion_target": "tension",
        "roles": [{"key": "witness", "actant": "subject", "label": "the witness",
                   "constraints": ["must have been present"]}],
        "beats": [
            {"key": "testify", "label": "The account is given", "intent": "a coherent account",
             "tension_target": 2, "order": 1},
            {"key": "press", "label": "The lie is pressed", "intent": "the gap is put to them",
             "tension_target": 4, "order": 2},
        ],
        "preconditions": [{"text": "someone saw something"}],
        "effects": [{"text": "the frame of the case moves"}],
        "examples": [{"text": "He was not at the warehouse."}],
    }
    m.update(over)
    return m


@pytest.fixture
def packdir(tmp_path, monkeypatch):
    """Redirect the tool at a temp translations tree — it writes real files."""
    monkeypatch.setattr(mt, "TRANSLATION_DIR", tmp_path / "translations")
    return tmp_path


# ── what reaches the model ─────────────────────────────────────────────────
def test_structure_is_never_sent_for_translation():
    """`tension_target`, `order`, `category`, `genre_tags`, the greimas `actant` are
    machine values. A model asked to 'localize' them would happily return a translated
    number or a renamed actant, and the merge would take it."""
    entry = mt.entry_of(_motif())
    blob = json.dumps(entry, ensure_ascii=False)
    for structural in ("tension_target", "order", "actant", "genre_tags", "category", "mystery.witness"):
        assert structural not in blob, f"{structural} must not reach the translator"
    assert entry["name"] and entry["beats"]["testify"]["label"]


def test_flat_keys_carry_the_beat_key_so_verify_catches_drift():
    """The chunk keys ARE the join keys. That is what makes i18n_translate's key-set
    identity check double as the key-invariance check for this corpus."""
    plan = mt.plan_pack("ja", "mystery", [_motif()], force=True, retry_keys=frozenset())
    keys = {k for chunk in plan["chunks"] for k in chunk}
    assert any(k.endswith("beats.testify.label") for k in keys)
    assert any(k.endswith("roles.witness.label") for k in keys)


# ── gap-fill ───────────────────────────────────────────────────────────────
def test_existing_translation_is_carried_not_re_spent(packdir):
    """A resume must not pay to re-translate what is already good — and, more
    importantly, must not overwrite a string a human went in and fixed."""
    out = packdir / "translations" / "ja" / "mystery.json"
    out.parent.mkdir(parents=True)
    entry = mt.entry_of(_motif())
    entry["name"] = "人の手で直した名前"          # a hand-corrected string
    out.write_text(json.dumps({"mystery.witness": entry}, ensure_ascii=False), encoding="utf-8")

    plan = mt.plan_pack("ja", "mystery", [_motif()], force=False, retry_keys=frozenset())
    assert plan["chunks"] == [], "a complete file must cost nothing on resume"
    assert plan["carry"]["mystery.witness|name"] == "人の手で直した名前"


def test_only_the_missing_keys_are_chunked(packdir):
    out = packdir / "translations" / "ja" / "mystery.json"
    out.parent.mkdir(parents=True)
    entry = mt.entry_of(_motif())
    del entry["beats"]["press"]                   # one beat never translated
    out.write_text(json.dumps({"mystery.witness": entry}, ensure_ascii=False), encoding="utf-8")

    plan = mt.plan_pack("ja", "mystery", [_motif()], force=False, retry_keys=frozenset())
    todo = {k for chunk in plan["chunks"] for k in chunk}
    assert todo == {"mystery.witness|beats.press.label", "mystery.witness|beats.press.intent"}


def test_a_key_listed_in_FAILED_is_retried_even_though_present(packdir):
    """A heal-exhausted key ships as its ENGLISH source, which is structurally
    indistinguishable from a real translation — so without the _FAILED list a re-run
    would carry it forever and the English would be permanent."""
    out = packdir / "translations" / "ja" / "mystery.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"mystery.witness": mt.entry_of(_motif())}, ensure_ascii=False),
                   encoding="utf-8")

    plan = mt.plan_pack("ja", "mystery", [_motif()], force=False,
                        retry_keys=frozenset({"mystery.witness|name"}))
    todo = {k for chunk in plan["chunks"] for k in chunk}
    assert todo == {"mystery.witness|name"}


def test_force_re_chunks_everything(packdir):
    out = packdir / "translations" / "ja" / "mystery.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"mystery.witness": mt.entry_of(_motif())}, ensure_ascii=False),
                   encoding="utf-8")
    plan = mt.plan_pack("ja", "mystery", [_motif()], force=True, retry_keys=frozenset())
    assert plan["n_new"] == plan["n_keys"] > 0


# ── assembly ───────────────────────────────────────────────────────────────
def test_an_untranslated_key_falls_back_to_english_never_blank(packdir):
    """A blank name renders as an empty motif card — which reads as data loss, not as
    a missing translation. i18n_translate made the same call for the same reason."""
    plan = mt.plan_pack("ja", "mystery", [_motif()], force=True, retry_keys=frozenset())
    plan["results"] = {}                          # every chunk 'failed'
    r = mt.assemble(plan, [_motif()])

    doc = json.loads(plan["out_path"].read_text(encoding="utf-8"))
    assert doc["mystery.witness"]["name"] == "The Witness Who Lies"
    assert r["codes"] == 1


def test_translated_values_land_on_the_right_beat(packdir):
    plan = mt.plan_pack("ja", "mystery", [_motif()], force=True, retry_keys=frozenset())
    plan["results"] = {
        i: {k: f"JA::{v}" for k, v in chunk.items()}
        for i, chunk in enumerate(plan["chunks"])
    }
    mt.assemble(plan, [_motif()])

    doc = json.loads(plan["out_path"].read_text(encoding="utf-8"))
    beats = doc["mystery.witness"]["beats"]
    assert beats["testify"]["label"] == "JA::The account is given"
    assert beats["press"]["label"] == "JA::The lie is pressed"


def test_a_drifted_key_fails_assembly_loudly(packdir):
    """THE structural gate. At runtime a drifted key does not raise — the translation
    just silently stops applying, while the committed file still looks complete. So it
    has to be caught here, before anything is reported as translated."""
    plan = mt.plan_pack("ja", "mystery", [_motif()], force=True, retry_keys=frozenset())
    plan["results"] = {0: {"mystery.witness|beats.typo_key.label": "x"}}
    plan["chunks"] = [{"mystery.witness|beats.typo_key.label": "x"}]

    with pytest.raises(TranslationFileError, match="unknown key"):
        mt.assemble(plan, [_motif()])


# ── the authored-language guard ────────────────────────────────────────────
def test_vi_is_declared_authored_in_both_the_tool_and_the_seeder():
    """Two independent guards protect the hand-written Vietnamese: this script refuses
    to write the language at all, and the seeder's upsert refuses to let a 'machine'
    row overwrite an 'authored' one. They must agree on WHICH languages those are —
    if they drift, one guard silently stops covering."""
    from app.db.seed_motifs import _AUTHORED_LANGUAGES

    assert mt.AUTHORED_LANGUAGES == _AUTHORED_LANGUAGES
    assert "vi" in mt.AUTHORED_LANGUAGES
