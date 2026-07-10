"""C26 (dị bản M3) — derivative critic dimension: override enforcement.

A new critic check that ACTIVATES ONLY for a DERIVATIVE Work (one carrying
`source_work_id` — surfaced as a non-empty derivative context). It LOADS the active
`entity_override[]` + the inherited BASE entities through C25's resolution path
(`build_derivative_context` + the base `present` lens) — REUSE, never a re-merge —
and verifies the generated scene HONOURS the overrides:

  • OVERRIDE SLIP — an overridden entity field that reverts to its canon/base value
    in the passage (the override "slipped"). Emits a STRUCTURED finding naming the
    entity + field + expected (the override) vs found (the reverted base value) so
    the writer / regeneration loop can act on it.
  • DELTA INTERNAL CONSISTENCY — the scene must not contradict an established delta
    fact. An overridden field that also added a `canon_rule` (the derivative's
    declared truth) but reverts to its base value contradicts that delta rule →
    a `delta_inconsistency` finding.

DETERMINISTIC + AI-FREE: composition has NO AI imports (LOCKED). The detection is a
pure text comparison of the passage against the resolved override vs base values —
no LLM call, fully unit-testable. The cross-space (knowledge-id → glossary-anchor)
reconcile reuses C25's `_resolve_override_anchors` (the same normalization seam the
packer applies), so the override target matches the base present item's key.

SCOPE (LOCKED M0): entity-field + added canon-rule overrides only. Relationship /
event overrides are deferred.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

from app.packer.merge import OVERRIDE_CANON_FIELD, _norm_name, _present_key
from app.packer.pack import build_derivative_context, _resolve_override_anchors

logger = logging.getLogger(__name__)

# C26 GATE — how many forced regenerations a stubborn override slip may trigger
# before the gate fails OPEN to the human (surfaces the finding + stops blocking
# accept). Bounds a false-positive (a slip the detector wrongly flags can't loop
# forever) AND a genuinely-stubborn model (after N tries the human decides). The
# count is tracked per-job across `/critique` calls (the existing regenerate→
# re-critique loop is the producer of each attempt).
REGEN_ATTEMPT_CAP = 3

# The present-item bio field is `summary` (glossary short_description). An override
# may author the bio as `summary` OR `description` (the C24 wizard writes
# `description`) — reconcile both to the one base field, mirroring
# `apply_entity_overrides` so a field-NAME drift doesn't silently skip enforcement.
# PRECEDENCE MUST MATCH C25 (merge.apply_entity_overrides): apply `description`
# first then `summary`, so `summary` WINS when an override carries both — otherwise
# the critic would treat a different value as "expected" than the packer grounded the
# drafter on (a two-sources-of-truth drift; adversary M1). Last in this order wins.
_BIO_OVERRIDE_FIELDS = ("description", "summary")


def _override_bio(fields: dict[str, Any]) -> str | None:
    """The override's bio value, reconciled EXACTLY as C25's apply_entity_overrides:
    `description` then `summary` (summary wins if both present). None when the
    override touches no bio field."""
    bio: str | None = None
    for fkey in _BIO_OVERRIDE_FIELDS:
        if fkey in fields and fields[fkey]:
            bio = str(fields[fkey])
    return bio


# An ASCII word char (Python's `\w` is Unicode-aware and ALSO matches CJK
# ideographs — that is exactly the FIX 1 bug: a `(?<!\w)…(?!\w)` boundary against
# a CJK value flanked by CJK chars NEVER matched, so the gate could not fire for
# Chinese prose). We restrict the word-boundary notion to ASCII so the English
# precision (don't match "king" inside "kingdom") is kept, while a CJK value — a
# script with NO word separators — is matched by containment.
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]")
# A bio value lifted from the glossary often carries trailing/leading sentence
# punctuation (e.g. `前世…重生复仇。`) that the generated prose won't replicate
# verbatim (it ends the clause with `，` or nothing). Trim word-irrelevant edge
# punctuation/whitespace from the VALUE before matching so a `。`-terminated bio
# still matches the same phrase mid-sentence (FIX 1 — "tolerant of surrounding
# punctuation"). We only strip non-word, non-CJK chars so an entity's actual name
# characters are never eaten.
_CJK = (
    "一-鿿㐀-䶿豈-﫿"  # CJK Unified + Ext-A + Compat
    "぀-ヿ"                              # Hiragana + Katakana
    "가-힯"                              # Hangul
)
_EDGE_PUNCT = re.compile(rf"^[^\w{_CJK}]+|[^\w{_CJK}]+$")


def _ascii_word_char(ch: str) -> bool:
    return bool(ch) and _ASCII_WORD.match(ch) is not None


def _trim_edges(v: str) -> str:
    """Strip leading/trailing punctuation/whitespace that is neither an ASCII word
    char nor a CJK/kana/hangul char — so a bio's trailing `。`/`，` doesn't defeat a
    containment match against the same phrase in prose."""
    return _EDGE_PUNCT.sub("", v)


def _phrase_occurs(passage_fold: str, value: Any) -> bool:
    """Whether the folded `value` occurs in `passage_fold` as a standalone phrase,
    correct for BOTH scripts (FIX 1 — CJK-safe):

    • ASCII edges keep WORD-BOUNDARY precision — a value whose first/last char is an
      ASCII word char must not be split out of a larger ASCII word ("king" inside
      "kingdom" → False; D-C26-CRITIC-FN edge 2 preserved).
    • CJK (and any non-ASCII-word) edges use CONTAINMENT — a script with no word
      separators can't carry an ASCII boundary, so `少年天才` flanked by Chinese chars
      now matches (the gate fires for Chinese).
    • Edge sentence-punctuation on the VALUE is trimmed first (a `。`-terminated bio
      matches the same phrase ending in `，`).

    Implemented as a containment scan: for each occurrence, reject ONLY when the
    boundary would split an ASCII word (value edge is ASCII-word AND the adjacent
    passage char is ASCII-word). Empty value → False."""
    v = _trim_edges(_norm_name(value))
    if not v:
        return False
    start_ascii = _ascii_word_char(v[0])
    end_ascii = _ascii_word_char(v[-1])
    idx = passage_fold.find(v)
    while idx != -1:
        before = passage_fold[idx - 1] if idx > 0 else ""
        after_pos = idx + len(v)
        after = passage_fold[after_pos] if after_pos < len(passage_fold) else ""
        # A boundary only matters where BOTH the value edge AND the neighbour are
        # ASCII word chars (i.e. we'd be slicing a larger ASCII token). CJK edges
        # never trip this, so containment wins for CJK.
        left_ok = not (start_ascii and _ascii_word_char(before))
        right_ok = not (end_ascii and _ascii_word_char(after))
        if left_ok and right_ok:
            return True
        idx = passage_fold.find(v, idx + 1)
    return False


def _strip_phrase(passage_fold: str, value: str) -> str:
    """Blank out every standalone occurrence of `value` in `passage_fold` (same
    boundary rule as `_phrase_occurs`), so a residual test can detect whether the
    override appears OUTSIDE the reverted base phrase. CJK-safe (containment),
    edge-punctuation-tolerant (same trim as `_phrase_occurs`)."""
    v = _trim_edges(_norm_name(value))
    if not v:
        return passage_fold
    start_ascii = _ascii_word_char(v[0])
    end_ascii = _ascii_word_char(v[-1])
    out: list[str] = []
    i = 0
    n = len(passage_fold)
    while i < n:
        if passage_fold.startswith(v, i):
            before = passage_fold[i - 1] if i > 0 else ""
            after_pos = i + len(v)
            after = passage_fold[after_pos] if after_pos < n else ""
            left_ok = not (start_ascii and _ascii_word_char(before))
            right_ok = not (end_ascii and _ascii_word_char(after))
            if left_ok and right_ok:
                out.append(" ")
                i = after_pos
                continue
        out.append(passage_fold[i])
        i += 1
    return "".join(out)


def _override_honoured(passage_fold: str, override_bio: str, base_bio: str) -> bool:
    """Whether the OVERRIDE value is genuinely asserted in the passage — NOT merely
    present as a substring of the BASE value the scene reverted to (D-C26-CRITIC-FN
    edge 2). When the override is a substring of the base ("young" ⊂ "a young man",
    or `少年` ⊂ `少年天才`), a naive `override in passage` is True whenever the base
    value appears, hiding the slip. We strip every base-value occurrence out FIRST,
    then test whether the override still occurs standalone — so the override only
    counts as honoured when it appears OUTSIDE the reverted base phrase. CJK-safe."""
    if not _norm_name(override_bio):
        return False
    residual = _strip_phrase(passage_fold, base_bio)
    return _phrase_occurs(residual, override_bio)


def detect_override_findings(
    passage: str,
    overrides: list[Any] | None,
    base_present: list[dict[str, Any]],
    *,
    target_anchor: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Pure detector — compare the generated `passage` against each override's
    declared value vs the inherited BASE value of the same entity.

    An OVERRIDE SLIP fires when, for an overridden bio field, the BASE/canon value
    appears in the passage AND the OVERRIDDEN value does NOT — the field reverted.
    A DELTA INCONSISTENCY additionally fires when that same override declared a
    `canon_rule` (an established delta fact) that the reverted scene contradicts.

    A non-overridden (inherited) entity is NEVER flagged — only overridden fields
    are enforced (M0). Returns a list of structured findings; [] for a compliant
    scene / no overrides.
    """
    if not overrides:
        return []
    anchor_map = target_anchor or {}
    passage_fold = _norm_name(passage)

    # Index the inherited base entities by their reconciled present-key
    # (`id:<glossary_anchor>` / `name:<folded>`) — the SAME axis C25's merge uses.
    base_by_key: dict[str, dict[str, Any]] = {}
    for item in base_present:
        base_by_key[_present_key(item)] = item

    findings: list[dict[str, Any]] = []
    for ov in overrides:
        tid = getattr(ov, "target_entity_id", None)
        if tid is None:
            continue
        # Resolve the override target → its base present item. The override target is
        # a knowledge node id; the base item keys on the glossary anchor — match on
        # BOTH the raw target and its resolved anchor (C25's reconcile, reused).
        item = base_by_key.get(f"id:{tid}")
        if item is None:
            resolved = anchor_map.get(str(tid))
            if resolved:
                item = base_by_key.get(f"id:{resolved}")
        if item is None:
            continue  # the override names an entity not in the base present set → skip
        entity_id = item.get("entity_id") or str(tid)
        fields = getattr(ov, "overridden_fields", None) or {}
        base_bio = item.get("summary")

        # Determine the overridden bio value (description/summary reconciled with the
        # SAME precedence C25 applies — summary wins if both; adversary M1).
        override_bio = _override_bio(fields)

        # Does the canon/base value revert into the passage? (word-bounded — edge 2).
        # Computed once: it is the shared signal for BOTH the bio slip and the
        # (decoupled) delta-rule contradiction below.
        base_reverted = bool(base_bio) and _phrase_occurs(passage_fold, base_bio)

        if override_bio is not None and base_bio:
            # Slip: the base value reverted AND the override value is NOT genuinely
            # asserted (not merely a substring of the reverted base phrase — edge 2).
            if base_reverted and not _override_honoured(passage_fold, override_bio, base_bio):
                findings.append({
                    "kind": "override_slip",
                    "entity_id": entity_id,
                    "name": item.get("name") or "",
                    "field": "description",
                    "expected": override_bio,
                    "found": str(base_bio),
                })

        # Delta internal consistency (D-C26-CRITIC-FN edge 3) — DECOUPLED from the
        # bio slip: an override that declared a `canon_rule` (the derivative's stated
        # delta truth) is contradicted whenever the entity's BASE value reverts into
        # the scene, EVEN when the override carried no bio field to slip (canon-rule-
        # only override). It fires on `base_reverted` alone, not on a bio slip.
        rule = fields.get(OVERRIDE_CANON_FIELD)
        if rule and base_reverted:
            findings.append({
                "kind": "delta_inconsistency",
                "entity_id": entity_id,
                "name": item.get("name") or "",
                "rule": str(rule),
                "why": "the scene reverts an overridden entity to its base value, "
                       "contradicting an established delta canon rule",
            })

    return findings


