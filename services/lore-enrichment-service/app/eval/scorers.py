"""Deterministic sub-score scorers for the enrichment eval (RAID C15).

Four of the five eval sub-scores are DETERMINISTIC rule scorers (no LLM, no
network) so they are reproducible on a fixture and never a false-green:

  * ``schema``       — is the proposal game-ready / normalized? every required
    dimension present + non-empty Chinese content, valid lifecycle vocab.
  * ``canon``        — does the C12 canon-verify annotation show NO unresolved
    contradiction? (M2 consistency; a flagged contradiction lowers the score).
  * ``anachronism``  — does the Chinese content avoid post-Shang/Zhou (商周/封神)
    intrusions? reuses the C12 anachronism marker table over the content.
  * ``provenance``   — does EVERY fact carry origin + confidence(<1.0) +
    grounding refs? (H0: enriched, never canon).

The fifth sub-score (``usefulness`` / cultural-fidelity) is SUBJECTIVE and is
produced by the judge-ENSEMBLE (see ``judge_usefulness.py``), not here.

Each scorer returns a float in ``[0, 100]`` (the climate-eval convention) plus
a list of human-readable issue strings for the scorecard. Scores are rounded to
one decimal to match the climate baseline-diff tolerance semantics.

H0 (eval-specific): a proposal is scored as ``source_type='enriched'`` data.
``provenance`` scorer treats ``confidence >= 1.0`` or ``origin == 'glossary'``
as the WORST possible provenance (it would mean an enriched proposal leaked into
canon shape) — never a high score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ScorableProposal",
    "SubScores",
    "score_schema",
    "score_canon",
    "score_anachronism",
    "score_provenance",
    "REQUIRED_DIMENSIONS",
    "ANACHRONISM_MARKERS",
    "CANON_ORIGIN",
]

# ── locked vocab (mirror C6 / OPEN_QUESTIONS_LOCKED demo set) ──────────────────
#: The 3 REQUIRED Chinese-labelled dimensions + 2 optional (English-labelled) per
#: the C6 DimensionSpec. A schema-valid LOCATION proposal fills all 5; the 3
#: required carry the heaviest schema weight.
REQUIRED_DIMENSIONS: tuple[str, ...] = ("历史", "地理", "文化")
OPTIONAL_DIMENSIONS: tuple[str, ...] = ("features", "inhabitants")
ALL_DIMENSIONS: tuple[str, ...] = REQUIRED_DIMENSIONS + OPTIONAL_DIMENSIONS

#: The authored-canon origin (H0). An enriched proposal must NEVER carry it.
CANON_ORIGIN: str = "glossary"

#: Legal lifecycle vocabulary (mirror C2 review_status CHECK).
_LIFECYCLE_VOCAB: frozenset[str] = frozenset(
    {"proposed", "author_reviewing", "approved", "promoted", "rejected"}
)

# ── anachronism marker table (mirror C12 curated CONCEPT markers) ──────────────
#: Out-of-era CONCEPT markers for the locked 商周/封神 frame. Curated COMPOUND
#: terms (NOT bare single chars — C12 lesson: bare 电 false-positived on
#: era-appropriate 雷电/电光). Each entry is a post-Shang/Zhou intrusion: later
#: dynasties, modern tech, foreign faiths, modern science. Operates on CHINESE
#: content (CJK importability), not romanized text.
ANACHRONISM_MARKERS: tuple[str, ...] = (
    # modern technology / science
    "电灯", "电力", "电脑", "计算机", "互联网", "手机", "汽车", "火车",
    "飞机", "电视", "电话", "雷达", "卫星", "原子", "基因", "细胞",
    "量子", "激光", "蒸汽机", "火药",  # 火药 is post-Han; out of Shang/Zhou frame
    # later dynasties / regimes (post-Zhou)
    "秦朝", "汉朝", "唐朝", "宋朝", "元朝", "明朝", "清朝", "民国",
    "皇帝陛下下旨",  # imperial-era bureaucratic phrasing
    # foreign faiths / later religions (anachronistic to 封神 frame)
    "佛教", "和尚", "寺院", "基督", "天主", "伊斯兰", "清真",
    # modern abstractions
    "民主", "共和国", "资本主义", "社会主义", "公司",
)


@dataclass(frozen=True)
class ScorableProposal:
    """The normalized, source-agnostic shape the deterministic scorers consume.

    Built from a persisted ``ProposalRow`` (real DB) OR a replay fixture entry
    — the scorers never touch a DB or network, so the same code path scores a
    fixture and a live run identically.

    ``dimensions`` maps the C6 dimension LABEL (历史/地理/文化/features/inhabitants)
    to its generated Chinese content. ``canon_verify`` is the C12 annotation
    block (``provenance_json['canon_verify']``) if present. ``source_refs`` is
    the grounding citation list. H0 markers (origin/confidence/pending) are
    carried verbatim so the provenance scorer can detect a canon leak.
    """

    name: str
    entity_kind: str
    dimensions: dict[str, str]
    origin: str
    technique: str
    confidence: float
    review_status: str
    pending_validation: bool
    source_refs: list[Any] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    canon_verify: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_provenance_json(
        cls,
        *,
        name: str,
        entity_kind: str,
        origin: str,
        technique: str,
        confidence: float,
        review_status: str,
        provenance_json: dict[str, Any],
        source_refs_json: list[Any],
    ) -> "ScorableProposal":
        """Build from a persisted proposal's columns (C14 shape).

        The generated dimensions live under ``provenance_json['dimensions']``
        (C14 ``build_proposal_fields``); the C12 verify annotation under
        ``provenance_json['canon_verify']``. ``pending_validation`` is True for
        any non-terminal enriched proposal (review_status != promoted/rejected).
        """
        prov = provenance_json or {}
        dims = prov.get("dimensions") or {}
        if not isinstance(dims, dict):
            dims = {}
        return cls(
            name=name,
            entity_kind=entity_kind,
            dimensions={str(k): str(v) for k, v in dims.items()},
            origin=origin,
            technique=technique,
            confidence=float(confidence),
            review_status=review_status,
            pending_validation=review_status not in ("promoted", "rejected"),
            source_refs=list(source_refs_json or []),
            provenance=prov,
            canon_verify=prov.get("canon_verify") or {},
        )


@dataclass(frozen=True)
class SubScores:
    """The five sub-scores for one proposal (each 0..100) + issue notes."""

    schema: float
    canon: float
    anachronism: float
    provenance: float
    usefulness: float
    issues: list[str] = field(default_factory=list)


# ── helpers ────────────────────────────────────────────────────────────────────

_CJK_RE = re.compile(r"[一-鿿]")
_LATIN_RUN_RE = re.compile(r"[A-Za-z]{4,}")


def _cjk_ratio(text: str) -> float:
    """Fraction of non-whitespace chars that are CJK. 0.0 for empty."""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(1 for c in chars if _CJK_RE.match(c)) / len(chars)


# ── 1. schema ───────────────────────────────────────────────────────────────────

def score_schema(
    p: ScorableProposal,
    *,
    required_dims: tuple[str, ...] = REQUIRED_DIMENSIONS,
    optional_dims: tuple[str, ...] = OPTIONAL_DIMENSIONS,
    require_cjk: bool = True,
) -> tuple[float, list[str]]:
    """Game-ready normalization: required dims present + non-empty, valid
    lifecycle vocab.

    De-bias (LE-PROD slice D): the dimension set + the language-faithfulness check
    are PARAMETERS, not hardcoded. ``required_dims``/``optional_dims`` default to the
    Fengshen LOCATION set (no regression); the runner passes the proposal's KIND dims
    (profile-localized). ``require_cjk`` defaults True (zh demo); the runner sets it
    from the book language (a non-Chinese book is NOT penalized for non-CJK content).

    Scoring (0..100):
      * required dimensions present + non-empty (+ language-faithful when required):
        60 pts split evenly.
      * optional dimensions present + non-empty: 25 pts split evenly.
      * lifecycle vocab valid: 15 pts.
    """
    issues: list[str] = []
    pts = 0.0

    req_slice = 60.0 / len(required_dims) if required_dims else 0.0
    for dim in required_dims:
        content = (p.dimensions.get(dim) or "").strip()
        if not content:
            issues.append(f"schema: required dimension {dim!r} missing/empty")
            continue
        # A non-language-faithful value (e.g. English where Chinese was required) is
        # a normalization failure — but ONLY checked when the book language demands a
        # script (require_cjk). A non-Chinese book skips this check entirely.
        if require_cjk and _LATIN_RUN_RE.search(content) and _cjk_ratio(content) < 0.5:
            issues.append(f"schema: required dimension {dim!r} not Chinese-faithful")
            pts += req_slice * 0.5  # partial credit — present but malformed
        else:
            pts += req_slice

    opt_slice = 25.0 / len(optional_dims) if optional_dims else 0.0
    for dim in optional_dims:
        content = (p.dimensions.get(dim) or "").strip()
        if content:
            pts += opt_slice
        else:
            issues.append(f"schema: optional dimension {dim!r} missing")

    if p.review_status in _LIFECYCLE_VOCAB:
        pts += 15.0
    else:
        issues.append(f"schema: invalid review_status {p.review_status!r}")

    return round(min(100.0, pts), 1), issues


# ── 2. canon (M2 consistency, NOT correctness) ──────────────────────────────────

def score_canon(p: ScorableProposal) -> tuple[float, list[str]]:
    """No contradiction vs KG/glossary (M2). Reads the C12 canon-verify
    annotation: a CONTRADICTION flag lowers the score; INJECTION flags also
    lower it (tampered content is not canon-consistent). A DEGRADED verify
    (KG down) is NOT a free pass — it is treated as partial uncertainty
    (caps at 70) so a down KG can never produce a false-green canon score.

    Scoring (0..100):
      * start at 100.
      * each CONTRADICTION flag: -40 (severity-weighted: HIGH -40, else -20).
      * each INJECTION flag: -30.
      * verify_degraded (KG unavailable, could not confirm consistency): cap 70.
      * no canon_verify annotation at all: cap 50 (could not assess M2 → not green).
    """
    issues: list[str] = []
    cv = p.canon_verify or {}
    if not cv:
        issues.append("canon: no canon_verify annotation — M2 not assessed (capped)")
        return 50.0, issues

    score = 100.0
    flags = cv.get("flags") or []
    if not isinstance(flags, list):
        flags = []
    for f in flags:
        if not isinstance(f, dict):
            continue
        kind = str(f.get("kind", "")).upper()
        sev = str(f.get("severity", "")).upper()
        if kind == "CONTRADICTION":
            score -= 40.0 if sev == "HIGH" else 20.0
            issues.append(f"canon: contradiction flag ({sev or 'n/a'}) — {f.get('evidence', '')[:80]}")
        elif kind == "INJECTION":
            score -= 30.0
            issues.append("canon: injection flag — tampered content is not canon-consistent")

    if cv.get("verify_degraded"):
        issues.append("canon: verify degraded (KG unavailable) — capped, never auto-pass")
        score = min(score, 70.0)

    return round(max(0.0, score), 1), issues


# ── 3. anachronism (商周/封神 frame, operates on Chinese) ────────────────────────

def score_anachronism(
    p: ScorableProposal, *, markers: tuple[str, ...] = ANACHRONISM_MARKERS
) -> tuple[float, list[str]]:
    """No out-of-era intrusions in the content. Scans every dimension value for the
    book's out-of-era CONCEPT markers.

    De-bias (LE-PROD slice D): ``markers`` is a PARAMETER, defaulting to the Fengshen
    商周/封神 table (no regression). The runner passes the per-book ``profile``
    markers — so an EMPTY marker set (a sci-fi / modern / non-Fengshen book) means the
    anachronism check is OFF (score 100), never penalizing era-appropriate content.

    Scoring (0..100): 100 minus 25 per distinct marker hit (floored at 0)."""
    issues: list[str] = []
    hits: set[str] = set()
    for dim, content in p.dimensions.items():
        for marker in markers:
            if marker in (content or ""):
                hits.add(marker)
                issues.append(f"anachronism: {marker!r} in dimension {dim!r}")
    score = 100.0 - 25.0 * len(hits)
    return round(max(0.0, score), 1), issues


# ── 4. provenance (H0: every fact origin/confidence/grounding) ──────────────────

def score_provenance(p: ScorableProposal) -> tuple[float, list[str]]:
    """Every fact carries origin + confidence(<1.0) + grounding ref (H0).

    H0 LEAK DETECTION (the worst-case): if the proposal looks like authored
    canon (origin == 'glossary' OR confidence >= 1.0 while in a non-promoted
    state), provenance is scored 0 — an enriched proposal masquerading as canon
    is the single worst provenance failure, never a high score.

    Scoring (0..100):
      * origin is enriched (not glossary): 30 pts.
      * confidence strictly 0 < c < 1.0: 30 pts.
      * at least one grounding source_ref present: 25 pts.
      * provenance dict records technique + model_ref key: 15 pts.
    """
    issues: list[str] = []

    # H0 leak: enriched proposal wearing canon clothes → worst score.
    if p.origin == CANON_ORIGIN or p.origin.startswith(CANON_ORIGIN + ":"):
        return 0.0, ["provenance: H0 LEAK — origin is authored-canon ('glossary')"]
    if p.confidence >= 1.0 and p.review_status != "promoted":
        return 0.0, ["provenance: H0 LEAK — enriched proposal has canon confidence (>=1.0)"]

    pts = 0.0
    if p.origin and p.origin != CANON_ORIGIN:
        pts += 30.0
    else:
        issues.append("provenance: missing/canon origin")

    if 0.0 < p.confidence < 1.0:
        pts += 30.0
    else:
        issues.append(f"provenance: confidence {p.confidence} out of enriched range (0,1)")

    if p.source_refs:
        pts += 25.0
    else:
        issues.append("provenance: no grounding source_refs (unprovenanced fact)")

    prov = p.provenance or {}
    if prov.get("technique") and ("model_ref" in prov):
        pts += 15.0
    else:
        issues.append("provenance: provenance dict missing technique/model_ref")

    return round(min(100.0, pts), 1), issues
