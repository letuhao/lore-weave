"""mui #1c K-detect — coreference detection over the knowledge graph.

One real character is referred to by many names (姜子牙 / 姜尚 / 太公望 / 子牙).
Because the canonical id is name-derived, each becomes a separate KG node +
glossary entity that exact-name dedup can't catch. This module finds likely-
same clusters and proposes them to glossary's merge-candidate inbox (G-cand),
where a human confirms via the R5 merge endpoint. NOTHING merges here — we only
detect + propose (L1: human-confirms every merge).

Signals (spec §3.1, no embeddings — dev KG has 0 entity vectors):
  • name        — shared alias, substring containment, honorific-stripped
                  equality, normalized edit-distance (reuses canonicalize).
  • structural  — Jaccard over RELATES_TO neighbor sets (catches 太公望↔姜子牙:
                  co-occur in the same scenes, share no name characters).

Design (spec §7c): a PURE scorer (block_and_score / score_pair / cluster_pairs)
that is unit-tested in isolation, an async orchestrator (build_candidates /
detect_from_records) tested with fakes, and a THIN Neo4j loader covered by the
phase-6 live-smoke. LLM-verify is config-gated (on by default) and degrades to
score-only per-pair on any LLM failure — human-confirm is the real gate, so a
verify hiccup must never silently drop a scored candidate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from itertools import combinations

from app.db.neo4j_helpers import CypherSession, run_read
from app.db.neo4j_repos.canonical import canonicalize_entity_name

logger = logging.getLogger(__name__)

__all__ = [
    "CorefEntity",
    "CandidatePair",
    "DetectResult",
    "score_pair",
    "block_and_score",
    "cluster_pairs",
    "build_candidates",
    "detect_from_records",
    "detect_and_propose",
    "load_anchored_kinds",
]


# ── records + results ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CorefEntity:
    """One glossary-anchored KG entity, the unit the scorer compares.

    `entity_id` is the GLOSSARY entity id (what the merge-candidate members
    must be — the propose endpoint validates glossary membership). `neighbor_ids`
    are the KG node ids of 1-hop RELATES_TO neighbours (the structural signal).
    """

    entity_id: str
    name: str
    aliases: tuple[str, ...] = ()
    mention_count: int = 0
    neighbor_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CandidatePair:
    a_id: str
    b_id: str
    score: float
    name_score: float
    struct_score: float
    shared_aliases: tuple[str, ...] = ()
    shared_neighbors: int = 0


@dataclass
class DetectResult:
    clusters_found: int = 0
    proposed: int = 0
    suppressed: int = 0
    skipped: int = 0
    candidates: list[dict] = field(default_factory=list)


# ── name + structural signals (pure) ──────────────────────────────────────────


def _name_set(e: CorefEntity) -> set[str]:
    """Canonicalized name + aliases (drop empties)."""
    out = {canonicalize_entity_name(e.name)}
    for a in e.aliases:
        out.add(canonicalize_entity_name(a))
    out.discard("")
    return out


def _levenshtein_ratio(a: str, b: str) -> float:
    """1 - edit_distance/max_len, in [0,1]. Cheap iterative DP."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


def _name_signal(a: CorefEntity, b: CorefEntity) -> tuple[float, tuple[str, ...]]:
    """Strongest name relationship between two entities, with the shared tokens."""
    sa, sb = _name_set(a), _name_set(b)
    shared = tuple(sorted(sa & sb))
    if shared:
        return 1.0, shared  # exact alias/name overlap (honorific-normalized)

    best = 0.0
    for x in sa:
        for y in sb:
            # substring containment (子牙 ⊂ 姜子牙); require len>=2 so a single
            # shared character doesn't masquerade as containment.
            if len(x) >= 2 and len(y) >= 2 and (x in y or y in x):
                best = max(best, 0.85)
            else:
                best = max(best, _levenshtein_ratio(x, y))
    return best, ()


def _structural_signal(a: CorefEntity, b: CorefEntity) -> tuple[float, int]:
    """Jaccard over RELATES_TO neighbour sets + the shared-neighbour count."""
    if not a.neighbor_ids or not b.neighbor_ids:
        return 0.0, 0
    inter = a.neighbor_ids & b.neighbor_ids
    union = a.neighbor_ids | b.neighbor_ids
    return (len(inter) / len(union) if union else 0.0), len(inter)