def evaluate_override_gate(
    findings: list[dict[str, Any]], *, prior_attempts: int,
) -> dict[str, Any]:
    """C26 GATE decision over the derivative critic findings — turn the (previously
    advisory) findings into an accept/regenerate verdict with a bounded attempt cap.

    A slip OR a delta_inconsistency is a FAIL (`needs_regeneration`) that blocks
    accept and feeds the existing regenerate→re-critique loop. `prior_attempts` is
    the count of earlier slipped critiques on this job; THIS critique counts as one
    more. Once the cap is reached the gate fails OPEN to the human (`regen_exhausted`
    — surface the finding, stop forcing regeneration) so a stubborn or false-positive
    slip can never loop forever. A clean scene neither gates nor advances the counter
    (only failing critiques burn an attempt).
    """
    has_fail = any(
        f.get("kind") in ("override_slip", "delta_inconsistency") for f in findings
    )
    if not has_fail:
        return {
            "needs_regeneration": False,
            "regen_exhausted": False,
            "regen_attempts": prior_attempts,
            "regen_cap": REGEN_ATTEMPT_CAP,
        }
    attempts = prior_attempts + 1
    exhausted = prior_attempts >= REGEN_ATTEMPT_CAP
    return {
        "needs_regeneration": not exhausted,
        "regen_exhausted": exhausted,
        "regen_attempts": attempts,
        "regen_cap": REGEN_ATTEMPT_CAP,
    }


