# W5 — Conformance (binary, advisory) + calibration harness — DETAILED DESIGN

> **Workstream:** W5 of the narrative-motif-library parallel build (composition-service / Python).
> **Spec basis:** [`docs/specs/2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) §14 (conformance & traceability), §R2.1 (binary-first + bootstrap gold set), §R1.2 F-3 (no calibrated narrative judge — audit), §16.1 (the structural-vs-stylistic dial split this dim checks).
> **Status:** DESIGN — file-by-file. Architecture DECIDED upstream; this is the build map for the 4 files W5 owns.
> **Size contribution:** part of the XL P1 effort. W5 alone ≈ **M** (1 new engine module + 1 script + 1 router + tests; 1 cross-service-adjacent seam = the eval gateway; advisory-only, no migration of its own — it writes into the existing `generation_job.critic` JSONB).

---

## 0. Files W5 OWNS (the deliverable boundary)

| File | New/changed | Role |
|---|---|---|
| `services/composition-service/app/engine/motif_conformance.py` | **NEW** | The binary `motif_conformance` judge (prompt + verdict parse + degrade) — mirrors `engine/critic.py:judge_prose`. |
| `services/composition-service/scripts/calibrate_motif_conformance.py` | **NEW** | The calibration harness: PO-seed + strong-model bootstrap → the existing binary `calibrate_judge`. Also the eval-gate (`ships` calibrated-or-labeled). |
| `services/composition-service/app/routers/conformance.py` | **NEW** | The trace read (`GET …/conformance?scope=chapter`): join `outline_node ⋈ motif_application ⋈ generation_job` → planned│realized│conformance per scene. |
| `services/composition-service/tests/unit/test_motif_conformance.py` | **NEW** | Unit tests + the audit risk-guards as failing-first tests. |

**Adjacent files W5 TOUCHES but does NOT own** (coordinate with sibling workstreams — additive, no rewrite):
- `app/engine/critic.py` — W5 calls its `parse_critique_json` helper (reuse, no change). If a shared `_merge_critic_dim` helper is wanted, it lands here as an additive function (coordinate with whoever owns critic.py; default: keep the merge local to W5).
- `app/routers/engine.py` — the `/jobs/{job_id}/critique` endpoint (§14.1) is where the conformance dim is *produced* during the normal critique call. W5 adds a **conformance branch** there (additive, behind the same critic-model gate). Owned by the engine/critic workstream; W5 supplies the function it calls.
- `app/db/repositories/motif_application.py` — owned by the schema/repo workstream (W1/W2). W5 **reads** it via a join query; W5 does not define the table.
- `app/mcp/server.py` — the Tier-W `composition_conformance_run` tool (arc scope) is **P4**, stubbed here as a future hook only (§14.5). Not built in P1.
- `app/config.py` — W5 adds 4 config keys (§2.4); coordinate so the keys land once.

**Hard scope fence (from §R1.5 / §14.7):** W5 ships the **scene-level binary** dim + the **coarse `chapter_id` trace read** + the **calibration harness**. The **arc extract-diff** (§14.4, thread-progression / pacing-curve / legal-succession diff) is **OUT — P4** (it rides F-1's missing causal graph + full re-extraction). The **fine offset-span anchor** (`scene_span`, §14.3) is **OUT — P2/P4**. Do not build them here.

---

## 1. Scope + the critic-dim contract (what gets written to `generation_job.critic`)

### 1.1 The data sink — reuse `generation_job.critic`, no migration

The existing advisory critic (`engine/critic.py:judge_prose`) already writes a JSONB blob to `generation_job.critic` via `GenerationJobsRepo.update_status(..., critic=...)`. That column is the sink for `motif_conformance` too — **no schema change** (§14.1: "Stored in `generation_job.critic` (JSONB — no schema change)").

Today the blob is:
```jsonc
{
  "coherence": 4, "voice_match": 3, "pacing": 4, "canon_consistency": 5,   // judge_prose dims (int 0-5 | null)
  "violations": [ { "rule_id": "...", "violated": true, "span": "...", "why": "..." } ],
  // (derivative Works also fold in derivative_findings + a regen gate)
}
```

W5 **adds one key**, `motif_conformance`, alongside the existing dims. **It never overwrites the dict** — the repo's `update_status` does `critic = COALESCE($5::jsonb, critic)` (whole-column replace on non-null), so W5 must **read-modify-write merge** exactly like `dismiss_violation` does (read `job.critic`, merge the new key, write the whole dict back). This is the load-bearing detail; a blind `update_status(critic={"motif_conformance": …})` would **destroy `coherence`/`violations`**. (See §2.3 for the merge helper.)

### 1.2 The `motif_conformance` shape (the contract)

```jsonc
"motif_conformance": {
  "beat_realized":      true,          // BINARY y/n — did the prose realize the planned beat?
  "tension_band_match": false,         // BINARY y/n — did realized tension land in the planned band?
  "calibrated":         false,         // is the judge that produced this CURRENTLY trusted? (drives the UI label)
  "motif_id":           "0192...",     // which motif beat was bound (from motif_application; null if unbound scene)
  "beat_key":           "bait",        // the specific beat within the motif (echo, for the trace view)
  "planned_tension_band": [60, 80],    // the [lo, hi] band the verdict was judged against (provenance)
  "reason":             "<=20 words",  // short rationale (UX "why")
  "error":              null           // "conformance_unavailable" | "conformance_<status>" on degrade; null on success
}
```

**Field rules (mirror `critic.py:_coerce_score` / `_filter_violations` defensive parsing):**
- `beat_realized` / `tension_band_match` — coerced to `bool`; a missing/malformed value → `null` (unjudged on that sub-flag, NOT defaulted true).
- `calibrated` — **NOT** produced by the judge. Stamped by the *producer* (the critique endpoint) from a config flag (`motif_conformance_calibrated`, §2.4) that flips to `true` only after the calibration harness passes (§3). Until then it is `false` → the FE renders "unverified self-report" (§5, AI-quality R1). This is the honest-labeling mechanism made structural.
- `error` — on any LLM/parse/timeout failure, the whole dim degrades to `{"beat_realized": null, "tension_band_match": null, "calibrated": <flag>, "error": "conformance_unavailable"}`. **Never raises** (advisory, §14.6 + CC4). The judge being down must never block a generate or a critique.

**Why binary, not graded (§R1.2 F-3 + §R2.1):** the existing `calibrate_judge` is a **binary** trust gate (`Pair = (human_bool, judge_bool)` → kappa/balanced-acc). A graded 0-5 `motif_conformance` could NOT plug into it without ordinal calibration (QWK), which has no harness yet (`plot_density` is the graded dim — deferred to **P1.5**, §R2.1). Two binary sub-flags map cleanly onto two independent `Pair` streams (§3.3). This is the whole reason the dim is binary-first.

### 1.3 What this dim is and isn't (the §16.1 boundary)

`motif_conformance` is a **STRUCTURAL** check (the §16.1 left column: "what must occur"). It answers *"did the realized prose hit the planned beat at the planned tension?"* — NOT *"is the prose good / well-voiced / well-paced"* (those are `coherence`/`voice_match`/`pacing`, already judged). Compressing length (a §16 stylistic dial) must NOT flip `beat_realized` (§16.1: "a 350-word terse render still fully realized the scheme beat"). The prompt (§2.1) enforces this separation explicitly so the judge does not penalize a short scene for being short.

---

## 2. `engine/motif_conformance.py` — the binary judge

### 2.1 The prompt (concrete shape)

Modeled byte-for-byte on the patterns in `engine/critic.py:build_critique_prompt` and `loreweave_eval/llm_judge.py` (the two production judges): abstract/multilingual-safe rubric, `temperature=0.0`, thinking suppressed, JSON-only output, tolerant parse.

```python
"""Binary motif-conformance judge (§14 / §R2.1) — ADVISORY, never a hard gate.

Given a scene's PLANNED beat (the bound motif beat + its tension band + the
roles that should be present) and the REALIZED prose, emit two BINARY verdicts:
  beat_realized      — did the prose actually enact the planned beat's intent?
  tension_band_match — did the scene's dramatic tension land in the planned band?

This is a STRUCTURAL judge (§16.1): it checks WHAT happened, never HOW it reads
(coherence/voice/pacing are judge_prose's job). A short, terse render that still
hits the beat is `beat_realized=true` — do NOT penalize compression.

Binary by design (§R2.1): two y/n flags plug into the EXISTING binary
calibrate_judge (cohen_kappa>=0.4 / balanced_acc>=0.75). A graded score would
need ordinal calibration (QWK) we don't have — that's plot_density, P1.5.

De-bias (critic.py §2.6 lesson): judge in the book's source_language; abstract
phrasing, NO English-only illustrative examples (they bias a CJK/VN judge).

CC4 (critic.py): any LLM/timeout/parse failure degrades to an empty advisory
verdict with an `error` marker — NEVER raises (advisory must not block).
"""

from __future__ import annotations
import logging
from typing import Any

from loreweave_llm.errors import LLMError
from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.critic import parse_critique_json   # REUSE the tolerant fence-stripping parser
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

# The degrade sentinel — the dim shape on any failure (calibrated stamped by the caller).
_EMPTY = {"beat_realized": None, "tension_band_match": None, "reason": ""}


def build_conformance_prompt(
    *, beat_intent: str, beat_key: str, motif_name: str,
    tension_band: tuple[int, int], expected_roles: list[str],
    passage: str, profile: BookProfile,
) -> tuple[str, str]:
    """Build (system, user) for the binary conformance judge. tension_band is the
    [lo, hi] the planner placed (derived from motif.beats[].tension_target +
    outline_node.tension); expected_roles are the role labels the binding requires
    present (motif_application.role_bindings → glossary names)."""
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
        "Judge by MEANING in the text's own language and script. Do NOT reward or "
        "penalise prose style, length, voice, or pacing — only whether the planned "
        "STRUCTURE was realized. Return ONLY a JSON object: "
        '{"beat_realized": <true|false>, "tension_band_match": <true|false>, '
        '"reason": "<=20 words"}.'
        + lang
    )
    roles_block = ", ".join(expected_roles) or "(none specified)"
    user = (
        f"PLANNED BEAT: {motif_name} / {beat_key}\n"
        f"BEAT INTENT: {beat_intent}\n"
        f"ROLES THAT SHOULD APPEAR: {roles_block}\n"
        f"PLANNED TENSION BAND (0-100): {tension_band[0]}-{tension_band[1]}\n\n"
        f"REALIZED PROSE:\n{passage}"
    )
    return system, user