def score_pair(
    a: CorefEntity, b: CorefEntity, *, name_weight: float, struct_weight: float
) -> CandidatePair:
    name_score, shared_aliases = _name_signal(a, b)
    struct_score, shared_neighbors = _structural_signal(a, b)
    total = name_weight * name_score + struct_weight * struct_score
    total = max(0.0, min(1.0, total))
    return CandidatePair(
        a_id=a.entity_id, b_id=b.entity_id, score=total,
        name_score=name_score, struct_score=struct_score,
        shared_aliases=shared_aliases, shared_neighbors=shared_neighbors,
    )


# ── blocking + scoring (pure) ──────────────────────────────────────────────────


def _char_bigrams(s: str) -> set[str]:
    s = canonicalize_entity_name(s)
    return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()


def block_and_score(
    entities: list[CorefEntity],
    *,
    score_floor: float,
    name_weight: float,
    struct_weight: float,
    max_pairs: int,
    max_bucket: int,
) -> list[CandidatePair]:
    """Bound O(n²): only score pairs that share a blocking signal — an exact
    name/alias token, a RELATES_TO neighbour, or a name char-bigram. Buckets
    larger than `max_bucket` (common-char explosion) are dropped. Returns
    candidate pairs scoring ≥ floor, highest first, capped at `max_pairs`.
    """
    by_idx = {i: e for i, e in enumerate(entities)}
    buckets: dict[str, list[int]] = {}

    def add(key: str, idx: int) -> None:
        buckets.setdefault(key, []).append(idx)

    for i, e in by_idx.items():
        for tok in _name_set(e):
            add(f"n:{tok}", i)
        for nb in e.neighbor_ids:
            add(f"r:{nb}", i)
        for bg in _char_bigrams(e.name):
            add(f"b:{bg}", i)
        for a in e.aliases:
            for bg in _char_bigrams(a):
                add(f"b:{bg}", i)

    # Candidate index-pairs that co-occur in at least one (non-oversized) bucket.
    seen_pairs: set[tuple[int, int]] = set()
    for members in buckets.values():
        if len(members) < 2 or len(members) > max_bucket:
            continue
        for i, j in combinations(sorted(set(members)), 2):
            seen_pairs.add((i, j))

    scored: list[CandidatePair] = []
    for i, j in seen_pairs:
        pair = score_pair(
            by_idx[i], by_idx[j], name_weight=name_weight, struct_weight=struct_weight
        )
        if pair.score >= score_floor:
            scored.append(pair)

    # Deterministic order: score desc, then ids for stable tie-break.
    scored.sort(key=lambda p: (-p.score, p.a_id, p.b_id))
    return scored[:max_pairs]


def cluster_pairs(pairs: list[CandidatePair]) -> list[list[str]]:
    """Union-find the confirmed pairs into clusters of ≥2 entity ids
    (transitive: A-B + B-C ⇒ {A,B,C}). Member order is sorted for stability."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    for p in pairs:
        union(p.a_id, p.b_id)

    groups: dict[str, list[str]] = {}
    for node in parent:
        groups.setdefault(find(node), []).append(node)
    return [sorted(g) for g in groups.values() if len(g) >= 2]


# ── orchestration (async; testable with fakes) ─────────────────────────────────

_VERIFY_SYSTEM = (
    "You judge whether two character/entity references denote the SAME entity in "
    "a Chinese novel. Consider naming conventions: a person may be referenced by "
    "名 (given name), 字 (courtesy name), 号 (art name), or title — all the same "
    "person (e.g. 姜子牙 = 太公望 = 子牙). BUT beware two DIFFERENT people who "
    "merely share a name or title. Reply ONLY JSON: "
    '{"same": true|false, "confidence": 0.0-1.0, "rationale": "<short>"}.'
)


def _verify_user_prompt(a: CorefEntity, b: CorefEntity, pair: CandidatePair) -> str:
    return (
        f"Entity A: name={a.name!r} aliases={list(a.aliases)}\n"
        f"Entity B: name={b.name!r} aliases={list(b.aliases)}\n"
        f"Shared aliases/names: {list(pair.shared_aliases)}\n"
        f"Shared graph neighbours (co-occurrence): {pair.shared_neighbors}\n"
        f"name_score={pair.name_score:.2f} structural_score={pair.struct_score:.2f}\n"
        "Are A and B the same entity?"
    )


async def _verify_pair(
    llm, *, user_id: str, model: str, model_source: str,
    a: CorefEntity, b: CorefEntity, pair: CandidatePair,
) -> bool | None:
    """LLM verdict for one pair. True/False, or None when the verdict could not
    be obtained (caller treats None as 'keep' — degrade to score-only)."""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=model_source,
            model_ref=model,
            input={
                "messages": [
                    {"role": "system", "content": _VERIFY_SYSTEM},
                    {"role": "user", "content": _verify_user_prompt(a, b, pair)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
                "max_tokens": 200,
            },
            job_meta={"extractor": "coref_verify"},
            transient_retry_budget=1,
        )
    except Exception as exc:  # noqa: BLE001 — degrade to score-only on any LLM error
        logger.warning("coref verify call failed (keeping pair): %s", exc)
        return None
    if getattr(job, "status", None) != "completed":
        logger.warning("coref verify job status=%s (keeping pair)", getattr(job, "status", None))
        return None
    payload = job.result or {}
    messages = payload.get("messages") or []
    content = ""
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        content = messages[0].get("content", "") or ""
    try:
        verdict = json.loads(content)
        return _coerce_same(verdict.get("same"))
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        logger.warning("coref verify parse failed (keeping pair): %s body=%r", exc, content[:200])
        return None


def _coerce_same(v) -> bool:
    """Robustly read the judge's `same` verdict. LLMs don't always emit a JSON
    bool — `bool("no")` is True (non-empty string), which would INVERT a reject.
    Map strings/numerics to the right boolean (review-impl MED)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1", "same", "y")
    return False


