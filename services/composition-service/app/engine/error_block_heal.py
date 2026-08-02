"""Grounded fixes for AUTHOR-MARKED error blocks (atom-edit Phase D).

An error block is a human-authored self-heal `Finding`: the author selects a span of wrong prose
and says what is wrong with it. So this module deliberately does NOT re-run the self-heal
pipeline — it composes its public primitives and skips everything a human finding does not need:

    self-heal:  judge -> locate -> SNAP -> vote -> verify -> rerank -> edit -> merge -> splice -> re-judge
    here:                re-anchor ------------------------> edit ----------------> splice

Why each omission is deliberate, not laziness:
  · judge/vote/verify/rerank exist to decide whether a defect is REAL. The author already
    decided; re-adjudicating their call would be the tool second-guessing its user.
  · `_snap_to_sentence` widens a judge's sloppy quote to a sentence boundary. Applied to a human
    span it would SILENTLY WIDEN a deliberate selection — the author marked those words.
  · the dup-word mechanical merge belongs to a whole-chapter sweep, not a targeted fix.

Design + the sealed decisions: docs/specs/2026-07-26-atom-edit/DESIGN-error-blocks.md
"""

from __future__ import annotations

from app.packer.sanitize import sanitize_guide

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.db.models import ErrorBlock
from app.engine.cowrite import SELECTION_MAX_CHARS, build_selection_messages
from app.llm_budget import max_tokens_for
from app.engine.self_heal import EditProposal, locate_span
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)


# A satellite edit must stay local. Same guard self-heal applies, same reason: an "edit" that
# triples the passage has stopped fixing and started rewriting.
DEFAULT_MAX_EXPANSION = 1.6


# ── fingerprint ────────────────────────────────────────────────────────

def fingerprint(text: str) -> str:
    """Identify the coordinate space a block's offsets were computed in.

    Offsets are meaningful only relative to one exact flattening of the document. If the document
    flattens differently later — most sharply when a doc loses its `_text` block snapshots and
    `tiptap_doc_to_text` falls back to concatenating inline runs — then EVERY stored offset moves
    at once. A cheap hash detects that wholesale shift, so the reader knows to distrust all
    offsets rather than discovering it one corrupted splice at a time.
    """
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# ── re-anchoring (E1) ──────────────────────────────────────────────────

def _all_exact(quote: str, text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(re.escape(quote), text)]


def locate_nearest(
    quote: str, text: str, hint: int, *, hint_trusted: bool,
) -> tuple[int, int] | None:
    """Re-anchor `quote` in `text`, preferring the occurrence nearest `hint`.

    THIS IS THE E1 FIX, and it is a correctness guard, not an optimisation. `locate_span` returns
    the FIRST match. Fiction repeats short lines constantly ("She nodded.", "Nàng gật đầu."), so
    first-match would silently re-anchor a mark made on the third occurrence onto the first — and
    then the co-writer's fix edits a paragraph the author never complained about, reporting
    success the whole way. Nothing downstream could detect it.

    `hint_trusted` says whether `hint` still means anything: it is the caller's fingerprint check.
    When the coordinate space is intact, the nearest occurrence is overwhelmingly the right one.
    When it is NOT, and the quote is ambiguous, we return None so the block ORPHANS — an author
    seeing "we lost track of this mark" is strictly better than a confidently wrong edit.
    """
    if not quote:
        return None
    exact = _all_exact(quote, text)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        if not hint_trusted:
            logger.info(
                "error_block: %d candidates for an ambiguous quote and no trusted hint → orphan",
                len(exact),
            )
            return None
        return min(exact, key=lambda span: abs(span[0] - hint))
    # No exact occurrence: the prose around/inside the span was edited. Fall back to self-heal's
    # fuzzy locator — best-effort, and deliberately only when there is no exact candidate to
    # disambiguate against, so fuzz can never outvote an exact match.
    return locate_span(quote, text)


@dataclass
class AnchoredBlock:
    block: ErrorBlock
    start: int
    end: int
    reanchored: bool = False   # offsets moved → the caller should persist them


@dataclass
class SkippedBlock:
    """A block that produced no proposal, WITH the reason.

    Every skip is reported. Returning fewer proposals than blocks with no explanation is the
    silent-no-op the Frontend-Tool-Contract forbids — the author must never be left wondering
    whether their mark was considered.
    """
    block_id: UUID
    reason: str                # not_located | ambiguous | too_long | edit_failed | edit_expanded
    detail: str = ""