def normalize_conformance(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Shape a parsed judge response into the dim contract. Missing/malformed
    flags → None (unjudged), reason coerced to str. Defensive like
    critic.normalize_critique — one bad field never poisons the dim."""
    parsed = parsed or {}

    def _flag(v: Any) -> bool | None:
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in ("true", "false"):
            return v.strip().lower() == "true"
        return None  # NOT defaulted — an absent flag is "unjudged", not "pass"

    return {
        "beat_realized": _flag(parsed.get("beat_realized")),
        "tension_band_match": _flag(parsed.get("tension_band_match")),
        "reason": str(parsed.get("reason", ""))[:200],
    }


async def judge_motif_conformance(
    judge: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    beat_intent: str, beat_key: str, motif_name: str,
    tension_band: tuple[int, int], expected_roles: list[str],
    passage: str, profile: BookProfile, max_tokens: int = 512,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run the binary conformance judge. Returns the dim dict (WITHOUT `calibrated`/
    `motif_id`/`beat_key`/band — the CALLER folds those provenance fields in, §2.3).
    CC4: any failure degrades to _EMPTY + error, never raises."""
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
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.0,
                "max_tokens": max_tokens,
                # Same no-think knobs critic.py uses (Qwen3/LM-Studio honor
                # reasoning_effort; others honor chat_template_kwargs). The judge
                # emits tiny JSON — reasoning tokens are pure budget burn.
                "reasoning_effort": "none",
                "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
            },
            job_meta={"extractor": "motif_conformance"}, trace_id=trace_id,
        )
    except LLMError as exc:
        logger.warning("motif_conformance degraded (LLM error): %s", exc)
        return {**_EMPTY, "error": "conformance_unavailable"}
    if job.status != "completed":
        logger.info("motif_conformance job status=%s → degraded", job.status)
        return {**_EMPTY, "error": f"conformance_{job.status}"}
    content = extract_judge_content(job.result)
    return normalize_conformance(parse_critique_json(content))
