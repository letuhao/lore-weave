"""V3 bilingual source→target name extractor (M4d-2a).

The 2-pass cold-start mode (§11.3.C / §12) seeds the glossary from a chapter's
FIRST-pass translation so the second pass renders proper nouns consistently. The
existing extraction pipeline is source-language-only ("Do NOT translate"), so it
cannot produce the source→target pairs seeding needs. This module fills that gap:
given a source chapter and its pass-1 translation, it asks the model for the
RECURRING proper nouns and how each was rendered — yielding ``NamePair`` rows the
writeback (M4d-2b) seeds and the second pass (M4d-2c) enforces.

Best-effort, like the LLM verifier: any failure or malformed output returns ``[]``
— a cold-start chapter must still translate. Pure I/O wrapper; no orchestrator or
V2 coupling (this slice is the producer only).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from ..session_translator import _parse_sdk_response, _lang_name, _SafeFormatMap

log = logging.getLogger(__name__)

# Cap on returned pairs — keeps the seed batch + the pass-2 prompt bounded.
_MAX_PAIRS = 40
_VALID_KINDS = frozenset({"character", "location", "organization", "item", "other"})

_SYSTEM = (
    "You are a bilingual name aligner for {source_lang}→{target_lang} literary "
    "translation. You are given a {source_lang} chapter and its {target_lang} "
    "translation. List the RECURRING proper nouns — characters, places, "
    "organizations, items that appear MORE THAN ONCE — and how each was rendered "
    "in the translation. When a name was rendered inconsistently, pick the most "
    "frequent rendering. Respond with ONLY a JSON array of "
    '{{"source": str, "target": str, "kind": str}}, where "source" is the EXACT '
    "{source_lang} name, \"target\" is its {target_lang} rendering, and \"kind\" "
    "is one of character|location|organization|item|other. Output [] if there are "
    "no recurring proper nouns. No prose, no markdown — only the JSON array."
)


@dataclass
class NamePair:
    """A source→target proper-noun rendering harvested from a pass-1 translation."""
    source: str
    target: str
    kind: str = "other"


def _build_messages(source_text: str, translated_text: str,
                    source_lang: str, target_lang: str) -> list[dict]:
    system = _SYSTEM.format_map(_SafeFormatMap({
        "source_lang": _lang_name(source_lang),
        "target_lang": _lang_name(target_lang),
    }))
    user = (
        f"SOURCE ({_lang_name(source_lang)}):\n{source_text}\n\n"
        f"TRANSLATION ({_lang_name(target_lang)}):\n{translated_text}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_name_pairs(text: str) -> list[NamePair]:
    """Parse the model's JSON array → NamePairs. Tolerant: strips code fences,
    extracts the first JSON array, ignores malformed entries, dedups on source,
    caps at _MAX_PAIRS, never raises."""
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

    pairs: list[NamePair] = []
    seen: set[str] = set()
    for it in data:
        if not isinstance(it, dict):
            continue
        source = str(it.get("source", "")).strip()
        target = str(it.get("target", "")).strip()
        if not source or not target or source in seen:
            continue
        kind = str(it.get("kind", "other")).strip().lower()
        if kind not in _VALID_KINDS:
            kind = "other"
        seen.add(source)
        pairs.append(NamePair(source=source, target=target, kind=kind))
        if len(pairs) >= _MAX_PAIRS:
            break
    return pairs


async def extract_name_pairs(
    source_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
    *,
    llm_client,
    msg: dict,
    model: tuple[str, str] | None = None,
) -> list[NamePair]:
    """Extract recurring source→target proper-noun pairs from a pass-1 translation.

    Best-effort: empty inputs, a non-completed job, or malformed output all yield
    ``[]`` — never raises (a cold-start chapter must still translate). ``model``
    defaults to the translator model on ``msg``.
    """
    if not source_text or not translated_text:
        return []
    src_model, ref = model or (msg["model_source"], msg["model_ref"])
    messages = _build_messages(source_text, translated_text, source_lang, target_lang)
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
            job_meta={"stage": "bilingual_extract"},
            transient_retry_budget=1,
        )
        if job.status != "completed":
            return []
        text, _, _ = _parse_sdk_response(job)
        return parse_name_pairs(text)
    except Exception as exc:  # best-effort — never fail the chapter on extraction
        log.warning("v3 bilingual extractor failed (non-fatal): %s", exc)
        return []


def build_namepair_block(pairs: list[NamePair], max_pairs: int = _MAX_PAIRS) -> str:
    """A "use these EXACT renderings" prompt block from harvested source→target
    pairs — injected into pass 2 of the 2-pass cold-start (M4d-2c) so recurring
    proper nouns render consistently. Sanitized minimally (the pairs are model
    output crossing back into a prompt). Empty when there are no usable pairs."""
    from .knowledge_context import _sanitize
    lines: list[str] = []
    for p in pairs[:max_pairs]:
        src = _sanitize(p.source, 80)
        tgt = _sanitize(p.target, 80)
        if src and tgt:
            lines.append(f"{src} → {tgt}")
    if not lines:
        return ""
    return (
        "NAME CONSISTENCY (cold-start) — these proper nouns recur in this chapter; "
        "render each EXACTLY and consistently as shown:\n" + "\n".join(lines)
    )
