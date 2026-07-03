"""B1(4) — cross-partition entity unification (the "world-core" query-time pass).

`kg_world_query` / `kg_multi_query` return a **forest of per-book islands**: a
node's `id` folds `project_id` into its hash (`canonical.py:entity_canonical_id`),
so the same real entity — "Alice" in the canon book and "Alice" in a side-story —
hashes to two different node ids and there is no edge between them. This module
adds a **query-time unification pass in application code** that recognizes the
same real entity across ≥2 of a user's owned partitions and proposes
confidence-scored **clusters** + inferred `SAME_AS` **bridge edges**, so the agent
gets a *connected* cross-book graph for synthesis.

Design invariants (spec `docs/specs/2026-07-03-kg-cross-partition-merge.md`):
  * **Propose, don't assert (D2).** No destructive `merge_entities`, no stored id,
    no migration. Bridges are tagged `inferred=true` + a confidence band so the
    agent (and a future human-confirm, T3) can judge.
  * **Ephemeral, no writes (D3).** The pass reads per-partition and clusters in
    Python; it NEVER issues a cross-partition Cypher and NEVER mutates Neo4j.
  * **Kind-gated (EC-M3).** Never unify across `kind` (character↔location), even at
    a perfect name match — bucket by kind first.
  * **Cross-partition only (EC-M10).** A bridge is emitted only between two
    entities in DIFFERENT partitions; two same-named entities in ONE book are
    `merge_entities` territory, not a bridge.
  * **Default-off byte-identical (EC-M5).** `unify="off"` never calls this module,
    so existing consumers see the unchanged forest.

T0 ships the **lexical** signal (canonicalize_entity_name + alias overlap). T1
adds the semantic signal (in-Python pairwise cosine + Q1=b on-demand embed).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from loreweave_extraction.canonical import canonicalize_entity_name

from app.db.neo4j_helpers import CypherSession, run_read
from app.db.neo4j_repos.relations import Subgraph

__all__ = [
    "UnifySeed",
    "cluster_seeds",
    "load_seed_details",
    "unify_subgraph",
]

# ── thresholds + caps (module constants; conservative, tunable) ───────
# Per-method bands (EC-M17 / D8): lexical and (T1) semantic scores are NOT on the
# same scale, so each method carries its own (low, high) pair. A pair MATCHES
# (unions) at score ≥ τ_low; a cluster's band is "same" at ≥ τ_high else "likely".
UNIFY_LEX_TAU_HIGH = 1.0    # exact canonical-name match → "same"
UNIFY_LEX_TAU_LOW = 0.5     # alias-overlap ≥ this → "likely" candidate

UNIFY_MAX_CLUSTERS = 100        # EC-M11 — cap emitted clusters (confidence-desc, EC-M21)
UNIFY_MAX_CLUSTER_SIZE = 16     # EC-M7 — a cluster spanning >16 partitions is suspect

# EC-M20 — generic names over-cluster lexically. For a "common" normalized key,
# name-equality ALONE is not enough: we require an additional shared alias. A key is
# common if it is very short OR in this small stoplist (canonicalize strips most
# honorifics, but role-words survive). Tunable; a fuller stoplist is a T1 refinement.
_COMMON_NAME_MIN_LEN = 3
_COMMON_NAME_STOPLIST = frozenset(
    {
        "master", "lord", "king", "queen", "emperor", "empress", "prince",
        "princess", "mother", "father", "brother", "sister", "boss", "chief",
        "elder", "senior", "teacher", "student", "the boy", "the girl",
        "old man", "young master", "system", "narrator",
    }
)


@dataclass(frozen=True)
class UnifySeed:
    """One entity considered for cross-partition unification.

    A per-partition supplementary projection of the full `:Entity` — richer than
    the lightweight `SubgraphNode` (which lacks aliases/canonical_name) but bounded
    to just the fields the unifier needs. T1 adds `embedding` + `embedding_model`.
    """

    project_id: str
    entity_id: str
    name: str
    kind: str
    canonical_name: str
    aliases: tuple[str, ...] = ()
    glossary_entity_id: str | None = None

    def norm_key(self) -> str:
        """The canonical match key — the stored `canonical_name` if present, else
        computed from `name`. Empty (honorific-only / stray punctuation) → "" and
        the caller skips this seed from key-equality matching (EC-M18)."""
        if self.canonical_name:
            return self.canonical_name
        try:
            return canonicalize_entity_name(self.name)
        except (TypeError, ValueError):
            return ""

    def alias_keys(self) -> frozenset[str]:
        """Canonicalized {name} ∪ {aliases}, empties dropped — the lexical overlap
        set. `name` is included so an alias in one book can match the display name
        in another."""
        out: set[str] = set()
        for raw in (self.name, *self.aliases):
            if not raw:
                continue
            try:
                k = canonicalize_entity_name(raw)
            except (TypeError, ValueError):
                continue
            if k:
                out.add(k)
        return frozenset(out)


# ── supplementary per-partition seed fetch (aliases/canonical_name) ────
# Binds BOTH $user_id AND $project_id (EC-M4 tenancy) + restricts to the seed ids
# the subgraph already surfaced. Never a cross-partition read.
_SEED_DETAIL_CYPHER = """
MATCH (n:Entity)
WHERE n.user_id = $user_id
  AND n.project_id = $project_id
  AND n.id IN $entity_ids
