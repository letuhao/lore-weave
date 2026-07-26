"""Apply policy for fuzzy HIL — confirm, auto, handoff chains."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

from app.engine.plan_forge.eval_fidelity import evaluate_spec_fidelity
from app.engine.plan_forge.interpret import interpret_feedback, is_lazy_handoff
from app.engine.plan_forge.refine import AcceptResult, accept_refine, refine_spec
from app.engine.plan_forge.self_check import run_self_check


@dataclass
class ApplyResult:
    spec: dict[str, Any]
    accepted: bool
    interpretation: dict[str, Any]
    accept_result: AcceptResult | None = None
    fidelity_before: float = 0.0
    fidelity_after: float = 0.0
    chat_response: str = ""
    rounds: list[dict[str, Any]] = field(default_factory=list)


def format_diagnosis_card(interpretation: dict[str, Any]) -> str:
    lines = [
        f"**Intent:** {interpretation.get('intent')} | **Confidence:** {interpretation.get('confidence')}",
        f"**Apply mode:** {interpretation.get('apply_mode')}",
    ]
    if interpretation.get("focus_paths"):
        lines.append(f"**Focus:** {', '.join(interpretation['focus_paths'])}")
    for d in interpretation.get("diagnosis") or []:
        lines.append(f"- [{d.get('gap_id', '?')}] {d.get('issue')}: {d.get('suggested_fix')}")
    if interpretation.get("clarifying_questions"):
        lines.append("**Cần làm rõ:**")
        for q in interpretation["clarifying_questions"]:
            lines.append(f"- {q}")
    rev = interpretation.get("draft_revision") or {}
    if rev.get("instruction"):
        lines.append(f"**Đề xuất sửa:** {rev['instruction'][:300]}")
    return "\n".join(lines)


def format_chat_response(
    *,
    interpretation: dict[str, Any],
    accepted: bool,
    fidelity_before: float,
    fidelity_after: float,
    remaining_gaps: int,
) -> str:
    mode = interpretation.get("apply_mode", "")
    if mode == "needs_clarification":
        qs = interpretation.get("clarifying_questions") or ["Bạn muốn sửa phần nào?"]
        return "Mình cần làm rõ thêm:\n" + "\n".join(f"- {q}" for q in qs)

    status = "đã áp dụng" if accepted else "chưa áp dụng (bị reject gate)"
    delta = fidelity_after - fidelity_before
    sign = "+" if delta >= 0 else ""
    return (
        f"Đã interpret feedback ({interpretation.get('intent')}). Sửa đổi {status}.\n"
        f"Fidelity: {fidelity_before:.2f} → {fidelity_after:.2f} ({sign}{delta:.2f})\n"
        f"Còn {remaining_gaps} gap. "
        + (interpretation.get("draft_revision") or {}).get("instruction", "")[:150]
    )


ConfirmFn = Callable[[dict[str, Any]], bool]


def apply_interpretation(
    spec: dict[str, Any],
    interpretation: dict[str, Any],
    *,
    client: Any,
    source_checksum: str,
    fidelity_cfg: dict[str, Any],
    package: dict[str, Any] | None = None,
    constraint_ledger: list[str] | None = None,
    confirm_fn: ConfirmFn | None = None,
    analyze: dict[str, Any] | None = None,
) -> ApplyResult:
    ledger = list(constraint_ledger or [])
    mode = interpretation.get("apply_mode", "confirm")
    revision = interpretation.get("draft_revision")

    if mode == "needs_clarification" or not revision:
        return ApplyResult(
            spec=spec,
            accepted=False,
            interpretation=interpretation,
            chat_response=format_chat_response(
                interpretation=interpretation,
                accepted=False,
                fidelity_before=0,
                fidelity_after=0,
                remaining_gaps=0,
            ),
        )

    if mode == "confirm" and confirm_fn is not None:
        if not confirm_fn(interpretation):
            return ApplyResult(
                spec=spec,
                accepted=False,
                interpretation=interpretation,
                chat_response="Đã hủy — không apply revision.",
            )

    rev = {**revision, "constraint_ledger": ledger}
    before = copy.deepcopy(spec)
    fb = evaluate_spec_fidelity(before, fidelity_cfg)["score"]
    candidate = refine_spec(before, rev, client=client, source_checksum=source_checksum, analyze=analyze)
    fa = evaluate_spec_fidelity(candidate, fidelity_cfg)["score"]
    accept = accept_refine(
        before,
        candidate,
        rev,
        package=package,
        fidelity_before=fb,
        fidelity_after=fa,
    )
    out_spec = candidate if accept.accepted else before
    gaps = evaluate_spec_fidelity(out_spec, fidelity_cfg).get("gaps") or []

    return ApplyResult(
        spec=out_spec,
        accepted=accept.accepted,
        interpretation=interpretation,
        accept_result=accept,
        fidelity_before=fb,
        fidelity_after=fa if accept.accepted else fb,
        chat_response=format_chat_response(
            interpretation=interpretation,
            accepted=accept.accepted,
            fidelity_before=fb,
            fidelity_after=fa if accept.accepted else fb,
            remaining_gaps=len(gaps),
        ),
        rounds=[{"revision": rev, "accepted": accept.accepted, "reasons": accept.reasons}],
    )


def apply_handoff_chain(
    spec: dict[str, Any],
    *,
    client: Any,
    source_checksum: str,
    fixture_path: Any,
    fidelity_path: Any,
    fidelity_cfg: dict[str, Any],
    package: dict[str, Any] | None = None,
    constraint_ledger: list[str] | None = None,
    max_rounds: int = 3,
    analyze: dict[str, Any] | None = None,
) -> ApplyResult:
    ledger = list(constraint_ledger or [])
    current = spec
    all_rounds: list[dict[str, Any]] = []
    last_interp: dict[str, Any] = {}
    fb = evaluate_spec_fidelity(current, fidelity_cfg)["score"]

    for _ in range(max_rounds):
        report = run_self_check(current, fixture_path, fidelity_path)
        gaps = report.get("ranked_gaps") or []
        if not gaps:
            break
        from app.engine.plan_forge.interpret import _build_revision_from_gap

        rev = _build_revision_from_gap(gaps[0], [], report.get("section_map") or [], intent="handoff")
        rev["constraint_ledger"] = ledger
        before = copy.deepcopy(current)
        f_before = evaluate_spec_fidelity(before, fidelity_cfg)["score"]
        candidate = refine_spec(before, rev, client=client, source_checksum=source_checksum, analyze=analyze)
        f_after = evaluate_spec_fidelity(candidate, fidelity_cfg)["score"]
        accept = accept_refine(
            before,
            candidate,
            rev,
            package=package,
            fidelity_before=f_before,
            fidelity_after=f_after,
        )
        all_rounds.append({"gap_id": gaps[0].get("id"), "accepted": accept.accepted})
        if accept.accepted:
            current = candidate
            entry = rev.get("instruction", "")[:200]
            if entry and entry not in ledger:
                ledger.append(entry)
        else:
            break
        last_interp = {
            "intent": "handoff",
            "apply_mode": "auto",
            "draft_revision": rev,
            "diagnosis": [{"gap_id": gaps[0].get("id"), "issue": gaps[0].get("detail", "")}],
        }

    fa = evaluate_spec_fidelity(current, fidelity_cfg)["score"]
    remaining = len(evaluate_spec_fidelity(current, fidelity_cfg).get("gaps") or [])
    return ApplyResult(
        spec=current,
        accepted=bool(all_rounds) and any(r.get("accepted") for r in all_rounds),
        interpretation=last_interp or {"intent": "handoff", "apply_mode": "auto"},
        fidelity_before=fb,
        fidelity_after=fa,
        chat_response=format_chat_response(
            interpretation=last_interp or {"intent": "handoff"},
            accepted=True,
            fidelity_before=fb,
            fidelity_after=fa,
            remaining_gaps=remaining,
        ),
        rounds=all_rounds,
    )


def process_user_turn(
    user_message: str,
    spec: dict[str, Any],
    section_map: list[dict[str, Any]],
    *,
    client: Any,
    source_checksum: str,
    fixture_path: Any,
    fidelity_path: Any,
    fidelity_cfg: dict[str, Any],
    package: dict[str, Any] | None = None,
    constraint_ledger: list[str] | None = None,
    chat_context: str | None = None,
    confirm_fn: ConfirmFn | None = None,
    analyze: dict[str, Any] | None = None,
    use_llm_interpret: bool = True,
) -> ApplyResult:
    self_report = run_self_check(spec, fixture_path, fidelity_path)
    interp = interpret_feedback(
        user_message,
        spec,
        section_map,
        self_check_report=self_report,
        chat_context=chat_context,
        client=client if use_llm_interpret else None,
        fixture_path=fixture_path,
        fidelity_path=fidelity_path,
    )

    if is_lazy_handoff(user_message) or interp.get("intent") == "handoff":
        if "sửa hết" in user_message.lower() or "làm đi" in user_message.lower() or is_lazy_handoff(user_message):
            return apply_handoff_chain(
                spec,
                client=client,
                source_checksum=source_checksum,
                fixture_path=fixture_path,
                fidelity_path=fidelity_path,
                fidelity_cfg=fidelity_cfg,
                package=package,
                constraint_ledger=constraint_ledger,
                analyze=analyze,
            )

    return apply_interpretation(
        spec,
        interp,
        client=client,
        source_checksum=source_checksum,
        fidelity_cfg=fidelity_cfg,
        package=package,
        constraint_ledger=constraint_ledger,
        confirm_fn=confirm_fn,
        analyze=analyze,
    )
