"""V3 LLM Verifier — Tier-2 semantic QA (M2).

Asks the verifier model for issues the deterministic rule-tier can't catch
(omissions, mistranslations, subtle wrong names, invented content). The
orchestrator caps these at advisory severity so an LLM-only flag never alone
triggers a destructive re-translate (§12.2 conservative gating). Best-effort —
any failure or malformed output returns [] (verification never fails the chapter).
"""
from __future__ import annotations

import json
import logging
import re

from ..session_translator import _parse_sdk_response, _lang_name, _SafeFormatMap
from .quality import Issue

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a meticulous {source_lang} to {target_lang} translation QA reviewer. "
    "For each [BLOCK N], compare the SOURCE with its TRANSLATION and report real "
    "problems: omission (dropped meaning), mistranslation (wrong meaning), "
    "wrong_name (a character/place rendered incorrectly), or added (invented "
    "content). Respond with ONLY a JSON array of "
    '{{"block": int, "type": str, "severity": "high"|"med", "detail": str}}. '
    "Output [] if every block is faithful. No prose, no markdown — only the JSON array."
)

_VALID_TYPES = frozenset({"omission", "mistranslation", "wrong_name", "added"})


def _build_messages(source_texts: dict[int, str], draft_texts: dict[int, str],
                    source_lang: str, target_lang: str,
                    knowledge_brief: str = "") -> list[dict]:
    parts = [
        f"[BLOCK {idx}]\nSOURCE: {source_texts.get(idx, '')}\nTRANSLATION: {draft_texts[idx]}"
        for idx in sorted(draft_texts)
    ]
    system = _SYSTEM.format_map(_SafeFormatMap({
        "source_lang": _lang_name(source_lang),
        "target_lang": _lang_name(target_lang),
    }))
    # M4b/G4 — the same character/relation brief the Translator saw, so the
    # verifier judges names/pronouns against the authored context.
    preamble = f"{knowledge_brief}\n\n" if knowledge_brief else ""
    user = preamble + "Review these blocks:\n\n" + "\n\n".join(parts)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_issues(text: str, valid_indices: set[int]) -> list[Issue]:
    """Parse the verifier's JSON array → Issues. Tolerant: strips code fences,
    extracts the first JSON array, ignores malformed entries, never raises."""
    if not text or not text.strip():
        return []
    body = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text.strip()).strip()
    m = re.search(r"\[.*\]", body, flags=re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    issues: list[Issue] = []
    for it in data:
        if not isinstance(it, dict):
            continue
        try:
            block = int(it.get("block"))
        except (TypeError, ValueError):
            continue
        if block not in valid_indices:
            continue
        typ = str(it.get("type", "")).lower()
        if typ not in _VALID_TYPES:
            typ = "mistranslation"
        sev = str(it.get("severity", "med")).lower()
        if sev not in ("high", "med", "low"):
            sev = "med"
        detail = str(it.get("detail", ""))[:300] or "LLM-flagged"
        issues.append(Issue(block, typ, sev, detail, detected_by="llm"))
    return issues


async def llm_verify(
    source_texts: dict[int, str],
    draft_texts: dict[int, str],
    source_lang: str,
    target_lang: str,
    verifier_model: tuple[str, str],
    msg: dict,
    *,
    llm_client,
    knowledge_brief: str = "",
) -> list[Issue]:
    """Best-effort LLM semantic verification → list[Issue] (detected_by='llm')."""
    if not draft_texts:
        return []
    src_model, ref = verifier_model
    messages = _build_messages(source_texts, draft_texts, source_lang, target_lang,
                               knowledge_brief)
    try:
        job = await llm_client.submit_and_wait(
            user_id=msg["user_id"],
            operation="translation",
            model_source=src_model,
            model_ref=str(ref),
            input={
                "messages": messages,
                "reasoning_effort": "none",
                "chat_template_kwargs": {"enable_thinking": False},
            },
            chunking=None,
            job_meta={"verifier": "llm"},
            transient_retry_budget=1,
        )
        if job.status != "completed":
            return []
        text, _, _ = _parse_sdk_response(job)
        return parse_issues(text, set(draft_texts.keys()))
    except Exception as exc:  # best-effort — never fail the chapter on verification
        log.warning("v3 LLM verifier failed (non-fatal): %s", exc)
        return []
