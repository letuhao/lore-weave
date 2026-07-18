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

import asyncio
import hashlib
from collections import Counter
from dataclasses import dataclass, replace

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
# Per-method bands (EC-M17 / D8): lexical and semantic scores are NOT on the same
# scale, so each method carries its own (low, high) pair. A pair MATCHES (unions)
# at score ≥ τ_low; its band is "same" at ≥ τ_high else "likely".
UNIFY_LEX_TAU_HIGH = 1.0    # exact canonical-name match → "same"
UNIFY_LEX_TAU_LOW = 0.5     # alias-overlap ≥ this → "likely" candidate
UNIFY_SEM_TAU_HIGH = 0.85   # cosine ≥ this → "same" (T1)
UNIFY_SEM_TAU_LOW = 0.72    # cosine ≥ this → "likely" candidate (T1)

UNIFY_MAX_CLUSTERS = 100        # EC-M11 — cap emitted clusters (confidence-desc, EC-M21)
UNIFY_MAX_CLUSTER_SIZE = 16     # EC-M7 — a cluster spanning >16 partitions is suspect
UNIFY_ONDEMAND_EMBED_CAP = 100  # EC-M15 — max discovered seeds embedded on demand per call
# Per-kind cosine is O(bucket²)×dim; above this bucket size the semantic pass would
# do >~30K dim-wide dot products and dominate latency, so an oversized same-kind
# bucket falls back to (cheap) lexical-only and flags unify_capped. The whole
# clustering also runs off the event loop (asyncio.to_thread) so it never starves
# the service even at the 500-node subgraph cap.
UNIFY_SEMANTIC_MAX_BUCKET = 250

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
    # T1 semantic: the stored per-entity vector (only anchored entities carry one)
    # + the model it was embedded under. `embedding_model` gates cosine (EC-M1) —
    # a pair is compared semantically only when both share it.
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None

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
       n.embedding_model AS embedding_model,
       coalesce(n.embedding_384, n.embedding_1024,
                n.embedding_1536, n.embedding_3072) AS embedding
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
        raw_vec = record["embedding"]
        embedding = (
            tuple(float(x) for x in raw_vec)
            if raw_vec is not None and len(raw_vec) > 0
            else None
        )
        seeds.append(
            UnifySeed(
                project_id=project_id,
                entity_id=str(record["id"]),
                name=str(record["name"] or ""),
                kind=str(record["kind"] or ""),
                canonical_name=str(record["canonical_name"] or ""),
                aliases=tuple(str(a) for a in aliases if a),
                embedding=embedding,
                embedding_model=record["embedding_model"],
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


# ── semantic matching (T1) ─────────────────────────────────────────────


# NOT migrated to `loreweave_vecmath.cosine_similarity` (2026-07-08 review,
# /review-impl finding on the vecmath promotion sweep): that SDK function
# returns a plain `float`, collapsing "zero-norm/length-mismatched" (degenerate)
# and "computed cosine of exactly 0.0" (orthogonal vectors) into the same 0.0
# value. This `_cosine` deliberately keeps them distinct via `Optional[float]`
# so `_semantic_score` can tell "no usable signal, fall back to lexical" apart
# from "a real, computed score" — see EC-M19. Reusing the SDK's plain-float
# form here would silently fold that distinction away for any future caller
# (or any future change to `UNIFY_SEM_TAU_LOW`), even though today the single
# caller (`_semantic_score`, below) happens to treat both the same because
# `UNIFY_SEM_TAU_LOW` (0.72) is positive. Kept as a one-off local
# implementation rather than promoted to the shared module for a single
# call site.
def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float | None:
    """Cosine similarity, or None if either vector is zero-norm / length-mismatched
    (EC-M19 — no divide-by-zero / NaN; such a pair falls back to lexical)."""
    if len(a) != len(b) or not a:
        return None
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return None
    return dot / ((na ** 0.5) * (nb ** 0.5))


def _semantic_score(a: UnifySeed, b: UnifySeed) -> float | None:
    """Cosine of two seeds' vectors, gated on a SHARED embedding_model (EC-M1 —
    cross-model cosine is meaningless). None if either lacks a vector, the models
    differ, or the cosine is below τ_sem_low."""
    if a.embedding is None or b.embedding is None:
        return None
    if not a.embedding_model or a.embedding_model != b.embedding_model:
        return None  # EC-M1 model-space gate
    cos = _cosine(a.embedding, b.embedding)
    if cos is None or cos < UNIFY_SEM_TAU_LOW:
        return None
    return cos


def _band(score: float, method: str) -> str:
    """Per-method band (EC-M17): the τ_high that applies depends on the method."""
    tau_high = UNIFY_SEM_TAU_HIGH if method == "semantic" else UNIFY_LEX_TAU_HIGH
    return "same" if score >= tau_high else "likely"


_BAND_RANK = {"same": 1, "likely": 0}


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
    band: str


def _match_pairs(seeds: list[UnifySeed], method: str) -> tuple[list[_Pair], bool]:
    """All cross-partition, same-kind matching pairs, deterministically ordered.

    `method="by_name"` → lexical only. `method="semantic"` → semantic PRIMARY
    (cosine, model-gated) blended with lexical FALLBACK (D1); each pair records the
    winning signal in `.method` so the blend is visible. Buckets by kind (EC-M3),
    compares only DIFFERENT-partition seeds (EC-M10), skips seeds with an empty norm
    key AND empty alias set AND no vector (EC-M18).

    Returns ``(pairs, semantic_capped)`` — semantic_capped is True when an oversized
    same-kind bucket (> UNIFY_SEMANTIC_MAX_BUCKET) fell back to lexical-only to bound
    the O(n²)×dim cosine cost (the caller flags unify_capped)."""
    by_kind: dict[str, list[UnifySeed]] = {}
    for s in seeds:
        if not s.norm_key() and not s.alias_keys() and s.embedding is None:
            continue  # EC-M18 — degenerate, nothing to match on
        by_kind.setdefault(s.kind, []).append(s)

    pairs: list[_Pair] = []
    semantic_capped = False
    for kind in sorted(by_kind):
        bucket = sorted(by_kind[kind], key=lambda s: (s.project_id, s.entity_id))
        # Oversized bucket → skip the O(n²)×dim cosine, use cheap lexical only.
        use_semantic = method == "semantic"
        if use_semantic and len(bucket) > UNIFY_SEMANTIC_MAX_BUCKET:
            use_semantic = False
            semantic_capped = True
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                if a.project_id == b.project_id:
                    continue  # EC-M10 — cross-partition only

                pair_method = pair_score = None
                if use_semantic:
                    sem = _semantic_score(a, b)
                    if sem is not None:
                        pair_method, pair_score = "semantic", sem
                if pair_method is None:  # by_name mode, or semantic fell through
                    lex = _lexical_score(a, b)
                    if lex is not None:
                        pair_method, pair_score = "by_name", lex
                if pair_method is not None:
                    pairs.append(
                        _Pair(
                            a=a, b=b, score=pair_score, method=pair_method,
                            band=_band(pair_score, pair_method),
                        )
                    )
    return pairs, semantic_capped


def _detect_disagreements(
    edges,
    *,
    uf: _UnionFind,
    kept: set[str],
    cluster_id_by_root: dict[str, str],
    seed_by_id: dict[str, UnifySeed],
) -> list[dict]:
    """T2 (spec §5) — surface where the unified books DISAGREE, never reconcile.

    For each intra-book RELATES_TO edge whose SOURCE is a unified cross-book entity,
    group by (source-cluster, target-group) where the target-group is the target's
    cluster if unified else its own entity_id (EC-M23). Within a group, ≥2 DISTINCT
    predicates from DIFFERENT books = a disagreement (same predicate = agreement,
    emitted only via the bridge). Expose it; the agent decides."""
    def _group_of(eid: str) -> tuple[str, str]:
        seed = seed_by_id.get(eid)
        if seed is not None:
            root = uf.find(eid)
            if root in kept:
                return ("cluster", cluster_id_by_root[root])
        return ("entity", eid)  # target capped out of the seed set, or a singleton

    # (src_cluster_id, target_group) → sorted-unique (predicate, project_id)
    obs: dict[tuple, set[tuple[str, str]]] = {}
    for e in edges or []:
        src_kind, src_key = _group_of(e.source)
        if src_kind != "cluster":
            continue  # only a cross-book (unified) source can disagree with itself
        src_seed = seed_by_id.get(e.source)
        if src_seed is None:
            continue
        tgt_group = _group_of(e.target)
        obs.setdefault((src_key, tgt_group), set()).add(
            (e.predicate, src_seed.project_id)
        )

    disagreements: list[dict] = []
    for (src_cid, tgt_group), pairs_set in sorted(obs.items(), key=lambda kv: str(kv[0])):
        by_pred_proj = sorted(pairs_set)
        # A CROSS-BOOK disagreement needs two observations differing in BOTH the
        # predicate AND the book — else it's an intra-book self-contradiction (both
        # edges from the same project), which is a different thing, not surfaced here.
        conflict = None
        for x in range(len(by_pred_proj)):
            for y in range(x + 1, len(by_pred_proj)):
                if by_pred_proj[x][0] != by_pred_proj[y][0] and \
                        by_pred_proj[x][1] != by_pred_proj[y][1]:
                    conflict = (by_pred_proj[x], by_pred_proj[y])
                    break
            if conflict:
                break
        if conflict is None:
            continue
        first, second = conflict
        record = {
            "cluster_id": src_cid,
            "predicate_a": first[0],
            "project_a": first[1],
            "predicate_b": second[0],
            "project_b": second[1],
        }
        if tgt_group[0] == "cluster":
            record["target_cluster_id"] = tgt_group[1]
        else:
            record["target_entity_id"] = tgt_group[1]  # EC-M23 singleton fallback
        disagreements.append(record)
    return disagreements


def _build_result(
    seeds: list[UnifySeed],
    pairs: list[_Pair],
    method: str,
    edges=None,
    extra_capped: bool = False,
) -> dict:
    """Cluster the matched pairs (union-find), cap confidence-descending, and
    emit `unification_clusters` + `bridge_edges`. A cluster's headline
    score/band/method come from its STRONGEST pair (best band, then score) — scores
    across methods aren't comparable, so band rank leads (EC-M17)."""
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

    # per-cluster STRONGEST pair (band rank, then score) — the representative
    def _pair_strength(p: _Pair) -> tuple[int, float]:
        return (_BAND_RANK[p.band], p.score)

    cluster_rep: dict[str, _Pair] = {}
    for p in pairs:
        root = uf.find(p.a.entity_id)
        cur = cluster_rep.get(root)
        if cur is None or _pair_strength(p) > _pair_strength(cur):
            cluster_rep[root] = p

    # EC-M7 — drop over-size clusters (a weak transitive chain gluing many books)
    surviving_roots = [
        r for r in clustered_roots
        if len(members_by_root[r]) <= UNIFY_MAX_CLUSTER_SIZE
    ]
    # EC-M21 — sort confidence-descending (band rank, then score), then id for
    # determinism, THEN cap so the cap drops the WEAKEST, never a random tail.
    surviving_roots.sort(
        key=lambda r: (
            -_BAND_RANK[cluster_rep[r].band] if r in cluster_rep else 0,
            -(cluster_rep[r].score if r in cluster_rep else 0.0),
            r,
        )
    )
    unify_capped = extra_capped or len(surviving_roots) > UNIFY_MAX_CLUSTERS
    surviving_roots = surviving_roots[:UNIFY_MAX_CLUSTERS]
    kept = set(surviving_roots)

    clusters: list[dict] = []
    cluster_id_by_root: dict[str, str] = {}
    for root in surviving_roots:
        member_ids = sorted(members_by_root[root])
        members = [seed_by_id[mid] for mid in member_ids]
        rep = cluster_rep[root]
        cid = _cluster_id(member_ids)
        cluster_id_by_root[root] = cid
        clusters.append(
            {
                "cluster_id": cid,
                "kind": members[0].kind,
                "members": [
                    {"project_id": m.project_id, "entity_id": m.entity_id, "name": m.name}
                    for m in members
                ],
                "method": rep.method,
                "score": round(rep.score, 4),
                "band": rep.band,
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

    disagreements = _detect_disagreements(
        edges,
        uf=uf,
        kept=kept,
        cluster_id_by_root=cluster_id_by_root,
        seed_by_id=seed_by_id,
    )

    return {
        "unification_clusters": clusters,
        "bridge_edges": bridge_edges,
        "disagreements": disagreements,
        "unify_method": method,
        "unify_capped": unify_capped,
    }


def _empty_result(method: str) -> dict:
    out = {
        "unification_clusters": [],
        "bridge_edges": [],
        "disagreements": [],
        "unify_method": method,
        "unify_capped": False,
    }
    if method == "semantic":
        out["unify_embed_skipped"] = 0  # contract-stable for the semantic path (EC-M15)
    return out


def cluster_seeds(
    seeds: list[UnifySeed],
    method: str = "by_name",
    *,
    edges=None,
    embed_skipped: int = 0,
) -> dict:
    """Pure clustering step (no Neo4j) — cluster already-loaded seeds and return the
    additive result keys. Split out so the engine is unit-testable without a session.

    `edges` (the forest's intra-book RELATES_TO edges) drives T2 disagreement
    detection. Guards: fewer than 2 distinct partitions represented → nothing can
    bridge, so an honest empty result (a bridge is cross-partition by definition,
    EC-M10)."""
    if len({s.project_id for s in seeds}) < 2:
        result = _empty_result(method)
    else:
        pairs, semantic_capped = _match_pairs(seeds, method)
        result = _build_result(
            seeds, pairs, method, edges=edges, extra_capped=semantic_capped
        )
    if method == "semantic":
        result["unify_embed_skipped"] = embed_skipped  # EC-M15
    return result


async def _ondemand_embed(
    seeds: list[UnifySeed], *, embedding_client, user_id: str
) -> tuple[list[UnifySeed], int]:
    """Q1=b (§7.1; EC-M14/M15/M16) — embed DISCOVERED (unembedded) seeds ON DEMAND so
    the semantic pass sees them, under the anchored `embedding_model`, IN MEMORY only
    (never `set_entity_embedding` — the stored graph stays byte-identical, D3/EC-M16),
    and spend-capped (EC-M15). Returns (seeds_with_vectors, embed_skipped).

    Model resolution (EC-M14): (1) the dominant `embedding_model` among seeds that
    already carry a vector; (2) else the user's default embed model; (3) else SKIP —
    semantic degrades to lexical for the unembedded seeds (never guess a model)."""
    if embedding_client is None:
        return seeds, 0

    model_counts = Counter(
        s.embedding_model
        for s in seeds
        if s.embedding is not None and s.embedding_model
    )
    target_model = model_counts.most_common(1)[0][0] if model_counts else None
    if target_model is None:  # EC-M14 step 2 — no anchored vector anywhere
        try:
            from app.clients.default_model import resolve_user_default_model

            # capability MUST be "embedding" — provider-registry's
            # defaultModelCapabilities key (NOT "embed"); a wrong string 400s → None.
            target_model = await resolve_user_default_model(
                user_id, capability="embedding"
            )
        except Exception:  # noqa: BLE001 — best-effort; degrade to lexical
            target_model = None
    if target_model is None:
        return seeds, 0  # EC-M14 step 3 — no resolvable model → lexical fallback

    # discovered seeds needing a vector, deterministic order, capped (EC-M15)
    todo = sorted(
        (i for i, s in enumerate(seeds) if s.embedding is None),
        key=lambda i: (seeds[i].project_id, seeds[i].entity_id),
    )
    embed_skipped = max(0, len(todo) - UNIFY_ONDEMAND_EMBED_CAP)
    todo = todo[:UNIFY_ONDEMAND_EMBED_CAP]

    from app.extraction.entity_embedder import build_embed_text

    texts: list[str] = []
    idxs: list[int] = []
    for i in todo:
        text = build_embed_text(seeds[i].name, list(seeds[i].aliases), None)
        if text:
            texts.append(text)
            idxs.append(i)
    if not texts:
        return seeds, embed_skipped

    try:
        result = await embedding_client.embed(
            user_id=user_id,
            model_source="user_model",
            model_ref=target_model,
            texts=texts,
        )
    except Exception:  # noqa: BLE001 — embed failure degrades to lexical, never fails the tool
        return seeds, embed_skipped

    vectors = list(getattr(result, "embeddings", None) or [])
    if len(vectors) != len(idxs):
        return seeds, embed_skipped  # mismatch → don't risk misaligned vectors

    out = list(seeds)
    for i, vec in zip(idxs, vectors):
        out[i] = replace(
            seeds[i],
            embedding=tuple(float(x) for x in vec),
            embedding_model=target_model,
        )
    return out, embed_skipped


async def unify_subgraph(
    session: CypherSession,
    *,
    user_id: str,
    subgraph: Subgraph,
    method: str,
    embedding_client=None,
) -> dict:
    """Run the cross-partition unification pass over an already-loaded forest
    subgraph and return the additive result keys (`unification_clusters`,
    `bridge_edges`, `unify_method`, `unify_capped`[, `unify_embed_skipped`]).

    `method` is the tool's `unify` arg. Groups the subgraph's surviving nodes by
    `source_project_id`, loads each partition's seed detail (aliases/canonical_name
    /embedding), for `"semantic"` embeds discovered seeds on demand (Q1=b), clusters,
    and proposes bridges. NEVER mutates Neo4j."""
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

    embed_skipped = 0
    if method == "semantic":
        seeds, embed_skipped = await _ondemand_embed(
            seeds, embedding_client=embedding_client, user_id=user_id
        )
    # Clustering is CPU-bound (O(n²) pairwise, ×dim for cosine); run it OFF the event
    # loop so a large-union semantic call never starves the async service (finding #1).
    result = await asyncio.to_thread(
        cluster_seeds, seeds, method, edges=subgraph.edges, embed_skipped=embed_skipped
    )
    # The unifier only sees the node-capped subgraph (top-N by salience) — a
    # low-salience recurrence below the cap is invisible; say so, don't imply coverage.
    if getattr(subgraph, "node_cap_hit", False):
        result["unify_note"] = (
            "unification covered only the returned (node-capped) nodes; a low-salience "
            "cross-book recurrence may be missing — raise limit to widen coverage"
        )
    return result