```

**Why reuse `parse_critique_json` and `extract_judge_content` rather than re-implement:** they are the production tolerant-parse path (fence strip + first-balanced-object fallback; result-envelope content extraction). Re-implementing risks drift from the proven behaviour. (`llm_judge.py` has its own `_extract_json_object`; we use critic.py's because this judge lives in composition-service, next to critic.py, and shares its `LLMClient`/`BookProfile` types.)

### 2.2 Tension-band derivation (the one non-obvious input)

`tension_band` is `[lo, hi]` on the **0-100** scale (the `outline_node.tension` scale, per `adaptive_k.py` docstring — **NOT** 1-5). The planner placed each scene's `tension`; the motif beat carries a `tension_target` (1-5 in `motif.beats[]`, per spec §2.1). The producer (the critique branch, §2.3) computes the band as:

- centre = `outline_node.tension` (the planner's per-scene 0-100 value) when present;
- else centre = `motif.beats[].tension_target × 20` (lift the 1-5 target to 0-100);
- band = `[max(0, centre − BAND_HALFWIDTH), min(100, centre + BAND_HALFWIDTH)]` where `BAND_HALFWIDTH = motif_conformance_tension_halfwidth` (config, default 15).

This keeps the judge's tension question concrete (a band, not a point) and matches `adaptive_k`'s existing 0-100 convention. **No new tension scale is invented** (the §16 "don't invent a new dial mechanism" rule).

### 2.3 The provenance merge (where `calibrated` + `motif_id` get stamped)

The judge returns only `{beat_realized, tension_band_match, reason}`. The **producer** (the critique branch in `engine.py`, supplied by W5 as a helper) folds in provenance + the calibration flag, then **read-modify-write merges** into `critic`:

```python
def build_conformance_dim(judge_out: dict, *, motif_id, beat_key, band, calibrated: bool) -> dict:
    """Fold provenance + the calibration flag into the judge output → the dim contract."""
    return {
        **judge_out,
        "motif_id": str(motif_id) if motif_id else None,
        "beat_key": beat_key,
        "planned_tension_band": list(band),
        "calibrated": bool(calibrated),
    }

def merge_conformance(critic: dict | None, dim: dict) -> dict:
    """Read-modify-write: add motif_conformance WITHOUT clobbering existing dims.
    The repo does critic = COALESCE($5, critic) (whole-column replace), so we MUST
    merge into the full dict here (the dismiss_violation pattern)."""
    out = dict(critic or {})
    out["motif_conformance"] = dim
    return out
