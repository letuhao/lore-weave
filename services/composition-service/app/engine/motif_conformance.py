"""Binary motif-conformance judge (W5 / §14 / §R2.1) — ADVISORY, never a hard gate.

Given a scene's PLANNED beat (the bound motif beat + its tension band + the roles
that should be present) and the REALIZED prose, emit two BINARY verdicts:
  beat_realized      — did the prose actually enact the planned beat's intent?
  tension_band_match — did the scene's dramatic tension land in the planned band?

This is a STRUCTURAL judge (§16.1): it checks WHAT happened, never HOW it reads
(coherence/voice/pacing are judge_prose's job). A short, terse render that still
hits the beat is `beat_realized=true` — do NOT penalise compression.

Binary by design (§R2.1): two y/n flags plug into the EXISTING binary
`calibrate_judge` (cohen_kappa>=0.4 / balanced_acc>=0.75). A graded score would
need ordinal calibration (QWK) we don't have — that's plot_density, P1.5.

De-bias (critic.py §2.6 lesson): judge in the book's source_language; abstract
phrasing, NO English-only illustrative examples (they bias a CJK/VN judge).

CC4 (critic.py): any LLM/timeout/parse failure degrades to an empty advisory
verdict with an `error` marker — NEVER raises (advisory must not block a generate
or a critique). The judge being down must never gate.

`calibrated` is NOT produced here — the PRODUCER (the critique branch) stamps it
from `motif_conformance_calibrated` (config), which flips true only after the
calibration harness passes. Until then it ships `false` → the FE labels the dim
"unverified self-report" (§5). This honest-labeling is structural, not a prompt.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Protocol

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.engine.adaptive_k import HIGH_WEIGHT_BEATS
from app.engine.critic import parse_critique_json  # REUSE the tolerant fence-stripping parser
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

# The degrade sentinel — the judge-output shape on any failure (the caller folds
# in calibrated/motif_id/beat_key/band provenance via build_conformance_dim).
_EMPTY: dict[str, Any] = {"beat_realized": None, "tension_band_match": None, "reason": ""}


class _JudgeLLMClient(Protocol):
    """Structural type the real LLMClient satisfies (and the test FakeJudge)."""

    async def submit_and_wait(self, **kwargs: Any) -> Any: ...


# ── prompt ──────────────────────────────────────────────────────────────────

def build_conformance_prompt(
    *,
    beat_intent: str,
    beat_key: str,
    motif_name: str,
    tension_band: tuple[int, int],
    expected_roles: list[str],
    passage: str,
    profile: BookProfile,
) -> tuple[str, str]:
    """Build (system, user) for the binary conformance judge.

    `tension_band` is the [lo, hi] on the 0-100 scale the planner placed (see
    derive_tension_band); `expected_roles` are the role labels the binding
    requires present. Mirrors critic.build_critique_prompt: abstract,
    multilingual-safe, JSON-only, structure-not-style.
    """
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the `reason` value in the language with code '{profile.source_language}'."
    )
    system = (
        "You are a narrative-structure conformance judge. You are given a PLANNED "
        "story beat (its intent, the role-players that should appear, and a target "
        "dramatic-tension band on a 0-100 scale) and the REALIZED prose written for "
        "it. Decide TWO things, each strictly true or false:\n"
        "  beat_realized: does the prose actually ENACT the planned beat's intent "
        "(the planned thing happens, the named roles act in it)? Judge the EVENT, "
        "not the writing quality. A short or terse passage that still makes the "
        "beat happen is true. A passage that drifts to a DIFFERENT beat (e.g. "
        "planned a confrontation, wrote a rest) is false.\n"
        "  tension_band_match: does the scene's dramatic tension fall within the "
        "planned band? A climactic beat written as calm low-stakes prose is false.\n"
        "Judge by MEANING in the text's own language and script. This is a "
        "STRUCTURAL judgement: do NOT reward or penalise prose style, length, "
        "voice, or pacing — only whether the planned STRUCTURE was realized. "
        "Return ONLY a JSON object: "
        '{"beat_realized": <true|false>, "tension_band_match": <true|false>, '
        '"reason": "<=20 words"}.'
        + lang
    )
    roles_block = ", ".join(r for r in expected_roles if r) or "(none specified)"
    user = (
        f"PLANNED BEAT: {motif_name} / {beat_key}\n"
        f"BEAT INTENT: {beat_intent}\n"
        f"ROLES THAT SHOULD APPEAR: {roles_block}\n"
        f"PLANNED TENSION BAND (0-100): {tension_band[0]}-{tension_band[1]}\n\n"
        f"REALIZED PROSE:\n{passage}"
    )
    return system, user


# ── normalize (defensive parse) ──────────────────────────────────────────────

def _flag(value: Any) -> bool | None:
    """Coerce a judge flag to bool; a missing/garbage value → None (unjudged,
    NOT defaulted true). bool-is-int trap excluded (a stray 1 is NOT True)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def normalize_conformance(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Shape a parsed judge response into the judge-output contract. Missing/
    malformed flags → None; reason coerced to a capped str. Defensive like
    critic.normalize_critique — one bad field never poisons the dim."""
    parsed = parsed or {}
    return {
        "beat_realized": _flag(parsed.get("beat_realized")),
        "tension_band_match": _flag(parsed.get("tension_band_match")),
        "reason": str(parsed.get("reason", ""))[:200],
    }


# ── the judge ────────────────────────────────────────────────────────────────

async def judge_motif_conformance(
    judge: _JudgeLLMClient,
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
    beat_intent: str,
    beat_key: str,
    motif_name: str,
    tension_band: tuple[int, int],
    expected_roles: list[str],
    passage: str,
    profile: BookProfile,
    max_tokens: int = 512,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run the binary conformance judge. Returns the judge-output dict (WITHOUT
    the calibrated/motif_id/beat_key/band provenance — the CALLER folds those in
    via build_conformance_dim). CC4: any failure degrades to _EMPTY + error,
    never raises (advisory must not block)."""
    if not passage.strip():
        return {**_EMPTY, "error": "conformance_no_passage"}
    system, user = build_conformance_prompt(
        beat_intent=beat_intent, beat_key=beat_key, motif_name=motif_name,
        tension_band=tension_band, expected_roles=expected_roles,
        passage=passage, profile=profile,
    )
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "text"},
                "temperature": 0.0,
                "max_tokens": max_tokens,
                # The judge emits tiny JSON — reasoning tokens are pure budget burn.
                # reasoning_effort is the knob that actually works for LM Studio +
                # Qwen3; chat_template_kwargs covers models honouring the template.
                "reasoning_effort": "none",
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            job_meta={"extractor": "motif_conformance"},
            trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("motif_conformance degraded (LLM error): %s", exc)
        return {**_EMPTY, "error": "conformance_unavailable"}
    if job.status != "completed":
        logger.info("motif_conformance job status=%s → degraded", job.status)
        return {**_EMPTY, "error": f"conformance_{job.status}"}
    content = extract_judge_content(job.result)
    return normalize_conformance(parse_critique_json(content))


