"""Unit tests for the binary motif-conformance judge (W5, §6.1 + §7 audit guards).

ADVISORY-only: conformance is a flag + signal, never a hard gate (§14.6). These
tests pin the load-bearing contracts the parallel design surfaced:
  - normalize: a missing/malformed flag is None ("unjudged"), NOT defaulted true.
  - CC4 degrade: any LLM/timeout/parse failure → a degraded dim, never raises.
  - merge_conformance: read-modify-write that PRESERVES coherence/violations (the
    generation_job.critic COALESCE-clobber guard — 00-RECONCILE §2). LOAD-BEARING.
  - tension-band derivation (node tension primary, beat tension_target×20 fallback).
  - the §16.1 structure-vs-style boundary baked into the prompt.
  - §7 audit risk-guards: calibrated defaults false, sampling skips low-tension,
    high-tension always judged, unbound scene not judged, beat_realized never gates.
"""

from __future__ import annotations

import json
import random
from types import SimpleNamespace

from loreweave_llm.errors import LLMError

from app.engine import motif_conformance as mc
from app.packer.profile import NEUTRAL, BookProfile


# ── normalize_conformance (defensive shaping) ──────────────────────────────

def test_normalize_conformance_well_formed():
    out = mc.normalize_conformance(
        {"beat_realized": True, "tension_band_match": False, "reason": "hit the bait"}
    )
    assert out["beat_realized"] is True
    assert out["tension_band_match"] is False
    assert out["reason"] == "hit the bait"


def test_normalize_conformance_missing_flag_is_none():
    # The "unjudged != pass" rule: an absent flag is None, NOT defaulted true.
    out = mc.normalize_conformance({"beat_realized": True})
    assert out["beat_realized"] is True
    assert out["tension_band_match"] is None


def test_normalize_conformance_string_bools():
    out = mc.normalize_conformance(
        {"beat_realized": "true", "tension_band_match": "FALSE", "reason": "x"}
    )
    assert out["beat_realized"] is True
    assert out["tension_band_match"] is False
    # garbage coerces to None, never a guess
    assert mc.normalize_conformance({"beat_realized": "maybe"})["beat_realized"] is None
    # a stray int is NOT a bool (bool-is-int trap) → None
    assert mc.normalize_conformance({"beat_realized": 1})["beat_realized"] is None


def test_normalize_conformance_malformed_json():
    # parse_critique_json returns None on garbage → _EMPTY-shaped dim, no raise.
    out = mc.normalize_conformance(None)
    assert out["beat_realized"] is None
    assert out["tension_band_match"] is None
    assert out["reason"] == ""


def test_normalize_conformance_caps_reason():
    out = mc.normalize_conformance({"reason": "z" * 500})
    assert len(out["reason"]) <= 200


# ── judge_motif_conformance (degrade-safe, CC4) ────────────────────────────

class FakeJudge:
    def __init__(self, *, content=None, status="completed", raises=False):
        self._content = content
        self._status = status
        self._raises = raises
        self.calls = []

    async def submit_and_wait(self, **kw):
        self.calls.append(kw)
        if self._raises:
            raise LLMError("gateway down")
        result = (
            {"messages": [{"role": "assistant", "content": self._content}]}
            if self._content else {}
        )
        return SimpleNamespace(status=self._status, result=result)


async def _judge(judge, *, passage="a confrontation happens", lang=NEUTRAL):
    return await mc.judge_motif_conformance(
        judge, user_id="u", model_source="user_model", model_ref="m",
        beat_intent="hero confronts the schemer", beat_key="confrontation",
        motif_name="cultivation.fortuitous_encounter", tension_band=(60, 80),
        expected_roles=["schemer", "hero"], passage=passage, profile=lang,
    )


