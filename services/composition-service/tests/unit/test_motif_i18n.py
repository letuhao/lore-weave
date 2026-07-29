"""MOTIF-I18N — the translatable payload, its hash, and language resolution.

The bug this whole layer replaces was SILENT: an English book's scene decomposer was
briefed in Vietnamese because a motif's language was part of its identity, so the two
languages were two unrelated rows and selection could pick either. Every test here is
written against that failure mode — the recurring theme is that a wrong or missing
translation must never be *quiet*.
"""
from __future__ import annotations

import pytest

import json

from app.motif_i18n import (
    ARC_TEMPLATE_SPEC,
    MOTIF_SPEC,
    TranslationFileError,
    build_translation_entry,
    extract_translatable,
    flatten_entry,
    is_untranslated_echo,
    parse_translation_entry,
    resolve_text,
    translatable_hash,
    unflatten_entry,
)


def _motif(**over):
    row = {
        "code": "romance.forced_proximity",
        "original_language": "en",
        "kind": "sequence",
        "category": "romance.proximity",
        "genre_tags": ["romance"],
        "tension_target": 3,
        "name": "Forced Proximity",
        "summary": "two people who keep distance lose the option of leaving",
        "emotion_target": "longing",
        "roles": [{"key": "lead", "actant": "subject", "label": "the point-of-view lead",
                   "constraints": ["cannot leave the shared space"]}],
        "beats": [
            {"key": "trapped", "label": "Shut in together", "intent": "leaving stops being an option",
             "tension_target": 2, "order": 1},
            {"key": "thaw", "label": "The argument stops", "intent": "habit gives way",
             "tension_target": 4, "order": 2},
        ],
        "preconditions": [{"text": "two parties with a reason to keep distance"}],
        "effects": [{"text": "distance can no longer be maintained by habit"}],
        "examples": [{"text": "The road washes out and there is one lamp."}],
    }
    row.update(over)
    return row


def _translation(**over):
    tr = {
        "language_code": "vi",
        "name": "Kề Cận Bắt Buộc",
        "summary": "hai người giữ khoảng cách mất đi lựa chọn rời đi",
        "emotion_target": "khắc khoải",
        "roles": [{"key": "lead", "label": "nhân vật góc nhìn"}],
        "beats": [
            {"key": "trapped", "label": "Bị nhốt chung", "intent": "rời đi không còn là lựa chọn"},
            {"key": "thaw", "label": "Cuộc cãi vã ngừng lại", "intent": "thói quen nhường bước"},
        ],
        "preconditions": [{"text": "hai bên có lý do giữ khoảng cách"}],
        "effects": [{"text": "khoảng cách không còn giữ được bằng thói quen"}],
        "examples": [{"text": "Đường sạt lở và chỉ còn một ngọn đèn."}],
        "source_content_hash": "",
    }
    tr.update(over)
    return tr


# ── what is text vs what is structure ──────────────────────────────────────
def test_extract_keeps_only_text_and_the_keys_that_join_it():
    """Structure must not reach a translator. If `tension_target` or `order` could be
    translated, a translation could silently re-pace the motif — and a translator has no
    way to know that a number they 'localized' is load-bearing."""
    payload = extract_translatable(_motif())

    assert set(payload) == {
        "name", "summary", "emotion_target",
        "roles", "beats", "preconditions", "effects", "examples",
    }
    assert "code" not in payload and "category" not in payload and "genre_tags" not in payload
    beat = payload["beats"][0]
    assert set(beat) == {"key", "label", "intent"}, (
        "a beat's tension/order are structure and must stay on the source row")
    assert set(payload["roles"][0]) == {"key", "label", "constraints"}, (
        "a role's greimas `actant` is structure, not a label")


def test_hash_is_stable_across_key_order_but_moves_with_text():
    """The staleness signal. Key ORDER is an artifact of dict construction and must not
    change the hash, or every translation would read as stale after an unrelated edit."""
    a = extract_translatable(_motif())
    b = extract_translatable(_motif())
    b = {k: b[k] for k in reversed(list(b))}
    assert translatable_hash(a) == translatable_hash(b)

    edited = extract_translatable(_motif(summary="a different summary"))
    assert translatable_hash(a) != translatable_hash(edited)