# ── provenance + the COALESCE-clobber-safe merge ────────────────────────────

def build_conformance_dim(
    judge_out: dict[str, Any],
    *,
    motif_id: Any,
    beat_key: str | None,
    band: tuple[int, int],
    calibrated: bool,
) -> dict[str, Any]:
    """Fold provenance + the calibration flag into the judge output → the dim
    contract (§1.2). `calibrated` is stamped by the producer from config; until
    the harness passes it is False (the FE renders "unverified self-report")."""
    return {
        **judge_out,
        "motif_id": str(motif_id) if motif_id else None,
        "beat_key": beat_key,
        "planned_tension_band": list(band),
        "calibrated": bool(calibrated),
    }


def merge_conformance(critic: dict[str, Any] | None, dim: dict[str, Any]) -> dict[str, Any]:
    """Read-modify-write: add `motif_conformance` WITHOUT clobbering existing dims.

    LOAD-BEARING (00-RECONCILE §2): generation_jobs.update_status does
    `critic = COALESCE($5::jsonb, critic)` — a whole-column replace on a non-null
    write. So a bare `update_status(critic={"motif_conformance": …})` would DESTROY
    `coherence`/`voice_match`/`pacing`/`violations`. We merge into the full dict
    here (the dismiss_violation pattern) and return a NEW dict (no mutation of the
    caller's critic)."""
    out = dict(critic or {})
    out["motif_conformance"] = dim
    return out


# ── tension-band derivation (the one non-obvious input, §2.2) ───────────────

def derive_tension_band(
    *,
    node_tension: int | None,
    beat_tension_target: int | None,
    halfwidth: int,
) -> tuple[int, int]:
    """The [lo, hi] band on the 0-100 scale (outline_node.tension's scale — NOT
    1-5). Centre = the planner's per-scene `outline_node.tension` when present,
    else the motif beat's `tension_target` (1-5) lifted to 0-100 (×20). When
    NEITHER is present the band is the widest [0,100] (no false flag). The band is
    centre ± halfwidth, clamped to [0,100]. No new tension scale is invented."""
    if node_tension is not None:
        centre = node_tension
    elif beat_tension_target is not None:
        centre = beat_tension_target * 20
    else:
        return (0, 100)
    lo = max(0, centre - halfwidth)
    hi = min(100, centre + halfwidth)
    return (lo, hi)


# ── sampling (cost-bounded, §5.2 / gap4) ────────────────────────────────────

class _RngLike(Protocol):
    def random(self) -> float: ...


def should_judge_conformance(
    *,
    beat_role: str | None,
    tension: int | None,
    has_motif: bool,
    rng: _RngLike,
    sample_pct: int,
    high_threshold: int = 70,
) -> bool:
    """Pure sampling decision (§5.2). Deterministic given `rng`.

    - A scene with NO bound motif is never judged (nothing planned to conform to).
    - A HIGH_WEIGHT_BEATS beat (climax/midpoint/crisis/reversal …) is ALWAYS judged
      — a missed climax is the expensive failure.
    - A scene whose `tension >= high_threshold` (the existing 70 gate) is ALWAYS
      judged.
    - Otherwise judged with probability `sample_pct`% (so low-tension scenes aren't
      a blind spot, but cost stays bounded)."""
    if not has_motif:
        return False
    if beat_role is not None and beat_role.strip().lower() in HIGH_WEIGHT_BEATS:
        return True
    if tension is not None and tension >= high_threshold:
        return True
    if sample_pct <= 0:
        return False
    if sample_pct >= 100:
        return True
    return rng.random() < (sample_pct / 100.0)
