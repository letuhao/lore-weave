"""Unit tests for the pure settings resolution cascade (spec §3).

The cascade is the heart of the Chat & AI unify feature — these pin the
edge-case decisions from the adversarial review (EC-1 liveness-per-tier, EC-3
shared-book slot, partial field inheritance, deep-merge null-clears)."""
from __future__ import annotations

import pytest

from app.services import settings_resolution as sr


# ── apply_patch (deep field-merge, null = clear) ─────────────────────────────
def test_apply_patch_sets_and_merges_nested():
    cur = {"chat": {"tts_model_ref": "m1", "tts_voice_id": "af_heart"}}
    patch = {"chat": {"tts_voice_id": "bella"}}
    out = sr.apply_patch(cur, patch)
    # sibling leaf preserved, only the patched leaf changes
    assert out["chat"] == {"tts_model_ref": "m1", "tts_voice_id": "bella"}
    assert cur["chat"]["tts_voice_id"] == "af_heart"  # input not mutated


def test_apply_patch_null_leaf_clears_key():
    cur = {"temperature": 0.7, "top_p": 1.0}
    out = sr.apply_patch(cur, {"temperature": None})
    assert out == {"top_p": 1.0}  # cleared → will inherit down


def test_apply_patch_absent_key_untouched():
    cur = {"a": 1, "b": 2}
    assert sr.apply_patch(cur, {"a": 9}) == {"a": 9, "b": 2}


# ── resolve_category (per-field, most-specific wins, partial inherit) ─────────
def test_resolve_category_partial_inheritance_per_field():
    # book overrides only temperature; account's top_p must survive (EC-3 / RES-3)
    tiers = [
        (sr.TIER_SESSION, {}),
        (sr.TIER_BOOK, {"temperature": 0.9}),
        (sr.TIER_ACCOUNT, {"temperature": 0.5, "top_p": 0.8}),
    ]
    out = sr.resolve_category(tiers, defaults={"reasoning_effort": "off"})
    assert out["temperature"]["effective_value"] == 0.9
    assert out["temperature"]["source_tier"] == sr.TIER_BOOK
    assert out["top_p"]["effective_value"] == 0.8
    assert out["top_p"]["source_tier"] == sr.TIER_ACCOUNT
    # a field only in System defaults resolves to system
    assert out["reasoning_effort"]["source_tier"] == sr.TIER_SYSTEM


def test_resolve_category_tier_stack_records_all_present_tiers():
    tiers = [(sr.TIER_SESSION, {"x": 1}), (sr.TIER_ACCOUNT, {"x": 2})]
    out = sr.resolve_category(tiers)
    assert out["x"]["tier_stack"] == {sr.TIER_SESSION: 1, sr.TIER_ACCOUNT: 2}
    assert out["x"]["effective_value"] == 1  # session wins


# ── resolve_model_role (liveness per tier) ───────────────────────────────────
def _live_all(_ref):
    return True


def test_model_role_session_wins_when_live():
    out = sr.resolve_model_role(
        sr.ModelRole.CHAT,
        session_ref=("user_model", "s"), book_ref=("user_model", "b"),
        account_refs={"chat": ("user_model", "a")}, is_live=_live_all,
    )
    assert out["effective_value"] == {"model_source": "user_model", "model_ref": "s"}
    assert out["source_tier"] == sr.TIER_SESSION


def test_model_role_skips_dead_middle_tier_and_names_it():
    # EC-1: session ref is dead → skip it (recorded), fall to a live account tier
    dead = ("user_model", "s")
    out = sr.resolve_model_role(
        sr.ModelRole.CHAT,
        session_ref=dead, book_ref=None,
        account_refs={"chat": ("user_model", "a")},
        is_live=lambda ref: ref != dead,
    )
    assert out["effective_value"]["model_ref"] == "a"
    assert out["source_tier"] == sr.TIER_ACCOUNT
    assert sr.TIER_SESSION in out["skipped"]