```

The critique endpoint then calls `jobs.update_status(user_id, job_id, job.status, critic=merge_conformance(job.critic, dim))`. **Both `build_conformance_dim` and `merge_conformance` live in `motif_conformance.py`** (W5-owned) so the merge contract is unit-tested in W5's test file, even though the *call site* is in engine.py.

### 2.4 The actuator (against flag-and-ignore — AI-quality R3)

`motif_conformance` is advisory (§14.6) — it never blocks a commit. The §R2.1 actuator (so the flag is *acted on*, not ignored) has three parts; W5 owns the wiring points:

1. **Surface in the trace** — the `GET …/conformance` read (§4) returns the dim per scene so the author's work/trace view (mockup 07-A) renders planned│realized│conformance. This is W5's `routers/conformance.py`.
2. **"Regenerate to beat" one-click** — a drift (`beat_realized=false`) row offers regenerate. This reuses the **existing** §11 scene-regenerate path (`POST …/scenes/{scene}/regenerate`, owned by the planner/engine workstream) — W5 does NOT build a new regenerate; it ensures the trace read returns the `outline_node_id` + `motif_id` + `beat_key` that the existing regenerate needs as inputs.
3. **Instrument the act-on-flag rate** — emit a structured log/metric `motif_conformance_flag` (one per produced dim, fields: `beat_realized`, `tension_band_match`, `calibrated`, `acted` later joined from a regenerate) so we can measure whether flags get acted on. W5 emits the produce-side signal in the critique branch; the act-side join is a follow-up (tracked, not P1-blocking).

**Config keys W5 adds (`app/config.py`):**
| Key | Default | Purpose |
|---|---|---|
| `motif_conformance_enabled` | `false` | Master gate — OFF → zero cost (mirrors `narrative_thread_enabled`). Producer no-ops when off. |
| `motif_conformance_calibrated` | `false` | Stamps `calibrated` on every dim. Flips to `true` ONLY after the harness passes (§3) AND a human sets it. Drives the UI honesty label. |
| `motif_conformance_tension_halfwidth` | `15` | The 0-100 band half-width (§2.2). |
| `motif_conformance_sample_random_pct` | `20` | Random-sample rate for non-high-tension scenes (§5 sampling). |

---

## 3. The calibration harness — `scripts/calibrate_motif_conformance.py`

### 3.1 The honesty framing (audit F-3, stated plainly)

**`loreweave_eval`'s reported F1=0.869 is an EXTRACTION judge** (entity/relation/event precision/recall vs human-correction gold — `llm_judge.py`). `motif_conformance` is a **NEW dimension with NO gold set** (audit F-3: "Stop calling any of this 'reuse the calibrated judge'"). The *mechanism* (`calibrate_judge`, binary kappa/balanced-acc) is reused; the *trust* is not inherited — it must be re-earned on a conformance-specific gold set. Until then the signal ships **`calibrated=false`** and the UI says so (§5).

### 3.2 The gold set — bootstrap, two sources

The harness builds a labeled set of `(scene, planned_beat) → human_beat_realized, human_tension_band_match` rows:

- **Source A — PO seed (~25-30 scenes).** The PO already hand-read the POC scenes (§R2.1). A small JSONL the PO fills: `{scene_text, motif_name, beat_key, beat_intent, tension_band, expected_roles, gold_beat_realized, gold_tension_band_match}`. Lives at `services/composition-service/scripts/motif_conformance_gold/po_seed.jsonl` (committed; it is abstract role-slot + author-written prose, NOT copied source — the §12.6 copyright rule). This is the **ground-truth anchor** — the human is truth, exactly as `calibration.py`'s `Pair` semantics require (`Pair = (human_says_correct, judge_says_correct)`).
- **Source B — strong-model-as-gold bootstrap (larger).** A frontier BYOK model (resolved via the user's model-registry, through the gateway — NOT a hardcoded model, NOT a direct SDK) labels a larger set of scenes. This **widens** the validation set cheaply but is **second-class truth** (a model, not a human). The harness treats A as the calibration ground truth and B as an *agreement-check / coverage extender*; **the gate decision rests on A** (model-as-gold can drift, so it never becomes the metric of record on its own — the panel-safety spirit).

> **Honest gap:** Source B is a model grading toward another model's notion of "beat realized". If the strong model is itself weak on the book's language (the `llm_judge.py` "honest limits" caveat), B is noisy there. The harness reports A-only and A+B kappa **separately** so the reader sees how much B moved the number.

### 3.3 Wiring to the EXISTING binary `calibrate_judge`

The harness runs the local `judge_motif_conformance` over every gold scene, then builds **two `Pair` streams** (one per binary sub-flag) and calibrates each independently:

```python
from loreweave_eval.calibration import calibrate_judge   # the EXISTING binary gate

# pairs_realized: [(gold_beat_realized, judge_beat_realized), ...]  (drop rows where judge returned None — unjudged)
# pairs_tension:  [(gold_tension_band_match, judge_tension_band_match), ...]
cal_realized = calibrate_judge("motif_conformance.beat_realized", pairs_realized,
                               min_kappa=0.4, min_balanced_accuracy=0.75)
cal_tension  = calibrate_judge("motif_conformance.tension_band_match", pairs_tension,
                               min_kappa=0.4, min_balanced_accuracy=0.75)

