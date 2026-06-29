"""Chapter stitch pass (LOOM chapter-assembly-modes, B3).

The `per_scene` + stitch path: once a chapter's scenes are drafted, ONE LLM pass
merges the consecutive scene drafts into a single seamless chapter — removing
repeated introductions / echoed descriptions and smoothing transitions, while
changing NO plot facts. Degrade-safe: any failure returns "" so the caller falls
back to the raw concatenation (never blocks). The stitched output is re-checked
by the chapter-level canon guard (a rewrite can re-introduce a gone character).

W-STITCH (§17.2, R2.7) layers five seam-quality deltas on top of that single
pass, all of them ADVISORY (the stitch only ever *proposes* — it never silently
rewrites committed prose, and any failure still degrades to the raw concat):

  1. **Cross-scene repetition signal** — a pure, in-code n-gram (word-shingle)
     overlap detector run over *adjacent scene boundaries* (each seam's tail↔head
     region). Findings are fed into the revise prompt so the model de-dups the
     specific echoed imagery/phrasing — NOT a per-pair LLM call.
  2. **Dial-respect** — the `voice`/`style_directive` profile is threaded through
     with an explicit over-stitching guard (§17.4): smooth seams, do NOT flatten
     voice or deliberate motifs.
  3. **≤2-scene over-resolve** — a local-window heuristic flags a scene that
     closed a beat the very next scene must still do.
  4. **Overlapping-window** — boundaries are analysed pairwise (each interior
     scene participates in two seams), keeping every join in a coherent local span
     (the §17.1 lost-in-the-middle rationale).
  5. **Eval-gate** — `tests/unit/test_stitch_motif.py` proves seams improve
     (repetition reduced) WITHOUT flattening (deliberate motif/voice preserved).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.engine.select import _NO_THINK
from app.packer.profile import BookProfile, style_directive

logger = logging.getLogger(__name__)

# ── W-STITCH (§17.2, R2.7) tunables — kept local to this module so the stitch
# behaviour stays self-contained (no new config.py knob). ──
_SHINGLE_K = 4          # word-shingle length for cross-boundary repetition
_BOUNDARY_CHARS = 600   # chars of each scene's tail/head examined at a seam
_MAX_FINDINGS = 6       # cap injected findings so the revise prompt stays focused
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)  # unicode-aware word tokens

# Lightweight lexicons for the ≤2-scene over-resolve heuristic (§17.2 "fixes
# over-resolving"): a scene that CLOSES a beat the next scene must still do.
_RESOLVE_CUES = (
    "finally forgave", "forgave", "the feud was over", "was over at last",
    "made peace", "reconciled", "let it go", "found closure", "at peace",
    "settled it", "put it to rest", "was over",
)
_REOPEN_CUES = (
    "could not forgive", "couldn't forgive", "still gnawed", "still festered",
    "unresolved", "not over", "wasn't over", "still raged", "still burned",
    "could not let", "couldn't let",
)


@dataclass(frozen=True)
class _RepetitionFinding:
    """A repeated phrase detected at the seam between two adjacent scenes.
    `left_scene`/`right_scene` are 1-based (matching the [SCENE n] prompt blocks)."""

    left_scene: int
    right_scene: int
    phrase: str


@dataclass(frozen=True)
class _OverResolveFinding:
    """A scene that resolved a beat its adjacent successor re-opens (1-based)."""

    left_scene: int
    right_scene: int


def boundary_windows(n: int) -> list[tuple[int, int]]:
    """Overlapping adjacent-scene windows (0-based) for ``n`` scenes. Each seam is
    ``(i, i+1)`` so every interior scene appears in two windows (with its
    predecessor and its successor) — the overlapping-window pass of R2.7."""
    return [(i, i + 1) for i in range(max(0, n - 1))]


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _shingles(words: list[str], k: int) -> set[tuple[str, ...]]:
    if len(words) < k:
        return set()
    return {tuple(words[i:i + k]) for i in range(len(words) - k + 1)}


def repetition_findings(
    scene_drafts: list[str], shingle_k: int = _SHINGLE_K,
) -> list[_RepetitionFinding]:
    """Cross-scene repetition signal (§17.2 dedup). For each ADJACENT boundary,
    compare the tail region of the left scene against the head region of the right
    scene via word k-shingles; a shared shingle ⇒ echoed imagery/phrasing at that
    seam. Pure + in-code (no LLM). Only the seam regions are compared, so a phrase
    that merely recurs elsewhere in two scenes is NOT flagged — we target the
    re-introduction/echo that shows up where two scenes are joined."""
    drafts = [d for d in scene_drafts if d and d.strip()]
    out: list[_RepetitionFinding] = []
    seen: set[str] = set()
    for left, right in boundary_windows(len(drafts)):
        tail = _words(drafts[left][-_BOUNDARY_CHARS:])
        head = _words(drafts[right][:_BOUNDARY_CHARS])
        shared = _shingles(tail, shingle_k) & _shingles(head, shingle_k)
        if not shared:
            continue
        # Pick the longest contiguous shared run as the representative phrase.
        phrase = _longest_run_phrase(tail, head, shared, shingle_k)
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        out.append(_RepetitionFinding(left + 1, right + 1, phrase))
        if len(out) >= _MAX_FINDINGS:
            break
    return out


def _longest_run_phrase(
    tail: list[str], head: list[str], shared: set[tuple[str, ...]], k: int,
) -> str:
    """Reconstruct the longest contiguous phrase in `head` whose k-shingles are all
    in `shared` (a human-readable fragment for the revise prompt)."""
    shingle_set = shared
    best: list[str] = []
    i = 0
    while i <= len(head) - k:
        if tuple(head[i:i + k]) in shingle_set:
            run = list(head[i:i + k])
            j = i + 1
            while j <= len(head) - k and tuple(head[j:j + k]) in shingle_set:
                run.append(head[j + k - 1])
                j += 1
            if len(run) > len(best):
                best = run
            i = j
        else:
            i += 1
    return " ".join(best)


def detect_over_resolve(scene_drafts: list[str]) -> list[_OverResolveFinding]:
    """≤2-scene over-resolve detection (§17.2). Heuristic: a scene whose tail
    voices a beat-completion cue while the adjacent successor's head re-opens the
    same beat ⇒ the earlier scene over-resolved what the next still needs to do.
    Scoped strictly to the local (i, i+1) window — never cross-chapter."""
    drafts = [d for d in scene_drafts if d and d.strip()]
    out: list[_OverResolveFinding] = []
    for left, right in boundary_windows(len(drafts)):
        tail = drafts[left][-_BOUNDARY_CHARS:].lower()
        head = drafts[right][:_BOUNDARY_CHARS].lower()
        if any(c in tail for c in _RESOLVE_CUES) and any(c in head for c in _REOPEN_CUES):
            out.append(_OverResolveFinding(left + 1, right + 1))
    return out


def cap_scene_drafts(drafts: list[str], max_chars: int) -> tuple[list[str], int]:
    """MED-3 input cap — char-cap with head+tail keep. Returns (kept, elided).

    Keeps the EARLIEST + LATEST scenes intact (opening + closing continuity, where
    stitching matters most) and elides the middle when the concatenation exceeds
    `max_chars`. Always keeps at least the first + last scene (so a very long
    chapter still stitches its ends rather than degrading entirely). `elided` is
    logged by the caller — no silent truncation."""
    if sum(len(d) for d in drafts) <= max_chars or len(drafts) <= 2:
        return list(drafts), 0
    head = [drafts[0]]
    tail = [drafts[-1]]
    budget = max_chars - len(drafts[0]) - len(drafts[-1])
    i, j = 1, len(drafts) - 2
    take_head = True
    while i <= j and budget > 0:
        d = drafts[i] if take_head else drafts[j]
        if len(d) > budget:
            break
        budget -= len(d)
        if take_head:
            head.append(d)
            i += 1
        else:
            tail.append(d)
            j -= 1
        take_head = not take_head
    kept = head + list(reversed(tail))
    return kept, len(drafts) - len(kept)


def _format_seam_notes(
    rep: list[_RepetitionFinding], over: list[_OverResolveFinding],
) -> str:
    """Render the in-code seam findings into an advisory block prepended to the
    revise prompt. Empty string when nothing was detected (no wasted tokens)."""
    if not rep and not over:
        return ""
    lines = [
        "SEAM NOTES (advisory — apply only where it improves flow; preserve voice "
        "and deliberate motifs):"
    ]
    for f in rep:
        lines.append(
            f"- Scenes {f.left_scene}→{f.right_scene} repeat/echo this phrasing at "
            f'their join: "{f.phrase}". De-duplicate it across the boundary, keeping '
            "one natural occurrence."
        )
    for o in over:
        lines.append(
            f"- Scene {o.left_scene} appears to over-resolve a beat that scene "
            f"{o.right_scene} still needs to play out. Soften scene {o.left_scene}'s "
            "closure so the next scene's continuation reads naturally."
        )
    return "\n".join(lines) + "\n\n"


async def stitch_chapter(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    scene_drafts: list[str], chapter_intent: str, profile: BookProfile,
    max_tokens: int, max_input_chars: int,
    reasoning_effort: str | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[str, str | None]:
    """Merge the chapter's scene drafts into one seamless chapter. Returns
    ``(stitched_prose, finish_reason)`` — prose is "" on empty input / LLM failure
    / empty output (the caller degrades to the raw concatenation); finish_reason is
    the model's stop reason ("length" ⇒ the stitch hit the cap; None when degraded
    or unreported — D-COMP-TRUNCATION-SURFACING)."""
    drafts = [d for d in scene_drafts if d and d.strip()]
    if not drafts:
        return "", None
    kept, elided = cap_scene_drafts(drafts, max_input_chars)
    if elided:
        logger.info("stitch input capped: kept %d/%d scene drafts (elided %d middle)",
                    len(kept), len(drafts), elided)
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5 — chapter-scoped density/pace
    # Dial-respect / over-stitching guard (§17.4): the stitch smooths SEAMS only —
    # it must preserve the book's voice + deliberate motifs, never homogenize prose.
    dial_guard = (
        " Smooth only the seams between scenes; preserve the established voice, "
        "tone, and any deliberate repeated imagery or motif — do NOT flatten or "
        "homogenize the prose, and do not shorten or blandify scenes that are "
        "already distinct."
    )
    system = (
        "You are a fiction editor merging consecutive scene drafts of ONE chapter "
        "into a single seamless chapter. Remove repeated introductions and echoed "
        "descriptions, smooth the transitions between scenes, and keep one "
        "continuous narrative. Change NO plot facts, events, or dialogue meaning — "
        "only restructure and de-duplicate the prose. Output ONLY the chapter prose."
        + lang + voice + style + dial_guard
    )
    # Cross-scene repetition + over-resolve signals computed over `kept` so the
    # 1-based scene indices line up with the [SCENE n] blocks below. Advisory: a
    # found echo is *pointed at*, not auto-deleted (§14.6 / §17.2 stitch proposes).
    rep = repetition_findings(kept)
    over = detect_over_resolve(kept)
    seam_notes = _format_seam_notes(rep, over)
    intent = (chapter_intent or "").strip()
    user = (
        (f"Chapter intent: {intent}\n\n" if intent else "")
        + seam_notes
        + "\n\n".join(f"[SCENE {i + 1}]\n{d}" for i, d in enumerate(kept))
    )
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.3, "max_tokens": max_tokens,
                "response_format": {"type": "text"},
                **({"reasoning_effort": reasoning_effort} if reasoning_effort is not None else _NO_THINK),
            },
            job_meta={"usage_purpose": "prose_stitch", "extractor": "stitch_chapter"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("stitch LLM error: %s → degrade to raw concat", exc)
        return "", None
    if job.status != "completed":
        logger.info("stitch status=%s → degrade to raw concat", job.status)
        return "", None
    text = extract_judge_content(job.result)
    if not text.strip():
        return "", None
    return text, (job.result or {}).get("finish_reason")
