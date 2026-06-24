"""Assembly (§2.4) + the A1 isolation chokepoint (§2.5/§12).

`assert_project_scoped` is the **A1 chokepoint**: knowledge `timeline`/`entities`
widen to ALL of a user's projects when `project_id` is omitted, so the packer
MUST assert it is present+non-null BEFORE any lens read (don't trust the endpoint
default). `build_segments` turns a LensBundle into budget Segments — sanitising
`<lore>` and `<guide>` (untrusted, §13 SEC3) as it goes — and `segments_to_blocks`
+ `render` produce the structured prompt.
"""

from __future__ import annotations

from uuid import UUID

from app.packer import budget as B
from app.packer.budget import Segment
from app.packer.lenses import LensBundle
from app.packer.sanitize import sanitize_guide, sanitize_lore

# Canonical block order for rendering (§2.4).
_BLOCK_ORDER = ["canon", "present", "threads", "beat", "open_promises", "recent", "memory", "lore", "guide"]


def assert_project_scoped(project_id: UUID | None) -> None:
    """A1 chokepoint — refuse to pack without a project scope (else knowledge
    lenses widen cross-project, §12.1). Raises ValueError when None."""
    if project_id is None:
        raise ValueError("A1 isolation: project_id is required on every lens call")


def assert_derivative_scoped(project_id: UUID | None, source_project_id: UUID | None) -> None:
    """C25 GUARD — a DERIVATIVE pack grounds on TWO partitions (G2): the delta
    (`project_id`, the derivative's own project) and the base (`source_project_id`,
    the source's project, read ≤ branch_point). BOTH must be present+non-null — a
    null on either would widen the corresponding knowledge read to ALL of the
    user's projects (the cross-project grounding leak C23's NOT-NULL guard exists
    for). Raises ValueError when either is None (refuse to proceed)."""
    if project_id is None or source_project_id is None:
        raise ValueError(
            "C25 derivative scoping: both the delta project_id and the base "
            "source_project_id are required for a derivative pack",
        )


def build_segments(
    bundle: LensBundle, *, guide: str = "", pinned_lore_ids: set[str] | None = None,
) -> list[Segment]:
    """Flatten a LensBundle (+ author guide) into prioritised, sanitised
    Segments for the budget pass.

    T3.4: a lore hit whose `source_id` is in `pinned_lore_ids` is emitted
    `protected=True` so the budget keeps it even under a tight trim (present/canon
    are already protected, so a pin there needs no change here)."""
    segs: list[Segment] = []
    _pinned_lore = pinned_lore_ids or set()

    for r in bundle.canon:
        segs.append(Segment("canon", r.text, B.PRIO_CANON, protected=True))

    # C25 — added canon-rule scope from entity overrides (M0 dị bản override
    # scope = entity fields + added canon rules). These are the derivative's
    # divergence constraints; render them in the <canon> block like inherited
    # rules. Sanitised: the rule text is author-authored but capped/neutralised
    # for delimiter safety, same posture as <lore>/<guide>.
    for rule in bundle.extra_canon:
        txt = sanitize_lore(rule)
        if txt:
            segs.append(Segment("canon", txt, B.PRIO_CANON, protected=True))

    for p in bundle.present:
        rel = ("; ".join(p.get("relations") or [])).strip()
        line = f'{p.get("name", "")}: {p.get("summary", "")}'.strip(": ").strip()
        if rel:
            line = f"{line} [relations: {rel}]" if line else f"[relations: {rel}]"
        if line:
            segs.append(Segment("present", line, B.PRIO_PRESENT_CORE, protected=True))

    beat = bundle.beat or {}
    beat_line = " | ".join(
        x for x in [
            f'beat={beat.get("beat_role")}' if beat.get("beat_role") else "",
            f'goal={beat.get("goal")}' if beat.get("goal") else "",
            f'synopsis={beat.get("synopsis")}' if beat.get("synopsis") else "",
        ] if x
    )
    if beat_line:
        segs.append(Segment("beat", beat_line, B.PRIO_BEAT, protected=True))
    for pl in bundle.planned:
        segs.append(Segment("beat", f'planned: {pl.get("title", "")}: {pl.get("synopsis", "")}',
                            B.PRIO_THREADS_STALE))

    # FD-1 S3 — open promises re-injected (F2) so the model carries + pays them.
    # Protected (a constraint, like beat) but capped upstream so a large ledger
    # can't crowd canon/beat.
    for p in bundle.open_promises:
        # SEC3 — the summary is LLM-detector output DERIVED FROM untrusted book
        # prose, so neutralize it like <lore>/<guide> (else a crafted passage →
        # detector summary → forged `</open_promises>` delimiter / injection on
        # re-injection). review-impl MED#1.
        summary = sanitize_lore((p.get("summary") or "").strip())
        if summary:
            segs.append(Segment("open_promises", f'{p.get("kind", "promise")}: {summary}',
                                B.PRIO_PROMISES, protected=True))

    for t in bundle.threads:
        segs.append(Segment("threads", f'{t.get("kind", "")} {t.get("label", "")} → {t.get("to", "")}'.strip(),
                            B.PRIO_THREADS_STALE))

    # S2 — the compressed state summary (older story-so-far) renders FIRST in the
    # `recent` block, BEFORE the immediate prose (older→immediate reading order).
    # Protected: it's the condensed prior state, high value.
    if bundle.state_summary:
        segs.append(Segment("recent", bundle.state_summary, B.PRIO_RECENT_IMMEDIATE, protected=True))

    # L3 recent: the LAST paragraph is the immediate-preceding prose (protected);
    # earlier paragraphs are droppable.
    n = len(bundle.recent)
    for i, para in enumerate(bundle.recent):
        is_last = i == n - 1
        segs.append(Segment(
            "recent", para,
            B.PRIO_RECENT_IMMEDIATE if is_last else B.PRIO_RECENT_OLDER,
            protected=is_last,
        ))

    for e in bundle.timeline:
        line = f'{e.get("title", "")}: {e.get("summary", "")}'.strip(": ").strip()
        if line:
            segs.append(Segment("memory", line, B.PRIO_TIMELINE_OLDER))

    for h in bundle.lore:
        txt = sanitize_lore(h.get("text", ""))
        if txt:
            # T3.4 — a pinned lore source is protected so a tight budget keeps it.
            pinned = str(h.get("source_id")) in _pinned_lore
            segs.append(Segment("lore", txt, B.PRIO_LORE, protected=pinned))

    if guide:
        segs.append(Segment("guide", sanitize_guide(guide), B.PRIO_CANON, protected=True))

    return segs


def segments_to_blocks(kept: list[Segment]) -> dict[str, str]:
    """Group kept segments back into `{block: joined text}`."""
    blocks: dict[str, list[str]] = {}
    for s in kept:
        blocks.setdefault(s.block, []).append(s.text)
    return {b: "\n".join(texts) for b, texts in blocks.items()}


def render(blocks: dict[str, str]) -> str:
    """Render blocks in canonical order as `<block>…</block>` (M6 draft prompt)."""
    out: list[str] = []
    for b in _BLOCK_ORDER:
        if blocks.get(b):
            out.append(f"<{b}>\n{blocks[b]}\n</{b}>")
    return "\n".join(out)