# The dim is "calibrated" only if BOTH sub-flags clear the gate AND the panel is
# honestly labeled (it can't pass panel_safety with one model — §5).
calibrated = cal_realized.passed and cal_tension.passed
```

**Two independent streams, not one** — because `beat_realized` and `tension_band_match` are different questions with different base rates; a judge can be reliable on one and not the other. `calibrate_judge` returns `JudgeCalibration` with `cohen_kappa`, `balanced_accuracy`, `passed`, and the confusion matrix per stream. A degenerate single-class set (e.g. all gold scenes realized their beat) returns `passed=False` (kappa undefined) — the harness surfaces "need both classes in the gold set" so the PO knows to include deliberate-drift negatives.

### 3.4 Harness structure (mirrors `eval_a3_decompose.py` + the eval-gate stance)

`eval_a3_decompose.py` is the template: a self-contained script run from the host against the live stack, login → resolve models → exercise → report a GATE verdict with honest caveats. The conformance harness is **offline-first** (it reads a committed gold JSONL, not a live book) but uses the same gateway for the judge call:

```
1. Load po_seed.jsonl (Source A) [+ optionally bootstrap.jsonl (Source B)].
2. Resolve the LOCAL judge model (the self-host model) AND, for Source B, a strong BYOK model
   — both via /v1/model-registry/user-models (no hardcoded names; the ai-provider-gate rule).
3. For each gold scene: run judge_motif_conformance → collect (gold_flag, judge_flag) pairs.
4. calibrate_judge per sub-flag (A-only, then A+B) → kappa / balanced-acc / passed.
5. PRINT the gate:
     GATE: CALIBRATED — both sub-flags kappa>=0.4 & balanced-acc>=0.75 on the PO seed (n=NN).
            → a human may now set motif_conformance_calibrated=true.
     GATE: SHIP UNCALIBRATED — kappa below threshold (or gold set too small / single-class).
            → the dim ships calibrated=false (UI-labeled "unverified"); enlarge the gold set / tune the prompt.
   Always print: panel_safety note (single-model self-host → self-report; §5), A-only vs A+B deltas.
```

**The eval-gate IS this script** (§6): the P1 ship condition is *"the harness runs and prints a verdict; either it calibrates, or it ships labeled-uncalibrated"* — **shipping uncalibrated is an ACCEPTED outcome**, not a failure (§R2.1: "OR ship as uncalibrated advisory and say so in the UI"). The gate that *would* fail the build is: the harness can't run, the merge clobbers other dims, or the advisory dim blocks a commit.

### 3.5 Who builds the gold set (the remaining OPEN, §R1.7)

The harness is buildable **now** with an empty/tiny seed (it just prints "SHIP UNCALIBRATED — gold set n=0"). The **PO labels ~25 scenes** to flip it to calibrated (§R2.1 residual). Recommendation in §8.

---

## 4. The trace read — `routers/conformance.py` (coarse `chapter_id`, §14.2)

### 4.1 The join (data already exists — §14.2)

The trace chain is already in the schema; W5 adds the **read**:

```
outline_node (scene)            [PLANNED: beat_role, goal/synopsis, tension, present_entity_ids]
  ├─ motif_application          [motif_id, motif_version, beat_key?, role_bindings]   (W1/W2-owned table)
  └─ generation_job (latest completed per node)  [REALIZED: result.text, critic.motif_conformance]
```

`GET /v1/composition/works/{project_id}/conformance?scope=chapter&chapter_id={id}` returns, per scene in the chapter:

```jsonc
{
  "scope": "chapter",
  "chapter_id": "…",
  "calibrated": false,                       // echo motif_conformance_calibrated (UI banner)
  "scenes": [
    {
      "outline_node_id": "…",
      "title": "…", "beat_role": "…",
      "planned":   { "motif_id": "…", "motif_name": "…", "beat_key": "bait",
                     "tension": 72, "role_bindings": { "schemer": "<entity>" } },
      "realized":  { "job_id": "…", "has_prose": true },          // text presence only (not the prose blob)
      "conformance": { "beat_realized": true, "tension_band_match": false,
                       "calibrated": false, "reason": "…", "error": null }   // from generation_job.critic
                     // null when no completed job, or the job has no motif_conformance dim yet
    }
  ]
}
```

**Coarse only (§14.2 / §R1.5):** the join keys on the **shared `chapter_id`** (both `outline_node.chapter_id` and the extraction anchor carry it) — no fine offset-span attribution. The realized side is the **latest completed `generation_job` per `outline_node_id`** (same "latest completed job per scene node" rule the publish-gate and stitch already use — see engine.py's note on `chapter_scene_drafts`). Arc-scope (`scope=arc`) is **rejected with 501/Not-Implemented** in P1 (it needs the §14.4 extract-diff → P4); the param is accepted in the contract so the FE shape is stable, but returns a clear "arc conformance is not available yet (P4)".

### 4.2 Router skeleton (mirrors the engine.py router conventions)

```python
router = APIRouter(prefix="/v1/composition")