def test_model_role_all_dead_is_no_model_configured():
    out = sr.resolve_model_role(
        sr.ModelRole.CHAT,
        session_ref=("user_model", "s"), book_ref=None,
        account_refs={"chat": ("user_model", "a")},
        is_live=lambda ref: False,
    )
    assert out["effective_value"] is None
    assert out["source_tier"] == sr.TIER_NONE


def test_model_role_book_unavailable_surfaces_not_silent_drop():
    # EC / TEN-6: composition unreachable → do NOT silently fall to account
    out = sr.resolve_model_role(
        sr.ModelRole.CHAT,
        session_ref=None, book_ref=None,
        account_refs={"chat": ("user_model", "a")},
        is_live=_live_all, book_unavailable=True,
    )
    # a live account still resolves, but if account were absent we'd see unavailable
    assert out["source_tier"] == sr.TIER_ACCOUNT
    out2 = sr.resolve_model_role(
        sr.ModelRole.CHAT,
        session_ref=None, book_ref=None, account_refs={}, is_live=_live_all,
        book_unavailable=True,
    )
    assert out2["source_tier"] == sr.TIER_UNAVAILABLE


def test_composer_falls_back_to_chat_capability_account_default():
    # §3.4 — composer has no own account key → inherits the chat capability default
    out = sr.resolve_model_role(
        sr.ModelRole.COMPOSER,
        session_ref=None, book_ref=None,
        account_refs={"chat": ("user_model", "chatdefault")},
        is_live=_live_all,
    )
    assert out["effective_value"]["model_ref"] == "chatdefault"
    assert out["source_tier"] == sr.TIER_ACCOUNT


def test_account_capability_order():
    assert sr.account_capability_for(sr.ModelRole.CHAT) == ["chat"]
    assert sr.account_capability_for(sr.ModelRole.COMPOSER) == ["composer", "chat"]
    assert sr.account_capability_for(sr.ModelRole.EMBEDDING) == ["embedding"]


def test_collect_candidate_refs_dedupes():
    refs = sr.collect_candidate_refs(
        session_refs={"chat": ("user_model", "x")},
        book_refs={"chat": ("user_model", "x")},  # dup
        account_refs={"chat": ("user_model", "y")},
    )
    assert refs == {("user_model", "x"), ("user_model", "y")}


# ── the shared closed-set registry (spec §8.1) ───────────────────────────────
#
# The enum registry used to live INSIDE the account router. The session row is a
# SECOND write door onto the same settings — so a registry only one door can see
# cannot defend the other. These tests pin the registry as shared, and that both
# doors reach for it rather than re-declaring their own copy (the drift class that
# lets a bad `context.mode` land and be read as 'auto' by every consumer).

def test_validate_setting_enums_rejects_out_of_set_values():
    with pytest.raises(ValueError, match="context.mode"):
        sr.validate_setting_enums("context", {"mode": "sometimes"})
    with pytest.raises(ValueError, match="behavior.permission_mode"):
        sr.validate_setting_enums("behavior", {"permission_mode": "root"})
    with pytest.raises(ValueError, match="behavior.reasoning_effort"):
        sr.validate_setting_enums("behavior", {"reasoning_effort": "extreme"})


def test_validate_setting_enums_names_the_allowed_set():
    """IN-6 self-correcting error: the message must say what IS allowed, so the
    caller (often an LLM) can fix itself without a second round-trip."""
    with pytest.raises(ValueError) as exc:
        sr.validate_setting_enums("context", {"mode": "nope"})
    msg = str(exc.value)
    assert "'auto'" in msg and "'on'" in msg and "'off'" in msg
    assert "'nope'" in msg


def test_validate_setting_enums_allows_none_absent_and_unknown_keys():
    sr.validate_setting_enums("context", {"mode": None})       # null = clear to inherit
    sr.validate_setting_enums("context", {})                    # absent = untouched
    sr.validate_setting_enums("context", None)                  # whole category cleared
    sr.validate_setting_enums("context", {"trigger_ratio": 0.8})  # not an enum key
    sr.validate_setting_enums("voice", {"anything": "goes"})     # category has no enums