def test_hash_ignores_a_structure_only_edit():
    """Re-pacing a beat does not invalidate its wording — flagging every translation stale
    for a tension bump would make the signal meaningless, which is how a real staleness
    flag stops being read."""
    a = extract_translatable(_motif())
    beats = [dict(b) for b in _motif()["beats"]]
    beats[0]["tension_target"] = 5
    assert translatable_hash(a) == translatable_hash(extract_translatable(_motif(beats=beats)))


# ── the translation-file contract ──────────────────────────────────────────
def test_unknown_beat_key_is_rejected_not_dropped():
    """THE drift guard. A renamed beat key would make the translation stop applying while
    the file on disk still looks complete — the exact silent-failure shape this whole
    change exists to remove."""
    src = extract_translatable(_motif())
    entry = build_translation_entry(extract_translatable(_translation()))
    entry["beats"]["typo_key"] = {"label": "x"}

    with pytest.raises(TranslationFileError, match="unknown key"):
        parse_translation_entry(entry, src, where="vi/romance.json:x")


def test_a_longer_positional_list_is_rejected():
    """`preconditions`/`effects`/`examples` have no keys, so they merge by INDEX. A
    translation with MORE entries than the source cannot be positionally matched — the
    extra ones would either be dropped or shift every later one onto the wrong text."""
    src = extract_translatable(_motif())
    entry = build_translation_entry(extract_translatable(_translation()))
    entry["effects"] = ["một", "hai", "ba"]

    with pytest.raises(TranslationFileError, match="cannot be positionally matched"):
        parse_translation_entry(entry, src, where="vi/romance.json:x")


def test_build_parse_round_trips():
    payload = extract_translatable(_translation())
    entry = build_translation_entry(payload)
    back = parse_translation_entry(entry, extract_translatable(_motif()), where="t")
    assert back["name"] == payload["name"]
    assert {b["key"]: b["label"] for b in back["beats"]} == {
        b["key"]: b["label"] for b in payload["beats"]}


# ── resolution ─────────────────────────────────────────────────────────────
def test_asking_for_the_original_language_is_not_a_fallback():
    out = resolve_text(_motif(), None, "en")
    assert out["name"] == "Forced Proximity"
    assert out["text_language"] == "en"
    assert out["text_fallback"] is False


def test_no_translation_falls_back_to_source_and_announces_it():
    """The dogfood bug in one assertion. Falling back is fine; falling back SILENTLY is
    the defect — a caller handed English text after asking for Vietnamese must be able to
    tell."""
    out = resolve_text(_motif(), None, "vi")
    assert out["name"] == "Forced Proximity", "text must never be blank"
    assert out["text_language"] == "en"
    assert out["text_fallback"] is True
    # The fallback path is the one most likely to be written as a lazy passthrough, and a
    # passthrough of the EXTRACTED payload silently drops beat pacing. Assert structure
    # survives here too, not only on the translated path.
    assert out["beats"][0]["tension_target"] == 2 and out["beats"][0]["order"] == 1


def test_translation_replaces_text_and_leaves_structure_alone():
    out = resolve_text(_motif(), _translation(), "vi")
    assert out["name"] == "Kề Cận Bắt Buộc"
    assert out["text_language"] == "vi" and out["text_fallback"] is False
    trapped = next(b for b in out["beats"] if b["key"] == "trapped")
    assert trapped["label"] == "Bị nhốt chung"
    assert trapped["tension_target"] == 2 and trapped["order"] == 1, (
        "structure comes from the SOURCE row, always")


def test_a_partial_translation_falls_back_per_leaf_never_blanks_one():
    """A translation covering 1 of 2 beats must render the other in the original language.
    All-or-nothing would throw away good work; blanking would look like the motif has an
    empty beat."""
    tr = _translation(beats=[{"key": "trapped", "label": "Bị nhốt chung", "intent": "…"}])
    out = resolve_text(_motif(), tr, "vi")

    by_key = {b["key"]: b for b in out["beats"]}
    assert by_key["trapped"]["label"] == "Bị nhốt chung"
    assert by_key["thaw"]["label"] == "The argument stops", (
        "an uncovered beat keeps its source wording")
    assert len(out["beats"]) == 2