def anchor_blocks(
    blocks: list[ErrorBlock], text: str,
) -> tuple[list[AnchoredBlock], list[SkippedBlock]]:
    """Resolve every block onto `text`, re-anchoring by quote where the offsets have drifted."""
    current = fingerprint(text)
    anchored: list[AnchoredBlock] = []
    skipped: list[SkippedBlock] = []
    for b in blocks:
        trusted = b.source_fingerprint == current
        if trusted and text[b.start_offset:b.end_offset] == b.quote:
            anchored.append(AnchoredBlock(b, b.start_offset, b.end_offset))
            continue
        found = locate_nearest(b.quote, text, b.start_offset, hint_trusted=trusted)
        if found is None:
            skipped.append(SkippedBlock(
                b.id,
                "ambiguous" if len(_all_exact(b.quote, text)) > 1 else "not_located",
                "the marked text could not be found in the current prose",
            ))
            continue
        anchored.append(AnchoredBlock(b, found[0], found[1], reanchored=True))
    return anchored, skipped


# ── overlap merge (E2) ─────────────────────────────────────────────────

@dataclass
class MergedFinding:
    """One or more overlapping marks over a single span.

    self-heal DROPS a finding that overlaps an accepted one (`skip_reason="overlap"`). For human
    marks that is unacceptable: the author marked the same passage twice because it is wrong for
    two reasons, and dropping one silently answers only half the complaint. We merge instead —
    the span union, both notes, one edit that has to satisfy both.
    """
    block_ids: list[UUID]
    start: int
    end: int
    notes: list[str]
    desired: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)

    @property
    def guide(self) -> str:
        parts = [f"Problem: {n}" for n in self.notes]
        parts += [f"Wanted: {d}" for d in self.desired if d]
        return " ".join(parts)


def merge_overlapping(anchored: list[AnchoredBlock]) -> list[MergedFinding]:
    """Union overlapping (or touching) spans into one finding, left to right."""
    out: list[MergedFinding] = []
    for a in sorted(anchored, key=lambda x: (x.start, x.end)):
        if out and a.start < out[-1].end:      # strict overlap; abutting spans stay separate
            last = out[-1]
            last.end = max(last.end, a.end)
            last.block_ids.append(a.block.id)
            last.notes.append(a.block.note)
            if a.block.desired:
                last.desired.append(a.block.desired)
            last.kinds.append(a.block.kind)
            continue
        out.append(MergedFinding(
            block_ids=[a.block.id], start=a.start, end=a.end,
            notes=[a.block.note],
            desired=[a.block.desired] if a.block.desired else [],
            kinds=[a.block.kind],
        ))
    return out


# ── the satellite edit ─────────────────────────────────────────────────

async def _chat(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    system: str, user: str, max_tokens: int,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    temperature: float = 0.3,
) -> str | None:
    """One blocking completion → content, or None on error/non-completion/empty.

    Deliberately NOT self_heal's `_chat`: that one is private (importing it would couple this
    module to another team's internals) and, more importantly, it stamps
    `job_meta.extractor="self_heal"`. Spend from an author-driven fix must not be attributed to
    the autonomous polish pass — `operation` is already overloaded, so the meta is where the two
    are told apart.
    """
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": temperature,
                "max_tokens": max_tokens, **no_thinking_fields(),
            },
            job_meta={"usage_purpose": "error_block_fix", "extractor": "error_block"},
            trace_id=trace_id, cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("error_block fix LLM error: %s", exc)
        return None
    if job.status != "completed":
        logger.info("error_block fix status=%s → degraded", job.status)
        return None
    content = extract_judge_content(job.result)
    return content if content.strip() else None


@dataclass
class ProposalResult:
    proposals: list[EditProposal]
    skipped: list[SkippedBlock]
    reanchored: list[AnchoredBlock]
    grounded: bool
    source_fingerprint: str