@router.get("/works/{project_id}/conformance")
async def read_conformance(
    project_id: UUID,
    scope: Literal["chapter"] = "chapter",          # "arc" intentionally absent → 422 (P4)
    chapter_id: UUID | None = None,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    motif_apps: MotifApplicationRepo = Depends(get_motif_application_repo),  # W1/W2-owned dep
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> dict[str, Any]:
    work = await works.get(user_id, project_id)
    if work is None:
        raise HTTPException(404, "work not found")
    if chapter_id is None:
        raise HTTPException(422, {"code": "CHAPTER_ID_REQUIRED"})
    # 1) planned: the chapter's scene nodes (user+project scoped repo read)
    scenes = await outline.scenes_for_chapter(user_id, project_id, chapter_id)
    # 2) bound motifs: motif_application rows for those nodes (one query, IN the node ids)
    apps = await motif_apps.by_nodes(user_id, project_id, [s.id for s in scenes])
    # 3) realized: latest completed job per node + its critic.motif_conformance
    latest = await jobs.latest_completed_by_nodes(user_id, project_id, [s.id for s in scenes])
    # 4) assemble planned│realized│conformance (pure, in-memory join) — see §4.1 shape
    return _assemble_conformance(work, chapter_id, scenes, apps, latest)
```

**New repo reads W5 needs** (coordinate ownership):
- `MotifApplicationRepo.by_nodes(user_id, project_id, node_ids)` — bound motif per node. If W1/W2 hasn't added it, W5 adds it to that repo (additive method, user+project scoped). **Defect-guard:** it MUST filter `user_id` + `project_id` (the kinds-bug tenancy rule); a node-id-only query is a cross-tenant read.
- `GenerationJobsRepo.latest_completed_by_nodes(user_id, project_id, node_ids)` — one row per node, the most-recent `status='completed'` job, returning `id` + `critic` + a `has_text` boolean (NOT the prose blob — keep the payload small; the trace view shows status, the editor shows prose). Additive to the jobs repo. The existing `idx_generation_job_node` index covers the per-node lookup.

**The assemble step is PURE** (`_assemble_conformance`, in `routers/conformance.py` or a tiny `engine/conformance_trace.py` helper) → unit-tested without a DB (§6). It is the join-correctness surface the audit gap4/F-3 tests hit.

---

## 5. The single-model self-host caveat + sampling

### 5.1 panel_safety can't be met with one local model → label as self-report (audit AI-quality gap5)

`loreweave_eval/calibration.py:panel_safety` requires **≥2 disjoint judges** (and no generator-in-panel) for a trustworthy metric of record. A single-model self-host deployment **structurally cannot** satisfy this — there is one model; it both drafts and would judge. The honest consequences W5 bakes in:

1. **The judge model MUST differ from the drafter** where possible (the anti-self-reinforcement rule the critique endpoint already enforces: `if str(critic_ref) == str(drafter_ref): skip`). On a single-model box this gate **skips conformance entirely** (no distinct critic) — the dim is simply absent, not faked. That is correct: better no signal than a self-graded one.
2. When a distinct-but-still-local judge exists (two local models), the dim is produced but `calibrated` stays `false` until the harness passes, and the UI labels it **"unverified self-report"** (§R2.1 / AI-quality R1). The harness's printed `panel_safety` note states plainly: *"single-model / two-local-model panel — does not meet the ≥2-disjoint-judge metric-of-record bar; treat as self-report."*
3. **Never claim "calibrated" from a single-model run.** Even if A-only kappa passes on a tiny seed, the panel-safety note travels with the report so no one reads a self-host kappa as a production-grade metric. (This is the §R1.2 F-3 / gap5 honesty requirement made concrete.)

### 5.2 Sampling — judge high-tension beats + a random sample, NOT every scene (audit gap4 / cost)

Running the judge on **every** generated scene doubles LLM spend on the hot path. The producer samples (§R2.1):

- **Always judge high-tension beats** — reuse `adaptive_k.HIGH_WEIGHT_BEATS` (the existing frozenset of climax/midpoint/crisis/reversal beat keys) OR `outline_node.tension >= plan_high_tension_threshold` (the existing 70 gate). These are the beats where drift matters most (a missed climax is the expensive failure).
- **Plus a random sample** of the rest at `motif_conformance_sample_random_pct` (default 20%) — so low-tension scenes aren't a blind spot, but cost stays bounded.
- **A bound scene with no motif** (`motif_application` absent) is **not judged** (nothing planned to conform to) — `conformance: null` in the trace.

The sampling decision is a pure function `should_judge_conformance(beat_role, tension, has_motif, rng) -> bool` in `motif_conformance.py` → unit-tested (deterministic with a seeded rng). It is the gap4 risk-guard surface (§7).

---

## 6. Tests + eval-gate

### 6.1 `tests/unit/test_motif_conformance.py` (pure unit, no live stack)

| Test | Asserts |
|---|---|
| `test_normalize_conformance_well_formed` | `{"beat_realized": true, "tension_band_match": false, "reason": "x"}` → correct dim. |
| `test_normalize_conformance_missing_flag_is_none` | Absent `tension_band_match` → `None` (NOT defaulted true). The "unjudged ≠ pass" rule. |
| `test_normalize_conformance_string_bools` | `"true"`/`"false"` strings coerced; garbage → `None`. |
| `test_normalize_conformance_malformed_json` | `parse_critique_json` returns `None` → `_EMPTY`-shaped dim, no raise. |
| `test_judge_degrades_on_llm_error` | A `JudgeLLMClient` double raising `LLMError` → `error="conformance_unavailable"`, never raises (CC4). |
| `test_judge_degrades_on_noncompleted_job` | job.status="failed" → `error="conformance_failed"`. |
| `test_judge_empty_passage_short_circuits` | blank passage → `conformance_no_passage`, no LLM call. |
| `test_merge_conformance_preserves_existing_dims` | **Load-bearing:** `merge_conformance({"coherence":4,"violations":[…]}, dim)` keeps `coherence`+`violations`. The COALESCE-clobber guard. |
| `test_build_conformance_dim_stamps_provenance` | `calibrated`/`motif_id`/`beat_key`/`planned_tension_band` folded in correctly. |
| `test_tension_band_from_node_tension` | band centred on `outline_node.tension`; falls back to `tension_target×20`; clamped [0,100]. |
| `test_prompt_no_english_only_examples` | system prompt contains no English illustrative phrases when `source_language!='en'` (the de-bias rule — assert the `lang` clause present + no hardcoded example sentence). |
| `test_prompt_separates_structure_from_style` | system prompt explicitly says "do NOT reward/penalise prose style, length, voice" (the §16.1 boundary). |

### 6.2 The eval-gate (`calibrate_motif_conformance.py` — §3.4)

The script IS the gate. Ship condition (P1): **the harness runs and prints CALIBRATED or SHIP-UNCALIBRATED**; uncalibrated-labeled is an accepted ship (§R2.1). A genuine fail is only: harness can't run, or one of the advisory-never-blocks / merge-preserves / join-correct invariants breaks.

### 6.3 Cross-service live-smoke (the CLAUDE.md VERIFY token)

W5's judge call is a real gateway round-trip (composition-service → provider-registry). At VERIFY, the evidence string includes either:
- `live smoke: judge_motif_conformance ran a real conformance verdict on a 2-service stack-up (composition→provider-registry)` — run the harness against a live stack with the PO seed, OR
- `LIVE-SMOKE deferred to D-MOTIF-CONFORMANCE-LIVE-SMOKE` if the full stack isn't bootable at dev time, OR
- `live infra unavailable: <reason>`.

The harness doubles as the live-smoke (it makes the cross-service judge call).

---

## 7. Audit risk-guards as failing-first tests

Per the Debugging Protocol (failing test → fix), each audit risk is encoded as a test that must be RED before the guard exists:

| Audit risk | Failing-first test | The guard it forces |
|---|---|---|
| **F-3** — false "reuse the calibrated judge" | `test_dim_calibrated_flag_defaults_false` — a freshly-produced dim with no calibration run has `calibrated=false`; and `test_harness_calibrates_independently` — the harness runs `calibrate_judge` on conformance-specific pairs, NOT inheriting extraction's F1. | The dim is **independently calibrated or labeled uncalibrated** — never silently presented as trusted. |
| **AI-quality R3** — actuator wired + instrumented (flag-and-ignore) | `test_conformance_emits_flag_signal` — producing a dim emits the structured `motif_conformance_flag` log/metric; and `test_trace_returns_regenerate_inputs` — the trace read returns `outline_node_id`+`motif_id`+`beat_key` (the inputs the existing scene-regenerate needs). | The flag is **surfaced + actionable + measurable**, not a dead field. |
| **gap4** — sampling not every-scene | `test_sampling_skips_low_tension_unsampled` — a low-tension non-high-weight beat with rng above the pct is NOT judged; `test_sampling_always_judges_high_tension` — a `HIGH_WEIGHT_BEATS` beat is always judged; `test_unbound_scene_not_judged` — no motif → no judge call. | Cost-bounded sampling; high-tension always covered. |
| **gap5** — single-model panel honesty | `test_harness_reports_panel_safety_note` — the harness output includes the single-model self-report caveat; `test_calibrated_false_when_panel_unsafe` — even if kappa passes on a tiny seed, the printed verdict carries the panel-safety warning. | A self-host kappa is **never** presentable as a production metric of record. |
| **§14.6** — advisory never blocks | `test_conformance_failure_never_raises` (judge down → degraded dim, generate/critique proceeds); `test_beat_not_realized_does_not_gate` — a `beat_realized=false` dim does not change the job status / publish-gate. | Conformance is **advisory** — it informs, it never forbids (the `narrative_thread` stance). |

---

## 8. Open micro-decisions + recommendation

| # | Decision | Options | **Recommendation** |
|---|---|---|---|
| MD-1 | **Who/when builds the gold set?** (the §R1.7 OPEN) | (a) PO labels ~25 scenes now; (b) ship uncalibrated, label later; (c) bootstrap purely from a strong model. | **(b) then (a).** Ship P1 with `calibrated=false` + the harness + an empty/tiny seed (the dim is honest-labeled and immediately useful as a surfaced signal). The **PO labels ~25 scenes** opportunistically (they already hand-read POCs) to flip `calibrated=true` in a follow-up — NOT a P1 blocker. **(c) alone is rejected** — model-as-gold can't be the metric of record (panel-safety spirit). Use the strong model only to *extend coverage* (Source B), gated on the PO seed (Source A). |
| MD-2 | Where does the conformance dim get **produced**? | (a) inside the existing `/jobs/{id}/critique` call (one extra judge call); (b) a separate `/conformance/run` endpoint; (c) inside the auto-generate canon-reflect step. | **(a).** The critique endpoint already resolves the distinct critic model + the passage + runs `judge_prose`; conformance is a sibling dim. Adding a branch there (behind `motif_conformance_enabled` + the distinct-critic gate + sampling) reuses all the wiring and writes one merged `critic`. A separate endpoint duplicates model-resolution + a second job round-trip. |
| MD-3 | `beat_key` source — does `motif_application` carry the specific bound beat? | (a) it does (schema has a `beat_key`/annotations field); (b) only `motif_id` is bound, beat inferred from the scene's order within the chapter. | **(a) if available, else degrade to motif-level.** Spec §R1.4 gives `motif_application.annotations` JSONB; recommend the binder (W1/W2) writes the bound `beat_key` there. If absent, the judge falls back to judging against the **motif summary** (coarser "did this scene advance the motif" rather than "did it hit beat 3") — still useful, flagged in the dim as `"beat_key": null`. Coordinate with the binder workstream. |
| MD-4 | Band half-width default | 10 / 15 / 20 (0-100 scale) | **15.** Wide enough that a reasonable render isn't false-flagged on tension, tight enough that a calm-written climax is caught. Config-tunable; revisit after the PO seed shows the false-flag rate. |
| MD-5 | `arc` scope param now or P4-only? | (a) accept + 501; (b) reject 422 | **(a) accept the param, return a clear "P4 / not available" body.** Keeps the FE contract stable so the arc view can be built later without a contract change; honest about availability. (Chapter is the only scope that computes in P1.) |
| MD-6 | Reuse critic.py's `parse_critique_json` vs llm_judge.py's `_extract_json_object`? | either | **critic.py's.** Same service, same `LLMClient`/`BookProfile`, already the composition-side tolerant parser. Avoids a cross-package import of an `_underscore`-private helper. |

---

## 9. Task list (W5, P1)

1. **`engine/motif_conformance.py`** — `build_conformance_prompt`, `normalize_conformance`, `judge_motif_conformance` (degrade-safe), `build_conformance_dim`, `merge_conformance`, `should_judge_conformance` (sampling), tension-band derivation helper. (§2, §5.2)
2. **`config.py`** (coordinate) — the 4 keys (§2.4).
3. **`engine.py` critique branch** (coordinate with critic/engine owner) — behind `motif_conformance_enabled` + distinct-critic gate + sampling: resolve the bound motif/beat/band → call the judge → `merge_conformance` → `update_status` → emit the `motif_conformance_flag` signal. (§2.3, §8 MD-2)
4. **`routers/conformance.py`** — `GET …/conformance?scope=chapter` + the pure `_assemble_conformance` join; `scope=arc` → P4 not-available body. (§4)
5. **Repo reads** (coordinate W1/W2) — `MotifApplicationRepo.by_nodes` (user+project scoped) + `GenerationJobsRepo.latest_completed_by_nodes`. (§4.2)
6. **`scripts/calibrate_motif_conformance.py`** — load gold JSONL → run judge → two `Pair` streams → `calibrate_judge` per sub-flag (A-only + A+B) → print CALIBRATED / SHIP-UNCALIBRATED + panel-safety note. (§3)
7. **`scripts/motif_conformance_gold/po_seed.jsonl`** — the seed scaffold (schema + a few example rows; PO fills, §3.2 / §8 MD-1).
8. **`tests/unit/test_motif_conformance.py`** — the §6.1 unit tests + the §7 audit risk-guards (failing-first).
9. **Wire `routers/conformance.py` into `main.py`/router registration** (additive).
10. **VERIFY** — run the harness against a live stack (live-smoke token, §6.3); confirm the merge preserves existing dims on a real job; confirm advisory-never-blocks on a generate with the judge down.
11. **SESSION + Deferred** — add `D-MOTIF-CONFORMANCE-GOLD-SET` (PO labels ~25 scenes → flip `calibrated`), `D-MOTIF-CONFORMANCE-ARC-DIFF` (§14.4 extract-diff, P4), `D-MOTIF-CONFORMANCE-FINE-ANCHOR` (`scene_span`, §14.3, P2/P4), `D-MOTIF-CONFORMANCE-PLOT-DENSITY` (graded dim + QWK, P1.5), `D-MOTIF-CONFORMANCE-ACT-RATE` (act-on-flag join, instrumentation follow-up). Optionally `D-MOTIF-CONFORMANCE-LIVE-SMOKE` if deferred.

---

## 10. Sibling-workstream contract summary (so parallel builds don't collide)

W5 **depends on** (read-only): `motif` table (W1), `motif_application` table + binder (W1/W2 — needs the bound `motif_id`, `motif_version`, and ideally `beat_key` in `annotations`, §8 MD-3), the existing `outline_node`/`generation_job` (unchanged).
W5 **provides** (for others): the `motif_conformance` dim contract (§1.2), the `judge_motif_conformance` + `merge_conformance` functions the engine/critique workstream calls, the `GET …/conformance` trace read the FE workstream renders.
W5 **does NOT touch**: the planner select+bind (W?), the publish/adopt tenancy (W?), the MCP discovery tools (W?), the §17 stitch pass (W?). The Tier-W `composition_conformance_run` MCP tool (arc scope) is **P4** — a named future hook only.