async def test_judge_happy_returns_both_flags():
    content = json.dumps(
        {"beat_realized": True, "tension_band_match": True, "reason": "confronts"}
    )
    judge = FakeJudge(content=content)
    out = await _judge(judge)
    assert out["beat_realized"] is True and out["tension_band_match"] is True
    # ran with the distinct critic ref via the chat operation, thinking disabled
    assert judge.calls[0]["model_ref"] == "m" and judge.calls[0]["operation"] == "chat"
    assert judge.calls[0]["input"]["reasoning_effort"] == "none"
    assert judge.calls[0]["input"]["temperature"] == 0.0


async def test_judge_degrades_on_llm_error():
    judge = FakeJudge(raises=True)
    out = await _judge(judge)
    assert out["error"] == "conformance_unavailable"
    assert out["beat_realized"] is None and out["tension_band_match"] is None


async def test_judge_degrades_on_noncompleted_job():
    judge = FakeJudge(content="{}", status="failed")
    out = await _judge(judge)
    assert out["error"] == "conformance_failed"


async def test_judge_empty_passage_short_circuits():
    judge = FakeJudge(content="{}")
    out = await _judge(judge, passage="   ")
    assert out["error"] == "conformance_no_passage"
    assert judge.calls == []  # never called the LLM


async def test_judge_malformed_json_degrades_not_crash():
    judge = FakeJudge(content="the model rambled without JSON")
    out = await _judge(judge)
    assert out["beat_realized"] is None and out["tension_band_match"] is None


# ── merge_conformance (THE COALESCE-clobber guard, load-bearing) ───────────

def test_merge_conformance_preserves_existing_dims():
    existing = {
        "coherence": 4, "voice_match": 3, "pacing": 5, "canon_consistency": 5,
        "violations": [{"rule_id": "r1", "violated": True, "span": "s", "why": "w"}],
    }
    dim = {"beat_realized": True, "tension_band_match": False, "calibrated": False}
    merged = mc.merge_conformance(existing, dim)
    # the new key is added
    assert merged["motif_conformance"] == dim
    # AND every pre-existing dim survives (a bare {motif_conformance:…} UPDATE
    # would destroy these via COALESCE whole-column replace)
    assert merged["coherence"] == 4
    assert merged["violations"][0]["rule_id"] == "r1"
    # the source dict is not mutated (read-modify-write returns a new dict)
    assert "motif_conformance" not in existing


def test_merge_conformance_none_critic():
    merged = mc.merge_conformance(None, {"beat_realized": True})
    assert merged == {"motif_conformance": {"beat_realized": True}}


def test_build_conformance_dim_stamps_provenance():
    judge_out = {"beat_realized": True, "tension_band_match": False, "reason": "x"}
    dim = mc.build_conformance_dim(
        judge_out, motif_id="0192aaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        beat_key="bait", band=(60, 80), calibrated=False,
    )
    assert dim["motif_id"] == "0192aaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert dim["beat_key"] == "bait"
    assert dim["planned_tension_band"] == [60, 80]
    assert dim["calibrated"] is False
    # the judge output is carried through
    assert dim["beat_realized"] is True and dim["reason"] == "x"


def test_build_conformance_dim_null_motif():
    dim = mc.build_conformance_dim(
        {"beat_realized": None}, motif_id=None, beat_key=None,
        band=(0, 100), calibrated=True,
    )
    assert dim["motif_id"] is None and dim["beat_key"] is None
    assert dim["calibrated"] is True


# ── tension-band derivation ────────────────────────────────────────────────

def test_tension_band_from_node_tension():
    # node tension present → band centred on it, clamped to [0,100]
    assert mc.derive_tension_band(node_tension=72, beat_tension_target=None, halfwidth=15) == (57, 87)
    # clamp at the top
    assert mc.derive_tension_band(node_tension=95, beat_tension_target=None, halfwidth=15) == (80, 100)
    # clamp at the bottom
    assert mc.derive_tension_band(node_tension=5, beat_tension_target=None, halfwidth=15) == (0, 20)


def test_tension_band_falls_back_to_beat_target():
    # no node tension → lift the 1-5 beat target to 0-100 (×20)
    assert mc.derive_tension_band(node_tension=None, beat_tension_target=4, halfwidth=15) == (65, 95)
    # neither present → the widest band (no false flag)
    assert mc.derive_tension_band(node_tension=None, beat_tension_target=None, halfwidth=15) == (0, 100)