RETURN n.id AS id,
       n.name AS name,
       n.kind AS kind,
       coalesce(n.canonical_name, '') AS canonical_name,
       coalesce(n.aliases, []) AS aliases,
       n.glossary_entity_id AS glossary_entity_id
"""


async def load_seed_details(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    entity_ids: list[str],
) -> list[UnifySeed]:
    """Load the unifier's per-entity detail (name/canonical_name/aliases/kind) for
    the given ids within ONE partition. Tenancy-bound (user_id + project_id); no
    cross-partition Cypher (EC-M4)."""
    if not entity_ids:
        return []
    result = await run_read(
        session,
        _SEED_DETAIL_CYPHER,
        user_id=user_id,
        project_id=project_id,
        entity_ids=entity_ids,
    )
    seeds: list[UnifySeed] = []
    async for record in result:
        aliases = record["aliases"] or []
        seeds.append(
            UnifySeed(
                project_id=project_id,
                entity_id=str(record["id"]),
                name=str(record["name"] or ""),
                kind=str(record["kind"] or ""),
                canonical_name=str(record["canonical_name"] or ""),
                aliases=tuple(str(a) for a in aliases if a),
                glossary_entity_id=record["glossary_entity_id"],
            )
        )
    return seeds


# ── union-find ─────────────────────────────────────────────────────────


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, x: str) -> None:
        self._parent.setdefault(x, x)

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # path-compress
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # deterministic root: smaller id wins (stable clusters, EC-M22)
            lo, hi = (ra, rb) if ra < rb else (rb, ra)
            self._parent[hi] = lo


# ── lexical matching ───────────────────────────────────────────────────


def _is_common_key(key: str) -> bool:
    return len(key) < _COMMON_NAME_MIN_LEN or key in _COMMON_NAME_STOPLIST


def _lexical_score(a: UnifySeed, b: UnifySeed) -> float | None:
    """Lexical similarity of two SAME-KIND, DIFFERENT-PARTITION seeds, or None if
    not a candidate. Exact canonical-name match → 1.0 (EC-M20: a *common* key needs
    an extra shared alias); otherwise the alias-overlap ratio."""
    ka, kb = a.norm_key(), b.norm_key()
    alias_a, alias_b = a.alias_keys(), b.alias_keys()
    shared = alias_a & alias_b

    if ka and kb and ka == kb:
        if not _is_common_key(ka):
            return 1.0
        # common name: require the shared key PLUS ≥1 other shared alias (EC-M20)
        if len(shared) >= 2:
            return 1.0
        return None

    if shared:
        denom = min(len(alias_a), len(alias_b)) or 1
        score = len(shared) / denom
        if score >= UNIFY_LEX_TAU_LOW:
            return min(score, 0.99)  # alias-only never claims the exact-match 1.0
    return None


def _band(score: float, tau_high: float) -> str:
    return "same" if score >= tau_high else "likely"


def _cluster_id(member_ids: list[str]) -> str:
    """Deterministic, ephemeral cluster id (EC-M22): a stable hash of the sorted
    member entity_ids. Per-call only — the agent must NOT cite it across turns."""
    joined = "|".join(sorted(member_ids))
    return "uc_" + hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


# ── the engine ─────────────────────────────────────────────────────────


@dataclass
class _Pair:
    a: UnifySeed
    b: UnifySeed
    score: float
    method: str


def _match_pairs(seeds: list[UnifySeed], method: str) -> list[_Pair]:
    """All cross-partition, same-kind matching pairs, deterministically ordered.

    T0: `method="by_name"` (lexical only). Buckets by kind (EC-M3), compares only
    seeds from DIFFERENT partitions (EC-M10), skips seeds with an empty norm key
    AND empty alias set (EC-M18)."""
    # bucket by kind
    by_kind: dict[str, list[UnifySeed]] = {}
    for s in seeds:
        if not s.norm_key() and not s.alias_keys():
            continue  # EC-M18 — degenerate, nothing to match on
        by_kind.setdefault(s.kind, []).append(s)

    pairs: list[_Pair] = []
    for kind in sorted(by_kind):
        bucket = sorted(by_kind[kind], key=lambda s: (s.project_id, s.entity_id))
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                if a.project_id == b.project_id:
                    continue  # EC-M10 — cross-partition only
                score = _lexical_score(a, b)  # T1 blends semantic here
                if score is not None:
                    pairs.append(_Pair(a=a, b=b, score=score, method="by_name"))
    return pairs


def _build_result(
    seeds: list[UnifySeed], pairs: list[_Pair], method: str, tau_high: float
) -> dict:
    """Cluster the matched pairs (union-find), cap confidence-descending, and
    emit `unification_clusters` + `bridge_edges`."""
    seed_by_id = {s.entity_id: s for s in seeds}
    uf = _UnionFind()
    for s in seeds:
        uf.add(s.entity_id)
    for p in pairs:
        uf.union(p.a.entity_id, p.b.entity_id)

    # group members by root; keep only multi-member clusters
    members_by_root: dict[str, list[str]] = {}
    for s in seeds:
        members_by_root.setdefault(uf.find(s.entity_id), []).append(s.entity_id)
    clustered_roots = {
        root for root, ids in members_by_root.items() if len(ids) >= 2
    }

    # per-cluster max score (for banding + cap ordering)
    cluster_score: dict[str, float] = {}
    for p in pairs:
        root = uf.find(p.a.entity_id)
        cluster_score[root] = max(cluster_score.get(root, 0.0), p.score)

    # EC-M7 — drop over-size clusters (a weak transitive chain gluing many books)
    surviving_roots = [
        r for r in clustered_roots
        if len(members_by_root[r]) <= UNIFY_MAX_CLUSTER_SIZE
    ]
    # EC-M21 — sort confidence-descending, then id for determinism, THEN cap
    surviving_roots.sort(key=lambda r: (-cluster_score.get(r, 0.0), r))
    unify_capped = len(surviving_roots) > UNIFY_MAX_CLUSTERS
    surviving_roots = surviving_roots[:UNIFY_MAX_CLUSTERS]
    kept = set(surviving_roots)

    clusters: list[dict] = []
    for root in surviving_roots:
        member_ids = sorted(members_by_root[root])
        members = [seed_by_id[mid] for mid in member_ids]
        score = cluster_score.get(root, 0.0)
        clusters.append(
            {
                "cluster_id": _cluster_id(member_ids),
                "kind": members[0].kind,
                "members": [
                    {"project_id": m.project_id, "entity_id": m.entity_id, "name": m.name}
                    for m in members
                ],
                "method": method,
                "score": round(score, 4),
                "band": _band(score, tau_high),
            }
        )

    # bridge edges: one per DIRECTLY-scored cross-partition pair in a kept cluster
    # (pairwise, Q3=pairwise at T0). Transitive-only links get no fabricated bridge.
    bridge_edges: list[dict] = []
    for p in sorted(pairs, key=lambda p: (p.a.entity_id, p.b.entity_id)):
        if uf.find(p.a.entity_id) not in kept:
            continue
        src, tgt = sorted((p.a.entity_id, p.b.entity_id))
        bridge_edges.append(
            {
                "source": src,
                "target": tgt,
                "predicate": "SAME_AS",
                "inferred": True,
                "method": p.method,
                "score": round(p.score, 4),
            }
        )

    return {
        "unification_clusters": clusters,
        "bridge_edges": bridge_edges,
        "unify_method": method,
        "unify_capped": unify_capped,
    }


def _empty_result(method: str) -> dict:
    return {
        "unification_clusters": [],
        "bridge_edges": [],
        "unify_method": method,
        "unify_capped": False,
    }


def cluster_seeds(seeds: list[UnifySeed], method: str = "by_name") -> dict:
    """Pure clustering step (no Neo4j) — cluster already-loaded seeds and return the
    additive result keys. Split out so the engine is unit-testable without a session.

    Guards: fewer than 2 distinct partitions represented → nothing can bridge, so an
    honest empty result (a bridge is by definition cross-partition, EC-M10)."""
    if len({s.project_id for s in seeds}) < 2:
        return _empty_result(method)
    pairs = _match_pairs(seeds, method)
    return _build_result(seeds, pairs, method, tau_high=UNIFY_LEX_TAU_HIGH)


async def unify_subgraph(
    session: CypherSession,
    *,
    user_id: str,
    subgraph: Subgraph,
    method: str,
) -> dict:
    """Run the cross-partition unification pass over an already-loaded forest
    subgraph and return the additive result keys (`unification_clusters`,
    `bridge_edges`, `unify_method`, `unify_capped`).

    `method` is the tool's `unify` arg (`"by_name"` at T0). Groups the subgraph's
    surviving nodes by `source_project_id`, loads each partition's seed detail
    (aliases/canonical_name), clusters, and proposes bridges. NEVER mutates Neo4j."""
    # group surviving nodes by partition (EC-M4 — per-partition, tenancy-bound reads)
    ids_by_partition: dict[str, list[str]] = {}
    for n in subgraph.nodes:
        pid = n.source_project_id
        if not pid:
            continue  # a single-project subgraph never sets it → nothing to unify
        ids_by_partition.setdefault(pid, []).append(n.id)

    if len(ids_by_partition) < 2:
        return _empty_result(method)  # <2 partitions → skip the seed fetch entirely

    seeds: list[UnifySeed] = []
    for pid in sorted(ids_by_partition):
        seeds.extend(
            await load_seed_details(
                session, user_id=user_id, project_id=pid, entity_ids=ids_by_partition[pid]
            )
        )
    return cluster_seeds(seeds, method)