async def propose_for_blocks(
    llm: LLMClient,
    blocks: list[ErrorBlock],
    text: str,
    *,
    profile: BookProfile,
    user_id: str,
    model_source: str,
    model_ref: str,
    grounding: str = "",
    max_expansion: float = DEFAULT_MAX_EXPANSION,
    # `None`, not 1200: a signature default cannot see the block it is rewriting.
    edit_max_tokens: int | None = None,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> ProposalResult:
    """Turn author-marked blocks into reviewable `EditProposal`s.

    Never writes. The proposals go to the same human accept/reject gate self-heal's do, and are
    spliced by `apply_block_edits` only once the author accepts.

    `grounded` reports whether canon/lore grounding was actually available. A fix produced with an
    empty pack (knowledge-service down, greenfield Work) is not wrong, but it IS less grounded
    than it looks, and the review card has to say so rather than presenting both identically.
    """
    anchored, skipped = anchor_blocks(blocks, text)
    findings = merge_overlapping(anchored)

    proposals: list[EditProposal] = []
    for f in findings:
        original = text[f.start:f.end]
        if len(original) > SELECTION_MAX_CHARS:
            # Reuse the existing selection ceiling rather than inventing a second limit: past it
            # the satellite premise (edit one passage in isolation) no longer holds.
            skipped.append(SkippedBlock(
                f.block_ids[0], "too_long",
                f"marked span is {len(original)} chars (max {SELECTION_MAX_CHARS})",
            ))
            continue
        guide = (
            # D-INJECTION-COVERAGE / D-COWRITE-GUIDE-UNSANITIZED (2026-07-31): the THIRD
            # site interpolating a raw author guide into a prompt. The other two were
            # fixed by hand this cycle as B2; this one was already flagged by
            # `injection-coverage-lint`, which had never run in CI. Fixing an instance
            # while its detector sits unwired is how a class survives.
            f"{sanitize_guide(f.guide)} Edit ONLY the selected passage; keep a similar length; "
            "add no new events; change nothing the author did not complain about."
        )
        messages = build_selection_messages(
            original, profile, "rewrite", guide=guide, grounding=grounding,
        )
        new = await _chat(
            llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
            system=messages[0]["content"], user=messages[1]["content"],
            max_tokens=edit_max_tokens or max_tokens_for(
                "error_block_heal_edit", target=len(original)),
            trace_id=trace_id, cancel_check=cancel_check,
        )
        if not new:
            skipped.append(SkippedBlock(f.block_ids[0], "edit_failed", "the model returned nothing"))
            continue
        new = new.strip()
        if len(new) > max(40, len(original)) * max_expansion:
            skipped.append(SkippedBlock(
                f.block_ids[0], "edit_expanded",
                f"the fix ran to {len(new)} chars against {len(original)} — rejected as a rewrite",
            ))
            continue
        proposals.append(EditProposal(
            id="", type="error_block", tier="semantic", start=f.start, end=f.end,
            before=original, after=new,
            issue=" · ".join(f.notes), fix=" · ".join(f.desired),
            recommended=True,   # the author asked for this one; it is pre-checked, never auto-applied
        ))

    proposals.sort(key=lambda p: p.start)
    for i, p in enumerate(proposals):
        p.id = f"eb{i}"
    return ProposalResult(
        proposals=proposals,
        skipped=skipped,
        reanchored=[a for a in anchored if a.reanchored],
        grounded=bool(grounding.strip()),
        source_fingerprint=fingerprint(text),
    )


@dataclass
class MigrationPlan:
    """What an accept would do to a preview's marks: which survive, and which are lost.

    Both halves are returned. A caller that only got the survivors could not tell the author
    "two of your five marks could not be found in the accepted text" — and a mark that silently
    disappears is indistinguishable from one that was addressed.
    """
    located: dict[UUID, tuple[int, int]] = field(default_factory=dict)
    orphaned: list[SkippedBlock] = field(default_factory=list)
    fingerprint: str = ""


def plan_accept_migration(blocks: list[ErrorBlock], chapter_text: str) -> MigrationPlan:
    """Re-anchor a compose preview's blocks onto the chapter text they were accepted into.

    The preview and the chapter are DIFFERENT STRINGS — accepting inserts the draft into an
    existing manuscript, so every offset shifts by however much prose precedes it, and the
    surrounding text may differ entirely. Only `quote` survives that transition, which is why it
    is the anchor and the offsets are a hint.

    The stored offsets are still passed as the hint, and `hint_trusted=False` reflects the truth:
    they were computed against the preview, not this chapter. So a quote that appears once
    anchors, and an ambiguous one ORPHANS rather than guessing — the same rule as E1, applied at
    the moment the coordinate space provably changed.
    """
    plan = MigrationPlan(fingerprint=fingerprint(chapter_text))
    for b in blocks:
        found = locate_nearest(b.quote, chapter_text, b.start_offset, hint_trusted=False)
        if found is None:
            plan.orphaned.append(SkippedBlock(
                b.id,
                "ambiguous" if len(_all_exact(b.quote, chapter_text)) > 1 else "not_located",
                "the marked text could not be located in the accepted chapter",
            ))
            continue
        plan.located[b.id] = found
    return plan


def apply_block_edits(
    text: str, proposals: list[EditProposal], accepted_ids: list[str] | None = None,
) -> str:
    """Splice accepted proposals, rightmost-first, SKIPPING any whose anchor no longer matches.

    The `before` check is the difference between this and `self_heal.apply_self_heal_edits`, and
    it is not redundant here. That function is only ever called on the same in-memory chapter its
    proposals were computed from, so its offsets cannot have drifted. Error-block proposals are
    reviewed by a human, which means an arbitrary amount of time — and possibly other edits —
    passes between propose and apply. Without this guard a stale proposal splices its replacement
    over whatever now occupies those offsets. The FE's `applySelfHealEdits` already carries the
    same check, with the same reasoning.
    """
    keep = proposals if accepted_ids is None else [p for p in proposals if p.id in set(accepted_ids)]
    healed = text
    for p in sorted(keep, key=lambda p: p.start, reverse=True):
        if text[p.start:p.end] != p.before:
            logger.info("error_block: proposal %s anchor drifted → skipped, prose left intact", p.id)
            continue
        healed = healed[:p.start] + p.after + healed[p.end:]
    return healed