# ── de-bias + structure-vs-style prompt boundary (§16.1) ──────────────────

def test_prompt_carries_source_language_no_english_default():
    sys_zh, _ = mc.build_conformance_prompt(
        beat_intent="i", beat_key="b", motif_name="m", tension_band=(60, 80),
        expected_roles=["x"], passage="p", profile=BookProfile(source_language="zh"),
    )
    assert "'zh'" in sys_zh
    sys_auto, _ = mc.build_conformance_prompt(
        beat_intent="i", beat_key="b", motif_name="m", tension_band=(60, 80),
        expected_roles=["x"], passage="p", profile=NEUTRAL,
    )
    assert "language with code" not in sys_auto


def test_prompt_separates_structure_from_style():
    # the §16.1 boundary: the judge must NOT reward/penalise prose style/length/voice.
    sys_p, _ = mc.build_conformance_prompt(
        beat_intent="i", beat_key="b", motif_name="m", tension_band=(60, 80),
        expected_roles=[], passage="p", profile=NEUTRAL,
    )
    low = sys_p.lower()
    assert "style" in low and "length" in low
    assert "structure" in low  # it announces it is a structural judge


# ── §7 audit risk-guards ───────────────────────────────────────────────────

# F-3 — the dim is NEVER silently presented as trusted.
def test_dim_calibrated_flag_defaults_false():
    # build_conformance_dim with calibrated=False (the producer default until the
    # harness passes) stamps calibrated=False — the honest-labeling mechanism.
    dim = mc.build_conformance_dim(
        {"beat_realized": True}, motif_id=None, beat_key=None,
        band=(0, 100), calibrated=False,
    )
    assert dim["calibrated"] is False


# gap4 — sampling is NOT every-scene (cost-bounded).
def test_sampling_always_judges_high_tension():
    # a HIGH_WEIGHT_BEATS beat is always judged regardless of rng/tension
    rng = random.Random(0)
    assert mc.should_judge_conformance(
        beat_role="climax", tension=10, has_motif=True, rng=rng, sample_pct=0,
    ) is True


def test_sampling_always_judges_high_tension_by_threshold():
    rng = random.Random(0)
    # tension >= the high gate (70) → always judged even on a non-weight beat
    assert mc.should_judge_conformance(
        beat_role="filler", tension=80, has_motif=True, rng=rng,
        sample_pct=0, high_threshold=70,
    ) is True


def test_sampling_skips_low_tension_unsampled():
    # a low-tension non-high-weight beat with the rng above the pct is NOT judged.
    class _Rng:
        def random(self):  # always returns 0.99 → above any pct < 99
            return 0.99
    assert mc.should_judge_conformance(
        beat_role="filler", tension=10, has_motif=True, rng=_Rng(), sample_pct=20,
    ) is False


def test_sampling_includes_low_tension_when_sampled():
    class _Rng:
        def random(self):
            return 0.05  # below 20% → sampled in
    assert mc.should_judge_conformance(
        beat_role="filler", tension=10, has_motif=True, rng=_Rng(), sample_pct=20,
    ) is True


def test_unbound_scene_not_judged():
    # no motif bound → nothing to conform to → never judged (gap4 / §5.2)
    rng = random.Random(0)
    assert mc.should_judge_conformance(
        beat_role="climax", tension=99, has_motif=False, rng=rng, sample_pct=100,
    ) is False


# ── the pure trace assemble (§4, the join-correctness surface) ─────────────

import uuid as _uuid  # noqa: E402

from app.db.models import MotifApplication, OutlineNode  # noqa: E402
from app.routers import conformance as conf  # noqa: E402


def _scene(node_id, *, title="S", beat_role="bait", tension=72, chapter_id=None):
    return OutlineNode(
        id=node_id, created_by=_uuid.uuid4(), project_id=_uuid.uuid4(),
        book_id=_uuid.uuid4(), kind="scene",
        rank="aaa", title=title, beat_role=beat_role, status="done",
        chapter_id=chapter_id or _uuid.uuid4(), tension=tension,
    )


