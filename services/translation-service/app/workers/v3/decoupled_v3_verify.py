"""LLM re-arch Phase 2b-T3b — decoupled V3 verify/correct loop.

The synchronous V3 verify/correct (`v3/orchestrator._verify_correct_persist`) is a
multi-round loop that pins the worker across its LLM waits:

    round 0: rule-verify (det) + LLM-verify (use_llm)
    while HIGH && round<max:  corrector (LLM, per flagged block) → keep-if-improved (det) → re-verify

This module runs that loop as a resumable state machine (mode='v3_verify') driven by
terminal events through the T2 consumer, chained AFTER the decoupled block translate
(defer-finalize: the chapter finalizes only here, once verify/correct is done).

The translation row has a SINGLE `provider_job_id` column, so the corrector is
**sequential** (one flagged block at a time) — fitting the same single-job-in-flight
model the block engine already uses, no schema change. Rule-verify + keep-if-improved
stay deterministic (no LLM); only LLM-verify + the corrector are decoupled steps.

resume_state (mode='v3_verify'):
  stage: verify | correct | finalize
  round: int (0 = initial verify)
  source_texts/draft_texts: {str(idx): text}  (draft mutated by accepted corrections)
  result_blocks / blocks: serialized block lists (result mutated; source for rebuild)
  cmap / glossary_prompt_block / knowledge_brief / source_lang / target / verifier_model
  qa_depth / use_llm / max_rounds
  report_issues / rule_issues: serialized Issues (current round's report + its rule half)
  flagged / correct_cursor: the correct stage's sequential cursor over flagged blocks
  msg / total_in / total_out / memo: finalize context (tokens accumulate across stages)
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from .quality import Issue, IssueReport

log = logging.getLogger(__name__)

VERIFY = "verify"
CORRECT = "correct"
FINALIZE = "finalize"

# Hard ceiling mirrors orchestrator._MAX_QA_ROUNDS — a misconfigured large value must
# not run unbounded LLM rounds.
_MAX_QA_ROUNDS = 5


# ── Issue serde (Issue ↔ JSON dict for resume_state JSONB) ──────────────────────

def _issue_to_dict(i: Issue) -> dict:
    return {
        "block_index": i.block_index, "type": i.type, "severity": i.severity,
        "detail": i.detail, "expected": i.expected, "detected_by": i.detected_by,
    }


def _issue_from_dict(d: dict) -> Issue:
    return Issue(
        d["block_index"], d["type"], d["severity"], d["detail"],
        d.get("expected"), d.get("detected_by", "rule"),
    )


def _issues_to_dicts(issues: list[Issue]) -> list[dict]:
    return [_issue_to_dict(i) for i in issues]


def _report_from_dicts(dicts: list[dict]) -> IssueReport:
    return IssueReport([_issue_from_dict(d) for d in dicts])


def _imap(d: dict) -> dict[int, str]:
    """JSON str-keyed text map → int-keyed (verify_rules wants int block indices)."""
    return {int(k): v for k, v in d.items()}


def _smap(d: dict[int, str]) -> dict:
    return {str(k): v for k, v in d.items()}


# ── deterministic rule-verify + keep-if-improved (pure, no LLM) ─────────────────

def _rule_report(rs: dict[str, Any], draft_texts: dict[int, str]) -> IssueReport:
    from .verifier import verify_rules
    return verify_rules(_imap(rs["source_texts"]), draft_texts, rs["cmap"], rs["target"])


def _cap_llm_issues(issues: list[Issue]) -> list[Issue]:
    """§12.2 conservative gate: an LLM-only flag never alone reaches the HIGH set that
    triggers a destructive re-translate — cap LLM high→med (matches orchestrator._verify)."""
    for i in issues:
        if i.severity == "high":
            i.severity = "med"
    return issues


def _merge_report(rule_dicts: list[dict], llm_issues: list[Issue]) -> IssueReport:
    report = _report_from_dicts(rule_dicts)
    report.issues.extend(_cap_llm_issues(llm_issues))
    return report


def keep_if_improved(rs: dict[str, Any], idx: int, corrected: str) -> bool:
    """Deterministic accept/reject for ONE corrected block: keep iff the rule-tier HIGH
    count drops (the LLM's non-determinism must not drive the accept decision)."""
    from .verifier import verify_rules
    report = _report_from_dicts(rs["report_issues"])
    orig_high = sum(1 for i in report.issues
                    if i.block_index == idx and i.severity == "high")
    src = _imap(rs["source_texts"]).get(idx, "")
    new_high = len(verify_rules({idx: src}, {idx: corrected}, rs["cmap"], rs["target"]).high)
    return new_high < orig_high


# ── shell: submit-assembly over the verifier/corrector seams ────────────────────

def assemble_verify_submit(rs: dict[str, Any]) -> dict:
    """Submit kwargs for the LLM-verify call over the current draft_texts."""
    from .llm_verifier import build_verify_submit_kwargs
    return build_verify_submit_kwargs(
        _imap(rs["source_texts"]), _imap(rs["draft_texts"]),
        rs["source_lang"], rs["target"], tuple(rs["verifier_model"]),
        knowledge_brief=rs.get("knowledge_brief", ""),
    )


def assemble_corrector_submit(rs: dict[str, Any], idx: int) -> dict:
    """Submit kwargs for ONE flagged block's correction (model from msg at the call site)."""
    from .corrector import build_corrector_submit_kwargs
    report = _report_from_dicts(rs["report_issues"])
    issues = [i for i in report.issues if i.block_index == idx and i.severity == "high"]
    src = _imap(rs["source_texts"])
    draft = _imap(rs["draft_texts"])
    return build_corrector_submit_kwargs(
        src.get(idx, ""), draft.get(idx, ""), issues,
        rs["source_lang"], rs["target"], rs.get("glossary_prompt_block", ""),
        block_idx=idx,
    )


# ── pure transitions ────────────────────────────────────────────────────────────

def _evaluate(rs: dict[str, Any]) -> dict[str, Any]:
    """Given the current report_issues + round, decide the next stage:
    HIGH issues remain AND we have a correction round left → CORRECT (seed flagged +
    cursor); else → FINALIZE. round IS the count of correction rounds already applied."""
    out = dict(rs)
    report = _report_from_dicts(rs["report_issues"])
    flagged = sorted(report.block_indices_with_high())
    if flagged and rs["round"] < rs["max_rounds"]:
        out["stage"] = CORRECT
        out["flagged"] = flagged
        out["correct_cursor"] = 0
    else:
        out["stage"] = FINALIZE
    return out


def fold_verify(rs: dict[str, Any], llm_issues: list[Issue]) -> dict[str, Any]:
    """Fold the LLM-verify terminal: merge the (capped) LLM issues with this round's rule
    issues → report_issues. The caller persists the round + evaluates."""
    out = dict(rs)
    out["report_issues"] = _issues_to_dicts(_merge_report(rs["rule_issues"], llm_issues).issues)
    return out


def begin_correct_next(rs: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
    """Return (rs, idx) for the next flagged block to correct, or (rs, None) when the
    round's corrections are exhausted (caller then re-verifies)."""
    cursor = rs.get("correct_cursor", 0)
    flagged = rs.get("flagged", [])
    if cursor < len(flagged):
        return rs, flagged[cursor]
    return rs, None


def apply_corrected(rs: dict[str, Any], idx: int, corrected: str | None) -> dict[str, Any]:
    """Apply one corrector terminal: keep-if-improved → maybe update draft_texts/
    result_blocks; advance the cursor. corrected None/empty ⇒ keep the original draft."""
    from ..block_classifier import rebuild_block
    out = dict(rs)
    if corrected and keep_if_improved(rs, idx, corrected):
        draft = dict(rs["draft_texts"])
        draft[str(idx)] = corrected
        out["draft_texts"] = draft
        blocks = list(rs["blocks"])
        result_blocks = list(rs["result_blocks"])
        result_blocks[idx] = rebuild_block(blocks[idx], corrected)
        out["result_blocks"] = result_blocks
    out["correct_cursor"] = rs.get("correct_cursor", 0) + 1
    return out


def start_next_round(rs: dict[str, Any]) -> dict[str, Any]:
    """A correction round finished (all flagged blocks corrected). Bump round, recompute
    this round's rule issues over the (possibly updated) draft, and set up re-verify:
    use_llm → stage=VERIFY (caller submits); rule_only → report=rule (caller persists +
    evaluates)."""
    out = dict(rs)
    out["round"] = rs["round"] + 1
    rule = _rule_report(rs, _imap(rs["draft_texts"]))
    out["rule_issues"] = _issues_to_dicts(rule.issues)
    if rs["use_llm"]:
        out["stage"] = VERIFY
    else:
        out["report_issues"] = out["rule_issues"]
    return out


# ── async shell: DB helpers (conn-aware; mirror orchestrator's SQL byte-for-byte) ──

async def _clear_issues(ex, ct_id) -> None:
    await ex.execute(
        "DELETE FROM translation_quality_issues WHERE chapter_translation_id=$1", ct_id,
    )


async def _persist_round_issues(ex, ct_id, report: IssueReport, round_: int) -> None:
    await ex.execute(
        "DELETE FROM translation_quality_issues WHERE chapter_translation_id=$1 AND round=$2",
        ct_id, round_,
    )
    for it in report.issues:
        await ex.execute(
            """INSERT INTO translation_quality_issues
                 (chapter_translation_id, block_index, round, issue_type,
                  severity, detail, expected, detected_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
            ct_id, it.block_index, round_, it.type, it.severity, it.detail,
            it.expected, it.detected_by,
        )


async def _update_rollup(ex, ct_id, report: IssueReport, rounds_used: int) -> None:
    await ex.execute(
        """UPDATE chapter_translations
             SET quality_score=$1, unresolved_high_count=$2, qa_rounds_used=$3
           WHERE id=$4""",
        report.quality_score(), len(report.high), rounds_used, ct_id,
    )


async def _persist_v3(ex, ct_id, provider_job_id, rs: dict) -> None:
    """Persist the v3_verify resume_state + the single in-flight provider_job_id (the
    pattern the translation row uses — one job at a time; corrector is sequential)."""
    import json
    await ex.execute(
        """UPDATE chapter_translations
             SET provider_job_id=$2, pipeline_stage='v3_verify', resume_state=$3, updated_at=now()
           WHERE id=$1""",
        ct_id, UUID(str(provider_job_id)), json.dumps(rs),
    )


async def _submit_verify(ex, llm_client, ct_id, rs: dict) -> None:
    submit = await llm_client.submit_job(
        user_id=rs["msg"]["user_id"], **assemble_verify_submit(rs),
    )
    await _persist_v3(ex, ct_id, submit.job_id, dict(rs, stage=VERIFY))


async def _submit_corrector(ex, llm_client, ct_id, rs: dict, idx: int) -> None:
    msg = rs["msg"]
    submit = await llm_client.submit_job(
        user_id=msg["user_id"], model_source=msg["model_source"],
        model_ref=str(msg["model_ref"]), **assemble_corrector_submit(rs, idx),
    )
    await _persist_v3(ex, ct_id, submit.job_id, dict(rs, stage=CORRECT))


def _seed_v3(block_rs: dict, result_blocks: list[dict]) -> dict:
    """Build the mode='v3_verify' resume_state from the completed block translate."""
    from ..block_classifier import classify_block, extract_translatable_text
    from ..decoupled_block_translate import memo_from_translated
    v3 = block_rs["v3"]
    source_texts: dict[int, str] = {}
    draft_texts: dict[int, str] = {}
    for i, (sb, tb) in enumerate(zip(block_rs["blocks"], result_blocks)):
        if classify_block(sb) == "passthrough":
            continue
        s = extract_translatable_text(sb)
        if not s:
            continue
        source_texts[i] = s
        draft_texts[i] = extract_translatable_text(tb)
    return {
        "mode": "v3_verify", "stage": VERIFY, "round": 0,
        "source_texts": _smap(source_texts), "draft_texts": _smap(draft_texts),
        "result_blocks": result_blocks, "blocks": block_rs["blocks"],
        "cmap": dict(v3.get("cmap") or {}),
        "glossary_prompt_block": block_rs.get("glossary_prompt_block", ""),
        "knowledge_brief": v3.get("knowledge_brief", ""),
        "source_lang": block_rs["source_lang"], "target": block_rs["target_code"],
        "verifier_model": list(v3["verifier_model"]),
        "qa_depth": v3["qa_depth"], "use_llm": v3["use_llm"], "max_rounds": v3["max_rounds"],
        "report_issues": [], "rule_issues": [], "flagged": [], "correct_cursor": 0,
        "msg": block_rs["msg"],
        "total_in": block_rs.get("total_input", 0),
        "total_out": block_rs.get("total_output", 0),
        "memo": memo_from_translated(block_rs),
        # review-impl B — carry the source text so the finalize's M7d quality judge gets
        # the real source (the block finalize_cb reads rs['chapter_text']); without it the
        # decoupled-v3 judge would degrade to structural-only, diverging from sync v3.
        "chapter_text": block_rs.get("chapter_text", ""),
    }


async def transition_from_block(conn, llm_client, ct_id: UUID, block_rs: dict,
                                result_blocks: list[dict]):
    """Called UNDER the block engine's FOR UPDATE lock when a v3 chapter's block translate
    completes (`block_rs['post_block']=='v3_verify'`). Seeds the v3_verify state + submits
    the first LLM step (verify, or the first corrector for a rule_only chapter with HIGH
    rule issues) — persisting the new provider_job_id UNDER THE LOCK so a redelivered
    last-batch terminal sees the advanced id and skips (race-safe transition).

    Returns a finalize payload `(body_json, in, out, memo)` ONLY for the no-LLM-work case
    (rule_only + no HIGH rule issues) so the caller finalizes the block result outside the
    lock; returns None when v3_verify is now in flight (caller must NOT finalize/clear)."""
    import json
    rs = _seed_v3(block_rs, result_blocks)
    if not rs["draft_texts"]:
        # No translatable blocks to verify — finalize the block result as-is.
        return (json.dumps(result_blocks), rs["total_in"], rs["total_out"], rs["memo"])

    await _clear_issues(conn, ct_id)  # clean slate (re-run safety, mirrors sync)
    rule = _rule_report(rs, _imap(rs["draft_texts"]))
    rs["rule_issues"] = _issues_to_dicts(rule.issues)

    if rs["use_llm"]:
        await _submit_verify(conn, llm_client, ct_id, rs)
        return None

    # rule_only: round-0 report IS the rule report → persist + evaluate.
    rs["report_issues"] = rs["rule_issues"]
    await _persist_round_issues(conn, ct_id, _report_from_dicts(rs["report_issues"]), 0)
    rs = _evaluate(rs)
    if rs["stage"] == CORRECT:
        await _submit_corrector(conn, llm_client, ct_id, rs, rs["flagged"][0])
        return None
    # FINALIZE with no corrections — record the rollup/metric now (under the lock) and let
    # the caller finalize the block result outside the lock.
    await _update_rollup(conn, ct_id, _report_from_dicts(rs["report_issues"]), rs["round"])
    _record_verify_metric(ct_id, rs, _report_from_dicts(rs["report_issues"]))
    return (json.dumps(result_blocks), rs["total_in"], rs["total_out"], rs["memo"])


def _record_verify_metric(ct_id, rs, report) -> None:
    from ...metrics import record_stage
    record_stage(
        "translation.verify", pipeline="v3", ct=str(ct_id),
        qa_depth=rs["qa_depth"], rounds=rs["round"],
        high_final=len(report.high), issues_final=len(report.issues),
        score=report.quality_score(),
    )


async def resume(*, pool, llm_client, job, chapter_translation_id: UUID, finalize_cb) -> None:
    """Consumer entry for a v3_verify terminal event. FOR UPDATE race-guard (mirrors the
    block engine): fold the verify/corrector terminal, submit the next LLM step, or
    finalize. Finalize runs OUTSIDE the lock (finalize_cb → _finalize_chapter re-locks the
    same row → nesting would deadlock)."""
    import json
    job_uuid = UUID(str(job.job_id))
    finalize_payload = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT resume_state, provider_job_id FROM chapter_translations WHERE id=$1 FOR UPDATE",
                chapter_translation_id,
            )
            if row is None or row["resume_state"] is None:
                return
            if row["provider_job_id"] != job_uuid:
                return  # already folded + advanced by a concurrent resume
            rs = row["resume_state"]
            rs = rs if isinstance(rs, dict) else json.loads(rs)
            if rs.get("mode") != "v3_verify":
                return

            # Token parity (review-impl A): the finalize records BLOCK-translate tokens
            # only — matching the sync v3 path, whose chapter input/output_tokens come from
            # the block stage and do NOT fold in the verify/corrector calls. (Those calls
            # are still billed per-job in provider-registry usage_logs.)

            if rs["stage"] == VERIFY:
                from .llm_verifier import parse_verify_job
                llm_issues = parse_verify_job(job, {int(k) for k in rs["draft_texts"]})
                rs = fold_verify(rs, llm_issues)
                await _persist_round_issues(
                    conn, chapter_translation_id, _report_from_dicts(rs["report_issues"]), rs["round"])
                rs = _evaluate(rs)
                if rs["stage"] == CORRECT:
                    await _submit_corrector(conn, llm_client, chapter_translation_id, rs, rs["flagged"][0])
                else:
                    finalize_payload = await _finalize_in_lock(conn, chapter_translation_id, rs)

            elif rs["stage"] == CORRECT:
                from .corrector import parse_corrector_job
                idx = rs["flagged"][rs["correct_cursor"]]
                rs = apply_corrected(rs, idx, parse_corrector_job(job))
                _, nxt = begin_correct_next(rs)
                if nxt is not None:
                    await _submit_corrector(conn, llm_client, chapter_translation_id, rs, nxt)
                else:
                    rs = start_next_round(rs)
                    if rs["stage"] == VERIFY:
                        await _submit_verify(conn, llm_client, chapter_translation_id, rs)
                    else:  # rule_only re-verify → persist + evaluate
                        await _persist_round_issues(
                            conn, chapter_translation_id, _report_from_dicts(rs["report_issues"]), rs["round"])
                        rs = _evaluate(rs)
                        if rs["stage"] == CORRECT:
                            await _submit_corrector(conn, llm_client, chapter_translation_id, rs, rs["flagged"][0])
                        else:
                            finalize_payload = await _finalize_in_lock(conn, chapter_translation_id, rs)
            else:  # FINALIZE / unexpected — finalize defensively
                finalize_payload = await _finalize_in_lock(conn, chapter_translation_id, rs)

    # ── outside the FOR UPDATE lock ──
    if finalize_payload is not None:
        body_json, total_in, total_out, memo = finalize_payload
        await finalize_cb(body_json, total_in, total_out, memo)
        from ..decoupled_block_translate import _clear_resume_state
        await _clear_resume_state(pool, chapter_translation_id)


async def _finalize_in_lock(conn, ct_id, rs):
    """Under the lock: write the rollup + the verify metric; return the finalize payload
    (the caller finalizes the chapter OUTSIDE the lock — _finalize_chapter re-locks)."""
    import json
    report = _report_from_dicts(rs["report_issues"])
    await _update_rollup(conn, ct_id, report, rs["round"])
    _record_verify_metric(ct_id, rs, report)
    return (json.dumps(rs["result_blocks"]), rs["total_in"], rs["total_out"], rs["memo"])