def test_beats_merge_by_key_not_by_position():
    """A translator reordering the beats must not shift wording onto the wrong beat."""
    tr = _translation(beats=[
        {"key": "thaw", "label": "Cuộc cãi vã ngừng lại", "intent": "b"},
        {"key": "trapped", "label": "Bị nhốt chung", "intent": "a"},
    ])
    out = resolve_text(_motif(), tr, "vi")
    by_key = {b["key"]: b["label"] for b in out["beats"]}
    assert by_key["trapped"] == "Bị nhốt chung" and by_key["thaw"] == "Cuộc cãi vã ngừng lại"


def test_stale_translation_is_served_but_flagged():
    """Right language with older wording beats correct wording in a language the reader
    cannot read — so a stale translation is still returned. It just says so, which is what
    lets a re-translate be scheduled instead of the drift going unnoticed."""
    out = resolve_text(_motif(), _translation(source_content_hash="made-from-older-text"), "vi")
    assert out["name"] == "Kề Cận Bắt Buộc", "stale text is still better than wrong-language text"
    assert out["text_stale"] is True


def test_a_fresh_translation_is_not_flagged_stale():
    fresh = _translation(source_content_hash=translatable_hash(extract_translatable(_motif())))
    out = resolve_text(_motif(), fresh, "vi")
    assert out["text_stale"] is False


# ── the flat wire shape (shared by the dev-time tool AND the runtime engine) ────
def test_flatten_unflatten_round_trips_a_real_entry():
    """Both translators hand the model a FLAT map and rebuild the entry from the reply.
    A round-trip that is not exact would move wording between leaves — the failure this
    whole module is about, arriving through the back door."""
    entry = build_translation_entry(extract_translatable(_motif()))
    assert unflatten_entry(flatten_entry(entry)) == entry


def test_flatten_keys_carry_the_beat_key_so_drift_is_detectable():
    """The flat keys ARE the join keys. That is what makes 'the model returned the same
    key set' double as 'nothing landed on the wrong beat'."""
    flat = flatten_entry(build_translation_entry(extract_translatable(_motif())))
    assert "beats.trapped.label" in flat
    assert "roles.lead.constraints[0]" in flat


def test_flatten_drops_empty_leaves():
    """An empty string has nothing to translate; carrying it would make a legitimately
    absent leaf look like a translation failure in every report that counts keys."""
    assert flatten_entry({"name": "x", "summary": "", "beats": {}}) == {"name": "x"}


