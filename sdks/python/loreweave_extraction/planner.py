"""Two-phase extraction planner (PLAN lane / architecture §3.1, §8.4).

The extraction pipeline historically only PACKED kinds up to a fixed count
(`plan_kind_batches`) — a pack-only model with no way to SPLIT a unit that is too big
for the model's context. That produced the failure modes S1–S5: an oversized
(chapter × kind) unit silently truncated mid-output (finish_reason=length → lost
entities) instead of being split, and there was no surfaced fan-out / cost signal.

This planner adds the missing direction. `plan()` is two-phase and PURE (no I/O):

  Phase 1 — normalize/split: any unit whose estimated input/output exceeds the
    per-call budget is split along its declared `split_axis` (chunk → kind → attr).
    A unit that cannot be reduced below budget is emitted as `Unplannable` so the
    cost-gate surfaces it instead of the executor truncating it.
  Phase 2 — pack: fit the (now in-budget) units into `LLMCall`s up to the per-call
    budget AND `max_units_per_call`.

Each packed unit carries a stable `id` the model must echo; VALIDATE asserts a 1:1
mapping before WRITEBACK (§8.4.6). The per-call budget is a function of the model
caps AND `reasoning_effort` (effort grows the output reservation — composes the
reasoning spec). Pricing is INJECTED (price-per-token resolved from
provider-registry by the caller) — the SDK never hardcodes a price or model name.

Reuses `ContextBudget`/`estimate_text_tokens` for the token arithmetic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .context_budget import DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL_CONTEXT

# Effort → output-reservation multiplier. A reasoning model spends extra output tokens on
# its thinking trace, so a higher effort needs a larger output reservation (smaller input
# budget). Composes the reasoning-effort spec (the resolver runs BEFORE planning and feeds
# Policy.reasoning_effort). 'none'/unknown → 1.0 (no thinking overhead).
_EFFORT_OUTPUT_MULTIPLIER: dict[str, float] = {
    "none": 1.0,
    "low": 1.3,
    "medium": 1.8,
    "high": 2.5,
}


def effort_output_multiplier(effort: str | None) -> float:
    return _EFFORT_OUTPUT_MULTIPLIER.get(effort or "none", 1.0)


@dataclass(frozen=True)
class ModelCaps:
    """The RESOLVED model limits (from provider-registry — never hardcoded here)."""

    context_window: int = DEFAULT_MODEL_CONTEXT
    output_ceiling: int = DEFAULT_MAX_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        if self.context_window <= 0 or self.output_ceiling <= 0:
            raise ValueError("ModelCaps context_window/output_ceiling must be > 0")


@dataclass(frozen=True)
class Policy:
    """Planning knobs. `reasoning_effort` feeds the output multiplier; `budget_ratio` is
    the fraction of the context window usable for prompt input (the rest is headroom);
    `expansion_ratio` scales a unit's declared est_output (model verbosity); `max_units_
    per_call` caps packing breadth (the MAX_KINDS_PER_BATCH analog that bounds per-call
    output); `fan_out_warn_threshold` flags pathological split fan-out."""

    reasoning_effort: str = "none"
    budget_ratio: float = 0.7
    expansion_ratio: float = 1.0
    max_units_per_call: int = 3
    fan_out_warn_threshold: int = 8
    # Injected pricing (USD per token), resolved from provider-registry by the caller.
    # 0.0 ⇒ unknown → cost range is all-zero (the caller treats it as "unpriced").
    price_per_input_token: float = 0.0
    price_per_output_token: float = 0.0

    def __post_init__(self) -> None:
        if not 0 < self.budget_ratio <= 1.0:
            raise ValueError("budget_ratio must be in (0, 1]")
        if self.max_units_per_call < 1:
            raise ValueError("max_units_per_call must be >= 1")


@dataclass(frozen=True)
class Unit:
    """One schedulable work-unit (e.g. a chapter×kind-group). `est_input`/`est_output` are
    token estimates. `splittable` + `split_axis` declare HOW it can be reduced when it
    exceeds budget. `max_parts` is the GRANULARITY ceiling — the most sub-units this unit can
    actually be subdivided into along its axis (e.g. its kind count); a split that needs more
    than this is `Unplannable` rather than an unrealizable promise. None = unbounded (a text
    `chunk` split can always slice finer). `group` (e.g. a chapter id) drives the
    calls_per_chapter metric; `origin` tracks the original unit id across splits."""

    id: str
    kind: str
    est_input: int
    est_output: int
    splittable: bool = False
    split_axis: str | None = None  # "chunk" | "kind" | "attr" | None
    max_parts: int | None = None
    group: str | None = None
    origin: str | None = None  # set on split children → the parent unit id

    def __post_init__(self) -> None:
        if self.est_input < 0 or self.est_output < 0:
            raise ValueError(f"Unit {self.id}: est_input/est_output must be >= 0")
        if self.max_parts is not None and self.max_parts < 1:
            raise ValueError(f"Unit {self.id}: max_parts must be >= 1")

    @property
    def root(self) -> str:
        return self.origin or self.id


@dataclass(frozen=True)
class LLMCall:
    units: list[Unit]
    est_input: int
    est_output: int

    @property
    def unit_ids(self) -> list[str]:
        """The stable ids the model must echo (VALIDATE asserts 1:1 — §8.4.6)."""
        return [u.id for u in self.units]


@dataclass(frozen=True)
class Unplannable:
    unit: Unit
    reason: str


@dataclass(frozen=True)
class CostRange:
    low: float
    expected: float
    high: float


@dataclass(frozen=True)
class Plan:
    calls: list[LLMCall]
    est_llm_calls: int
    calls_per_chapter: float
    est_cost_range: CostRange
    model_fit_warning: str | None
    unplannable: list[Unplannable] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanRequest:
    # `pipeline` is a passthrough LABEL (which pipeline asked — e.g. "extraction") for the
    # caller's logging/telemetry; the planner does not branch on it (it is model+policy+unit
    # driven). Kept on the request so a multi-pipeline caller can correlate plans.
    pipeline: str
    units: list[Unit]
    model: ModelCaps
    policy: Policy = field(default_factory=Policy)


def per_call_budget(model: ModelCaps, policy: Policy) -> tuple[int, int]:
    """(input_budget, output_budget) for one call. The output reservation grows with
    reasoning effort (and is clamped to the model's output ceiling); the input budget is
    what's left of the effort-scaled context window after the output reservation."""
    out = min(
        model.output_ceiling,
        max(1, int(model.output_ceiling * effort_output_multiplier(policy.reasoning_effort))),
    )
    inp = int(model.context_window * policy.budget_ratio) - out
    return max(0, inp), out


def _split_unit(unit: Unit, in_budget: int, out_budget: int, exp_ratio: float) -> list[Unit]:
    """Split an oversized unit into the FEWEST even sub-units that each fit both budgets,
    preserving the root id (origin) for the fan-out guard. Returns [unit] unchanged when it
    already fits."""
    eff_out = math.ceil(unit.est_output * exp_ratio)
    parts_in = math.ceil(unit.est_input / in_budget) if in_budget > 0 else 0
    parts_out = math.ceil(eff_out / out_budget) if out_budget > 0 else 0
    parts = max(parts_in, parts_out, 1)
    if parts <= 1:
        return [unit]
    root = unit.root
    sub_in = math.ceil(unit.est_input / parts)
    sub_out = math.ceil(unit.est_output / parts)
    return [
        Unit(
            id=f"{unit.id}#{i}", kind=unit.kind, est_input=sub_in, est_output=sub_out,
            splittable=unit.splittable, split_axis=unit.split_axis, group=unit.group, origin=root,
        )
        for i in range(parts)
    ]


def plan(req: PlanRequest) -> Plan:
    in_budget, out_budget = per_call_budget(req.model, req.policy)
    exp = req.policy.expansion_ratio
    rationale: list[str] = [
        f"per-call budget: input={in_budget} output={out_budget} "
        f"(effort={req.policy.reasoning_effort}, x{effort_output_multiplier(req.policy.reasoning_effort)})"
    ]

    # ── Phase 1: normalize / split ──────────────────────────────────────────────
    normalized: list[Unit] = []
    unplannable: list[Unplannable] = []
    for u in req.units:
        eff_out = math.ceil(u.est_output * exp)
        if u.est_input <= in_budget and eff_out <= out_budget:
            normalized.append(u)
            continue
        if not u.splittable:
            unplannable.append(Unplannable(
                u, f"{u.est_input}in/{eff_out}out exceeds budget {in_budget}/{out_budget}; not splittable"))
            rationale.append(f"UNPLANNABLE {u.id}: oversized + not splittable")
            continue
        parts = _split_unit(u, in_budget, out_budget, exp)
        # Granularity ceiling: a unit only subdivides so far along its axis (e.g. its kind
        # count). Needing more sub-units than `max_parts` means the axis can't be cut fine
        # enough → Unplannable (surfaced), never an unrealizable plan the executor can't honor.
        if u.max_parts is not None and len(parts) > u.max_parts:
            unplannable.append(Unplannable(
                u, f"needs {len(parts)} sub-units along {u.split_axis} but max_parts={u.max_parts}"))
            rationale.append(f"UNPLANNABLE {u.id}: needs {len(parts)} > max_parts {u.max_parts}")
            continue
        # A minimal split (a single sub-unit) that STILL overflows is irreducible (covers the
        # in_budget<=0 / out_budget<=0 case and the expansion_ratio rounding edge).
        if any(p.est_input > in_budget or math.ceil(p.est_output * exp) > out_budget for p in parts):
            unplannable.append(Unplannable(
                u, f"irreducible along {u.split_axis}: a single sub-unit still exceeds budget"))
            rationale.append(f"UNPLANNABLE {u.id}: irreducible along {u.split_axis}")
            continue
        normalized.extend(parts)
        if len(parts) > 1:
            rationale.append(f"split {u.id} along {u.split_axis} → {len(parts)} units")

    # ── Phase 2: pack ───────────────────────────────────────────────────────────
    calls: list[LLMCall] = []
    cur: list[Unit] = []
    cur_in = cur_out = 0
    for u in normalized:
        eff_out = math.ceil(u.est_output * exp)
        fits = (
            cur
            and len(cur) < req.policy.max_units_per_call
            and cur_in + u.est_input <= in_budget
            and cur_out + eff_out <= out_budget
        )
        if not fits and cur:
            calls.append(LLMCall(units=cur, est_input=cur_in, est_output=cur_out))
            cur, cur_in, cur_out = [], 0, 0
        cur.append(u)
        cur_in += u.est_input
        cur_out += eff_out
    if cur:
        calls.append(LLMCall(units=cur, est_input=cur_in, est_output=cur_out))

    # ── Metrics / guards ────────────────────────────────────────────────────────
    groups = {u.group for u in normalized if u.group is not None}
    n_chapters = len(groups) if groups else 0
    calls_per_chapter = (len(calls) / n_chapters) if n_chapters else float(len(calls))

    # Fan-out guard: how many calls did a single ORIGINAL unit explode into?
    per_root: dict[str, int] = {}
    for c in calls:
        for root in {u.root for u in c.units}:
            per_root[root] = per_root.get(root, 0) + 1
    worst = max(per_root.values(), default=0)
    model_fit_warning = None
    if worst > req.policy.fan_out_warn_threshold:
        worst_root = max(per_root, key=per_root.get)
        model_fit_warning = (
            f"unit '{worst_root}' fans out to {worst} calls (> {req.policy.fan_out_warn_threshold}); "
            f"consider a larger-context model or fewer kinds per unit"
        )
        rationale.append(model_fit_warning)

    total_in = sum(c.est_input for c in calls)
    total_out = sum(c.est_output for c in calls)
    expected = total_in * req.policy.price_per_input_token + total_out * req.policy.price_per_output_token
    # The range brackets the expected by the effort multiplier (output is the variable cost).
    mult = effort_output_multiplier(req.policy.reasoning_effort)
    low = total_in * req.policy.price_per_input_token + (total_out / mult) * req.policy.price_per_output_token
    high = total_in * req.policy.price_per_input_token + total_out * mult * req.policy.price_per_output_token

    return Plan(
        calls=calls,
        est_llm_calls=len(calls),
        calls_per_chapter=calls_per_chapter,
        est_cost_range=CostRange(low=round(low, 6), expected=round(expected, 6), high=round(high, 6)),
        model_fit_warning=model_fit_warning,
        unplannable=unplannable,
        rationale=rationale,
    )