def _app(node_id, *, motif_id, beat_key="bait", role_bindings=None):
    return MotifApplication(
        id=_uuid.uuid4(), created_by=_uuid.uuid4(), project_id=_uuid.uuid4(),
        book_id=_uuid.uuid4(), motif_id=motif_id, motif_version=1,
        outline_node_id=node_id, role_bindings=role_bindings or {"schemer": "ent-1"},
        annotations={"beat_key": beat_key} if beat_key else {},
    )


def test_assemble_planned_realized_conformance():
    n1 = _uuid.uuid4()
    chapter_id = _uuid.uuid4()
    m_id = _uuid.uuid4()
    scenes = [_scene(n1, chapter_id=chapter_id)]
    apps = {n1: _app(n1, motif_id=m_id, beat_key="bait")}
    latest = {n1: {
        "job_id": "job-1", "has_text": True,
        "critic": {"coherence": 4, "motif_conformance": {
            "beat_realized": True, "tension_band_match": False,
            "calibrated": False, "reason": "ok", "error": None,
        }},
    }}
    out = conf._assemble_conformance(
        chapter_id=chapter_id, calibrated=False, scenes=scenes,
        apps_by_node=apps, latest_by_node=latest,
    )
    assert out["scope"] == "chapter"
    assert out["calibrated"] is False
    s = out["scenes"][0]
    # AI-quality R3 — the trace returns the regenerate inputs (node + motif + beat).
    assert s["outline_node_id"] == str(n1)
    assert s["planned"]["motif_id"] == str(m_id)
    assert s["planned"]["beat_key"] == "bait"
    assert s["realized"]["has_prose"] is True
    assert s["conformance"]["beat_realized"] is True
    assert s["conformance"]["tension_band_match"] is False


def test_assemble_unbound_scene_has_null_conformance():
    # a scene with no motif_application → planned motif null + conformance null
    n1 = _uuid.uuid4()
    chapter_id = _uuid.uuid4()
    scenes = [_scene(n1, chapter_id=chapter_id)]
    out = conf._assemble_conformance(
        chapter_id=chapter_id, calibrated=False, scenes=scenes,
        apps_by_node={}, latest_by_node={},
    )
    s = out["scenes"][0]
    assert s["planned"]["motif_id"] is None
    assert s["conformance"] is None
    assert s["realized"]["has_prose"] is False


def test_assemble_bound_but_no_conformance_dim_yet():
    # bound + a completed job, but the critic has no motif_conformance dim yet
    n1 = _uuid.uuid4()
    chapter_id = _uuid.uuid4()
    m_id = _uuid.uuid4()
    scenes = [_scene(n1, chapter_id=chapter_id)]
    apps = {n1: _app(n1, motif_id=m_id)}
    latest = {n1: {"job_id": "j", "has_text": True, "critic": {"coherence": 5}}}
    out = conf._assemble_conformance(
        chapter_id=chapter_id, calibrated=False, scenes=scenes,
        apps_by_node=apps, latest_by_node=latest,
    )
    s = out["scenes"][0]
    assert s["planned"]["motif_id"] == str(m_id)
    assert s["conformance"] is None  # job exists but no dim → null, not fabricated


def test_assemble_beat_key_falls_back_to_null():
    # binder didn't write beat_key into annotations → degrade to motif-level (null)
    n1 = _uuid.uuid4()
    chapter_id = _uuid.uuid4()
    m_id = _uuid.uuid4()
    scenes = [_scene(n1, chapter_id=chapter_id)]
    apps = {n1: _app(n1, motif_id=m_id, beat_key=None)}
    out = conf._assemble_conformance(
        chapter_id=chapter_id, calibrated=False, scenes=scenes,
        apps_by_node=apps, latest_by_node={},
    )
    assert out["scenes"][0]["planned"]["beat_key"] is None