# ── the echo predicate exists twice, by necessity ──────────────────────────────
def test_the_two_echo_predicates_are_calibrated_per_corpus():
    """`scripts/i18n_translate.py` cannot import from a service and a service cannot import
    from `scripts/`, so this predicate exists twice. They must NOT be identical — and that
    is the finding, not a compromise.

    The same rule was mis-generalised twice before it was split:
      1. a >=3-prose-word bar justified by COGNATES (`Status` is a German word) applied to
         non-Latin targets, where no cognate defence exists — hid ~200 verbatim English
         labels per script-bearing locale;
      2. a Title-Case exemption justified by PRODUCT NAMES (`LM Studio`, `API Key`,
         `Top-K`) applied to the narrative corpus, which has none — hid exactly the motif
         TITLES a translated library exists to show.

    So the calibration is per corpus, each measured on its own content:
      · UI strings   — Title-Case exempt, Latin bar 3   (309 → 66 false hits)
      · narrative    — no exemption,      Latin bar 2   (bar 1 flags 79, of which
                       `tension`/`suspense` really are French; bar 2 flags 2, both real)
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
    from i18n_translate import is_untranslated_echo as ui_echo

    # ── where they MUST agree: real prose, in both directions ──────────────
    for src, out, lang, expected in [
        ("Never allow this tool to run", "Never allow this tool to run", "de", True),
        ("a statement contradicts one small checkable thing",
         "a statement contradicts one small checkable thing", "de", True),
        ("Confirm cost", "Confirm cost", "ja", True),
        ("Quota left", "Quota left", "ru", True),
        ("Never allow this tool to run", "Diesem Werkzeug nie erlauben", "de", False),
        ("{{op}} {{status}}", "{{op}} {{status}}", "de", False),      # no prose at all
        ("https://example.com/docs", "https://example.com/docs", "de", False),
        ("{{n}}", "{{n}}", "ja", False),
        ("tension", "tension", "fr", False),          # a French word, single token
    ]:
        assert is_untranslated_echo(src, out, lang) is expected, ("narrative", src, lang)
        assert ui_echo(src, out, lang) is expected, ("ui", src, lang)

    # ── where they DELIBERATELY differ ─────────────────────────────────────
    # A pure Title-Case token string: a NAME in the UI corpus, a TITLE in the narrative one.
    for value in ("LM Studio", "The Witness Who Lies", "Beat Sheet"):
        assert ui_echo(value, value, "ja") is False, f"UI must keep the name {value!r}"
        assert is_untranslated_echo(value, value, "ja") is True,             f"a narrative title left verbatim is the defect: {value!r}"

    # The narrative Latin bar is 2, the UI bar is 3 — a two-word English compound sitting
    # in the hand-written Vietnamese is real (this pair was found by lowering it).
    assert is_untranslated_echo("grim-resolve", "grim-resolve", "vi") is True
    assert ui_echo("grim-resolve", "grim-resolve", "vi") is False


# ── the ARC-TEMPLATE spec (ARC-I18N) ───────────────────────────────────────────
def _arc(**over):
    row = {
        "code": "arc.three-year-pact",
        "original_language": "en",
        "name": "The Three-Year Pact",
        "summary": "two rivals bound to cooperate until a fixed date",
        "genre_tags": ["xianxia"],
        "chapter_span": 30,
        "threads": [{"key": "combat", "label": "Combat"},
                    {"key": "romance", "label": "Romance"}],
        "layout": [{"motif_code": "duel", "thread": "combat", "span_start": 1,
                    "span_end": 2, "ord": 0, "role_hints": {}, "triggers": []}],
        "arc_roster": [{"key": "rival", "actant": "opponent", "label": "the rival",
                        "constraints": ["must outrank the lead at the start"]}],
    }
    row.update(over)
    return row


def test_the_arc_spec_translates_text_and_refuses_structure():
    """`layout` is entirely machine values — motif_code, thread key, spans, ord — so it
    carries no translatable leaf and is absent from the spec BY DESIGN. A model asked to
    'localize' a layout would happily rename a thread key and silently break every
    placement's binding."""
    payload = extract_translatable(_arc(), ARC_TEMPLATE_SPEC)
    assert set(payload) == {"name", "summary", "threads", "arc_roster"}
    blob = json.dumps(payload, ensure_ascii=False)
    for structural in ("layout", "motif_code", "span_start", "chapter_span",
                       "xianxia", "opponent"):
        assert structural not in blob, f"{structural} must never reach a translator"


def test_an_arc_translation_merges_by_thread_key_not_position():
    """The join key is `key`. A translation that reorders threads — or a source that
    gains one — must not shift wording onto the wrong thread, which is silent at runtime
    (the merge just misses) and therefore has to be structural."""
    tr = {"language_code": "vi", "name": "Giao Ước Ba Năm", "summary": "",
          "threads": [{"key": "romance", "label": "Tình cảm"}], "arc_roster": []}
    out = resolve_text(_arc(), tr, "vi", spec=ARC_TEMPLATE_SPEC)
    by_key = {t["key"]: t["label"] for t in out["threads"]}
    assert by_key["romance"] == "Tình cảm"
    assert by_key["combat"] == "Combat", "an uncovered thread keeps its source wording"
    assert out["name"] == "Giao Ước Ba Năm"
    assert out["text_language"] == "vi" and out["text_fallback"] is False


def test_an_arc_with_no_translation_reads_original_and_says_so():
    out = resolve_text(_arc(), None, "vi", spec=ARC_TEMPLATE_SPEC)
    assert out["name"] == "The Three-Year Pact"
    assert out["text_language"] == "en" and out["text_fallback"] is True


def test_the_two_specs_do_not_share_mutable_state():
    """They are separate frozen specs, not one dict two names — a stray mutation through
    either would silently redefine what is translatable for the other."""
    assert MOTIF_SPEC.lists is not ARC_TEMPLATE_SPEC.lists
    assert "beats" in MOTIF_SPEC.lists and "beats" not in ARC_TEMPLATE_SPEC.lists
    assert "threads" in ARC_TEMPLATE_SPEC.lists and "threads" not in MOTIF_SPEC.lists