async def build_candidates(
    records: list[CorefEntity],
    *,
    llm,
    user_id: str,
    score_floor: float,
    name_weight: float,
    struct_weight: float,
    max_pairs: int,
    max_bucket: int,
    min_mentions: int,
    llm_verify: bool,
    judge_model: str,
    judge_user: str,
    judge_model_source: str,
) -> list[dict]:
    """Score → (optionally) LLM-verify → cluster → assemble propose-payload dicts.

    Pure aside from the optional LLM hop, so it is exercised directly with a fake
    `llm`. Returns the `candidates` list the glossary propose endpoint expects.
    """
    pool = [r for r in records if r.mention_count >= min_mentions]
    if len(pool) < 2:
        return []
    by_id = {r.entity_id: r for r in pool}

    pairs = block_and_score(
        pool, score_floor=score_floor, name_weight=name_weight,
        struct_weight=struct_weight, max_pairs=max_pairs, max_bucket=max_bucket,
    )

    verify_on = llm_verify and bool(judge_model) and llm is not None
    kept: list[CandidatePair] = []
    for p in pairs:
        if verify_on:
            verdict = await _verify_pair(
                llm, user_id=judge_user or user_id, model=judge_model,
                model_source=judge_model_source,
                a=by_id[p.a_id], b=by_id[p.b_id], pair=p,
            )
            if verdict is False:  # explicit reject — drop. None (couldn't verify) → keep.
                continue
        kept.append(p)

    pair_by_key = {(p.a_id, p.b_id): p for p in kept}
    candidates: list[dict] = []
    for cluster in cluster_pairs(kept):
        winner = max(cluster, key=lambda gid: by_id[gid].mention_count)
        # Aggregate evidence from the kept pairs that lie inside this cluster.
        cset = set(cluster)
        ev_pairs = [
            p for (x, y), p in pair_by_key.items() if x in cset and y in cset
        ]
        best = max((p.score for p in ev_pairs), default=0.0)
        shared_aliases = sorted({a for p in ev_pairs for a in p.shared_aliases})
        names = ", ".join(by_id[g].name for g in cluster)
        candidates.append(
            {
                "member_entity_ids": cluster,
                "suggested_winner_entity_id": winner,
                "score": round(best, 4),
                "evidence": [
                    {
                        "a": p.a_id, "b": p.b_id, "score": round(p.score, 4),
                        "name_score": round(p.name_score, 4),
                        "structural_score": round(p.struct_score, 4),
                        "shared_neighbors": p.shared_neighbors,
                    }
                    for p in ev_pairs
                ],
                "rationale": (
                    f"coref cluster of {len(cluster)} ({names}); "
                    f"shared names/aliases={shared_aliases}; "
                    f"{'LLM-verified' if verify_on else 'score-only'}"
                ),
            }
        )
    return candidates


async def _propose_and_tally(glossary, book_id, candidates: list[dict]) -> DetectResult:
    """Propose candidates to glossary and tally per-candidate outcomes."""
    result = DetectResult(clusters_found=len(candidates), candidates=candidates)
    if not candidates:
        return result
    resp = await glossary.propose_merge_candidates(book_id, candidates=candidates)
    for item in (resp or {}).get("results", []) if isinstance(resp, dict) else []:
        status = item.get("status")
        if status == "proposed":
            result.proposed += 1
        elif status == "suppressed":
            result.suppressed += 1
        else:
            result.skipped += 1
    return result