async def critique_overrides(
    *,
    work: Any,
    user_id: UUID,
    passage: str,
    bearer: str,
    works_repo: Any,
    derivatives_repo: Any,
    glossary: Any,
    knowledge: Any,
    book: Any,
    _base_present_fn: Any = None,
) -> list[dict[str, Any]]:
    """The wired derivative critic dimension — orchestrates the enforcement at the
    critique call site.

    ACTIVATION (LOCKED): only a DERIVATIVE Work fires. We resolve the derivative
    context via C25's `build_derivative_context` (REUSE — the same path that gives
    the packer its overrides + base project). A NON-derivative Work yields an empty
    context (no source project) → we return [] WITHOUT querying the base lens.

    For a derivative, we read the inherited BASE `present` entities from the source
    project (the same lens the packer merges), reconcile the override targets →
    glossary anchors (C25's `_resolve_override_anchors`), and run the pure detector.

    Degrade-safe: any resolution/lens failure → [] (the critic is advisory; it must
    NEVER block accept — CC4 parity).
    """
    try:
        deriv = await build_derivative_context(
            work, works_repo=works_repo,
            derivatives_repo=derivatives_repo,
        )
    except Exception:  # noqa: BLE001 — context resolution degrades the dimension
        logger.warning("critique_overrides: derivative context resolve failed", exc_info=True)
        return []

    # ACTIVATION GATE — a canon Work (no source project, no overrides) never fires;
    # the base lens is NOT queried.
    if deriv.source_project_id is None or not deriv.overrides:
        return []

    # D-C26-CRITIC-FN edge 1 — scope the BASE lens to the packer's actually-grounded
    # set, not a broad project-wide query: pass the OVERRIDE TARGET ids as the
    # present-entity scope (these are exactly the entities the dimension enforces, and
    # the same ids C25's packer pins into the present window). gather_present resolves
    # each id → its present item, so the base bio we compare against is the one the
    # drafter was actually grounded on (a broad query=`""` could surface a DIFFERENT
    # present row for the same entity, hiding/falsely flagging a slip).
    target_ids = [
        getattr(ov, "target_entity_id", None) for ov in deriv.overrides
        if getattr(ov, "target_entity_id", None) is not None
    ]
    # FIX 4 — the override TARGET anchors (glossary ids, post-C24). The base lens
    # pins on these AND guarantees they appear in the present set even when the broad
    # semantic read excludes them (see `_gather_base_present`). Without this the
    # explicit pin degraded to the broad query="" path: get_entity(<anchor>) 404s on a
    # glossary id, so the target's BIO never surfaced via the pin — leaving detection
    # to a semantic query that returns nothing for an empty query (the live-found hole).
    target_anchors = [str(t) for t in target_ids]

    base_fn = _base_present_fn or _gather_base_present
    try:
        base_present = await base_fn(
            glossary=glossary, knowledge=knowledge, book=book,
            book_id=getattr(work, "book_id", None), user_id=user_id,
            project_id=deriv.source_project_id, bearer=bearer,
            present_entity_ids=target_ids, query="",
            override_target_anchors=target_anchors,
        )
    except Exception:  # noqa: BLE001 — base lens failure degrades the dimension
        logger.warning("critique_overrides: base present lens failed", exc_info=True)
        return []

    try:
        target_anchor = await _resolve_override_anchors(knowledge, bearer, deriv.overrides)
    except Exception:  # noqa: BLE001 — anchor resolve degrades to raw-target matching
        logger.warning("critique_overrides: anchor resolve failed", exc_info=True)
        target_anchor = {}

    return detect_override_findings(
        passage, deriv.overrides, base_present, target_anchor=target_anchor)