def test_both_write_doors_use_the_one_registry():
    """A private copy in either router is the drift this consolidation removes."""
    from app.routers import ai_settings

    assert not hasattr(ai_settings, "_ENUMS"), "the account router must not re-declare the enums"
    assert set(sr.SETTING_ENUMS) == {"behavior", "context"}
    assert sr.SETTING_ENUMS["context"]["mode"] == {"auto", "on", "off"}
    assert sr.SETTING_ENUMS["behavior"]["permission_mode"] == {"ask", "write", "plan"}
    assert sr.SETTING_ENUMS["behavior"]["reasoning_effort"] == {"off", "low", "medium", "high"}


# ── D-CHATAI-VOICE-TWO-STORES — voice source vocab reconcile (WS-4.0) ────────
# Voice sources nest in the `voice` blob, so they can't live in the flat SETTING_ENUMS;
# they get their own `normalize_voice_sources` (coerce legacy 'ai_model' → canonical
# 'user_model', reject an unknown value). This was formerly the deliberately-unvalidated
# hole; the reconcile closes it with one canonical vocabulary.
def test_voice_stays_out_of_flat_registry_but_has_its_own_validator():
    assert "voice" not in sr.SETTING_ENUMS  # flat check can't reach nested paths
    assert sr.VOICE_SOURCE_ALLOWED == {"browser", "user_model"}


def test_normalize_coerces_legacy_ai_model_on_all_surfaces():
    v = sr.normalize_voice_sources({
        "chat": {"tts_source": "ai_model", "tts_model_ref": "m1"},
        "reading": {"tts_source": "ai_model"},
        "stt": {"source": "ai_model", "model_ref": "s1"},
    })
    assert v["chat"]["tts_source"] == "user_model"
    assert v["reading"]["tts_source"] == "user_model"
    assert v["stt"]["source"] == "user_model"
    assert v["chat"]["tts_model_ref"] == "m1"  # sibling fields untouched


def test_normalize_accepts_canonical_and_browser():
    v = sr.normalize_voice_sources({"chat": {"tts_source": "user_model"}, "stt": {"source": "browser"}})
    assert v["chat"]["tts_source"] == "user_model"
    assert v["stt"]["source"] == "browser"


def test_normalize_rejects_unknown_source():
    with pytest.raises(ValueError, match="voice.chat.tts_source"):
        sr.normalize_voice_sources({"chat": {"tts_source": "wat"}})


def test_normalize_is_noop_on_absent_or_none():
    assert sr.normalize_voice_sources(None) is None
    assert sr.normalize_voice_sources({}) == {}
    # a patch that doesn't touch source fields passes through untouched
    assert sr.normalize_voice_sources({"chat": {"tts_voice_id": "nova"}}) == {"chat": {"tts_voice_id": "nova"}}


def test_normalize_does_not_mutate_input():
    src = {"chat": {"tts_source": "ai_model"}}
    sr.normalize_voice_sources(src)
    assert src["chat"]["tts_source"] == "ai_model"  # caller's dict untouched


# ── WS-4.3 — per-user audio retention bounded by the deploy ceiling ──────────
def test_audio_retention_accepts_in_range_and_zero():
    sr.validate_audio_retention({"audio_retention_hours": 24}, 48)  # ok
    sr.validate_audio_retention({"audio_retention_hours": 0}, 48)   # 0 = don't retain
    sr.validate_audio_retention({"audio_retention_hours": 48}, 48)  # exactly the ceiling
    sr.validate_audio_retention({}, 48)                             # absent = inherit
    sr.validate_audio_retention({"audio_retention_hours": None}, 48)  # clear = inherit


def test_audio_retention_rejects_over_ceiling():
    with pytest.raises(ValueError, match=r"\[0, 48\]"):
        sr.validate_audio_retention({"audio_retention_hours": 72}, 48)


def test_audio_retention_rejects_negative_and_non_int():
    with pytest.raises(ValueError):
        sr.validate_audio_retention({"audio_retention_hours": -1}, 48)
    with pytest.raises(ValueError):
        sr.validate_audio_retention({"audio_retention_hours": "24"}, 48)
    with pytest.raises(ValueError):
        sr.validate_audio_retention({"audio_retention_hours": True}, 48)  # bool is not a valid count