async def detect_from_records(
    records: list[CorefEntity],
    *,
    glossary,
    llm,
    book_id,
    user_id: str,
    **cfg,
) -> DetectResult:
    """build_candidates → propose to glossary. Tested with fake glossary+llm.

    NOTE: `records` MUST be a single kind — block_and_score is kind-agnostic, so
    mixing kinds would cluster a character with a co-occurring location and the
    propose endpoint would reject the whole mixed cluster (review-impl HIGH-1).
    `detect_and_propose` enforces this by building candidates per kind.
    """
    candidates = await build_candidates(records, llm=llm, user_id=user_id, **cfg)
    return await _propose_and_tally(glossary, book_id, candidates)


# ── Neo4j loader (thin; live-smoke covered) ────────────────────────────────────

_LOAD_CYPHER = """
MATCH (e:Entity {user_id: $user_id, kind: $kind})
WHERE e.project_id = $project_id AND e.glossary_entity_id IS NOT NULL
OPTIONAL MATCH (e)-[r:RELATES_TO]-(n:Entity)
  WHERE r.user_id = $user_id AND r.valid_until IS NULL
WITH e, collect(DISTINCT n.id) AS neighbor_ids
RETURN e.glossary_entity_id AS gid, e.name AS name, e.aliases AS aliases,
       e.mention_count AS mentions, neighbor_ids AS neighbor_ids
ORDER BY mentions DESC
LIMIT $limit
"""


_KINDS_CYPHER = """
MATCH (e:Entity {user_id: $user_id})
WHERE e.project_id = $project_id AND e.glossary_entity_id IS NOT NULL
RETURN DISTINCT e.kind AS kind
"""


async def load_anchored_kinds(
    session: CypherSession, *, user_id: str, project_id: str
) -> list[str]:
    """Distinct kinds of anchored entities in the project — the default scope
    when the detect request omits an explicit `kinds` list."""
    result = await run_read(session, _KINDS_CYPHER, user_id=user_id, project_id=project_id)
    kinds: list[str] = []
    async for row in result:
        k = row.get("kind")
        if k:
            kinds.append(str(k))
    return kinds


async def _load_coref_entities(
    session: CypherSession, *, user_id: str, project_id: str, kind: str, limit: int
) -> list[CorefEntity]:
    result = await run_read(
        session, _LOAD_CYPHER,
        user_id=user_id, project_id=project_id, kind=kind, limit=limit,
    )
    out: list[CorefEntity] = []
    async for row in result:
        gid = row.get("gid")
        if not gid:
            continue
        out.append(
            CorefEntity(
                entity_id=str(gid),
                name=row.get("name") or "",
                aliases=tuple(row.get("aliases") or ()),
                mention_count=int(row.get("mentions") or 0),
                neighbor_ids=frozenset(str(n) for n in (row.get("neighbor_ids") or []) if n),
            )
        )
    return out


async def detect_and_propose(
    *,
    session: CypherSession,
    glossary,
    llm,
    user_id: str,
    project_id: str,
    book_id,
    kinds: list[str],
    score_floor: float,
    name_weight: float,
    struct_weight: float,
    max_pairs: int,
    max_bucket: int,
    max_candidates_per_kind: int,
    min_mentions: int,
    llm_verify: bool,
    judge_model: str,
    judge_user: str,
    judge_model_source: str,
) -> DetectResult:
    """Load anchored entities per kind from Neo4j, score+verify+cluster, and
    propose merge candidates to glossary. Neo4j-coupled — live-smoke verified.

    Candidates are built PER KIND (then proposed together): block_and_score is
    kind-agnostic, so scoring a combined multi-kind set would cluster entities
    of different kinds (they share neighbours/bigrams) into a mixed cluster the
    glossary propose endpoint rejects wholesale — silently losing the valid
    same-kind sub-pairs inside it (review-impl HIGH-1)."""
    all_candidates: list[dict] = []
    for kind in kinds:
        records = await _load_coref_entities(
            session, user_id=user_id, project_id=project_id,
            kind=kind, limit=max_candidates_per_kind,
        )
        all_candidates += await build_candidates(
            records, llm=llm, user_id=user_id,
            score_floor=score_floor, name_weight=name_weight, struct_weight=struct_weight,
            max_pairs=max_pairs, max_bucket=max_bucket, min_mentions=min_mentions,
            llm_verify=llm_verify, judge_model=judge_model, judge_user=judge_user,
            judge_model_source=judge_model_source,
        )
    return await _propose_and_tally(glossary, book_id, all_candidates)