async def _gather_base_present(
    *, glossary: Any, knowledge: Any, book: Any,
    book_id: Any, user_id: UUID, project_id: UUID, bearer: str,
    present_entity_ids: list[Any] | None = None, query: str = "",
    override_target_anchors: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Read the inherited BASE `present` entities from the source project — the SAME
    lens (and the same SCOPE) C25's packer merges (reuse). D-C26-CRITIC-FN edge 1:
    the caller forwards the override TARGET ids as `present_entity_ids` so the base
    set mirrors the packer's actually-grounded cast (pinned present items) rather than
    a broad project-wide query that could surface a different row for the same entity.

    FIX 4 — the override target's BIO must be present for the detector to compare it.
    gather_present sources bios from the SEMANTIC lens (vector-ranked, project-scoped)
    or, when that yields nothing, the book-scoped glossary FTS. But a glossary anchor
    pinned via `present_entity_ids` only adds RELATIONS (knowledge.get_entity keys on a
    KNOWLEDGE node id — a glossary anchor 404s there), NOT the bio. So if the broad
    semantic read excludes an override target (an empty query returns NOTHING — the
    live-found hole), its bio never surfaces and the slip is invisible. We GUARANTEE the
    override targets are present by augmenting from the same book-scoped glossary FTS the
    packer falls back to (`select_for_context`), keyed on the stable glossary `entity_id`
    — exactly the anchor the override target and `_present_key` reconcile on."""
    from app.packer.lenses import gather_present

    present, _seen = await gather_present(
        glossary, knowledge, book_id=book_id, user_id=user_id,
        project_id=project_id, bearer=bearer, query=query,
        present_entity_ids=present_entity_ids or [],
    )

    # Augment any MISSING override target from the book-scoped glossary (id-space-safe:
    # both the override target and the present item reconcile on the glossary anchor).
    want = {str(a) for a in (override_target_anchors or []) if a}
    if want and book_id is not None:
        have = {str(p.get("entity_id")) for p in present if p.get("entity_id")}
        missing = want - have
        if missing:
            try:
                extras = await glossary.select_for_context(book_id, user_id, "")
            except Exception:  # noqa: BLE001 — augmentation is best-effort
                logger.warning("base-present augment (select_for_context) failed", exc_info=True)
                extras = []
            for e in extras:
                eid = str(e.get("entity_id") or "")
                if eid in missing:
                    present.append({
                        "entity_id": eid,
                        "name": e.get("cached_name") or "",
                        "summary": e.get("short_description") or "",
                        "relations": [],
                    })
    return present
