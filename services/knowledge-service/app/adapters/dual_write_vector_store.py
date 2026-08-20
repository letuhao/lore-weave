"""Dual-write + shadow-read across two `VectorStore` backends (plan T24).

The migration step between "pgvector works" (T23) and "pgvector is the store" (T25). It
implements the port itself, so nothing downstream learns that a migration is in progress —
composition happens at the root, and every consumer keeps holding a `VectorStore`.

── THE ASYMMETRY IS THE WHOLE DESIGN ────────────────────────────────────────────────────
**Writes go to both. Reads come from the primary.** A read served from a half-populated
secondary would be a correctness regression bought for nothing, so the secondary never
answers a request during the migration — it is only ever *compared* against.

── A SWALLOWED SECONDARY FAILURE IS THE DANGEROUS ONE ───────────────────────────────────
A secondary write that fails must not fail the request: the secondary is not authoritative
yet, and taking production down for a backfill target inverts the risk. But a swallowed
failure is invisible *by construction* — the caller got its success — and every one of them
is a row the secondary will still be missing at cutover, when the primary's indexes are
dropped and nothing can reconstruct it.

So the count IS the evidence: `vector_dual_write_total{outcome="secondary_failed"}` must
read **zero** before T25, not "low". That is the mechanism this deferral carries, rather
than a sentence in a runbook. `raise_on_secondary_failure=True` flips it to fail-closed for
a backfill job, where a missing row is the only thing that matters and there is no user
request to protect.

The reverse case is not swallowed at all: if the PRIMARY write fails, the exception
propagates. It is still the system of record.

── WHY THE SHADOW READ IS INLINE AND SAMPLED ────────────────────────────────────────────
Fire-and-forget (`create_task`) would keep the request off the secondary's latency, and
that is exactly why it is wrong here: the task would run after the request released its
connection, so the divergence number would describe a load the request never saw. Sampling
buys the same budget without lying about when the measurement happened.

── OVERLAP IS NOT RECALL ────────────────────────────────────────────────────────────────
Neither backend is ground truth, so what the shadow read reports is **overlap**: how much
of the primary's top-k the secondary also returned. Calling it recall would assert the
primary is correct, which is the very thing T24 is measuring. Recall against exact
arithmetic is `app/benchmark/vector_backend_bench.py`'s job.
"""

from __future__ import annotations

import logging
import random

from app.metrics import (
    vector_dual_write_total,
    vector_shadow_read_extra_total,
    vector_shadow_read_overlap,
    vector_shadow_read_total,
)
from app.ports.vector_store import (
    VectorFilter,
    VectorHit,
    VectorRecord,
    VectorScope,
    VectorStore,
)

logger = logging.getLogger(__name__)

__all__ = ["DualWriteVectorStore"]


class DualWriteVectorStore:
    """Writes to both stores, reads from `primary`, optionally compares `secondary`."""

    def __init__(
        self,
        primary: VectorStore,
        secondary: VectorStore,
        *,
        shadow_read_rate: float = 0.0,
        primary_read_scopes: frozenset[str] = frozenset({"passage", "entity"}),
        raise_on_secondary_failure: bool = False,
        rng: random.Random | None = None,
    ) -> None:
        if not 0.0 <= shadow_read_rate <= 1.0:
            raise ValueError(f"shadow_read_rate must be in [0, 1], got {shadow_read_rate!r}")
        self._primary = primary
        self._secondary = secondary
        self._shadow_read_rate = shadow_read_rate
        # T25 — WHICH SCOPES THE PRIMARY ANSWERS. Default: both, i.e. unchanged.
        #
        # It exists because the cutover is not one decision. `PgVectorStore` deliberately
        # OMITS `anchor_score` from an entity hit (D-T25B-PG-ANCHOR-SCORE): the score is
        # bucket-relative and recomputed on its own schedule, so a copy on the vector row
        # would be confidently stale — worse than absent. Entity reads RANK by it. So
        # passages are ready to cut over and entities are not, and a single primary would
        # have forced one of those two facts to be ignored.
        #
        # The tripwire test that caught this is `test_the_provider_keeps_neo4j_as_primary`,
        # which fired on the argument swap before it shipped.
        self._primary_read_scopes = frozenset(primary_read_scopes)
        self._raise_on_secondary_failure = raise_on_secondary_failure
        # Injectable so a test can pin the sampling decision. Without this the shadow-read
        # tests would either be flaky or have to run at rate 1.0, and rate 1.0 is the one
        # setting that never exercises the sampling branch.
        self._rng = rng or random.Random()

    # ── reads ────────────────────────────────────────────────────────────────

    def _server_and_shadow(self, scope: str):
        """(who answers, who is compared) for this scope. The one that does not serve is
        always the shadow, so the overlap metric keeps measuring new-against-old in whichever
        direction the deployment is currently pointing."""
        if scope in self._primary_read_scopes:
            return self._primary, self._secondary
        return self._secondary, self._primary


    async def search(
        self,
        *,
        scope: VectorScope,
        user_id: str,
        embedding: list[float],
        dim: int,
        k: int = 10,
        filter: VectorFilter | None = None,
        include_vectors: bool = False,
    ) -> list[VectorHit]:
        server, shadow = self._server_and_shadow(scope)
        hits = await server.search(
            scope=scope, user_id=user_id, embedding=embedding, dim=dim, k=k, filter=filter,
            include_vectors=include_vectors,
        )
        if self._shadow_read_rate <= 0.0 or self._rng.random() >= self._shadow_read_rate:
            if self._shadow_read_rate > 0.0:
                vector_shadow_read_total.labels(outcome="skipped_sampling").inc()
            return hits
        # `include_vectors` is deliberately NOT forwarded to the shadow: the comparison is
        # over `record_id` sets and nothing else, so asking it for k×dim floats would pay
        # the whole payload to discard it. Omitted on purpose, said here so it does not read
        # as the parameter having been missed.
        await self._compare(
            shadow, hits, scope=scope, user_id=user_id, embedding=embedding, dim=dim, k=k,
            filter=filter,
        )
        return hits

    async def _compare(self, shadow_store: VectorStore, hits: list[VectorHit], **kw) -> None:
        """Never raises and never changes the answer. A shadow read that broke the request
        it was measuring would be a monitoring tool causing the outage it reports."""
        try:
            shadow = await shadow_store.search(**kw)
        except Exception as exc:  # noqa: BLE001 — see the docstring; this is the point
            # NOT counted as agreement. A comparison that did not happen is unmeasured, and
            # folding it into the overlap histogram would make a broken secondary look like
            # a perfect one.
            vector_shadow_read_total.labels(outcome="failed").inc()
            logger.warning(
                "vector shadow read failed: scope=%s dim=%s err=%s",
                kw.get("scope"), kw.get("dim"), exc,
            )
            return

        vector_shadow_read_total.labels(outcome="compared").inc()
        primary_ids = {h.record_id for h in hits}
        if not primary_ids:
            # An empty primary result has no top-k to overlap with. Recording 1.0 ("they
            # agreed") or 0.0 ("total divergence") would both be inventions.
            return
        shadow_ids = {h.record_id for h in shadow}
        overlap = len(primary_ids & shadow_ids) / len(primary_ids)
        vector_shadow_read_overlap.observe(overlap)
        # 🔴 The direction `overlap` cannot see. It is |P ∩ S| / |P|, so a shadow returning a
        # SUPERSET scores a perfect 1.0 — and after the cutover the shadow's rows become the
        # served answer, which makes "rows the secondary has and the primary does not" the
        # single most important disagreement and the one the gating metric was blind to.
        # (QC-3 `/review-impl`, 2026-08-14.)
        if shadow_ids - primary_ids:
            vector_shadow_read_extra_total.inc()
            logger.warning(
                "vector shadow read EXTRA: scope=%s dim=%s the secondary returned %d "
                "record(s) the primary did not — after the cutover these become the answer",
                kw.get("scope"), kw.get("dim"), len(shadow_ids - primary_ids),
            )
        if overlap < 1.0:
            logger.warning(
                "vector shadow read divergence: scope=%s dim=%s k=%s overlap=%.3f "
                "primary=%d secondary=%d",
                kw.get("scope"), kw.get("dim"), kw.get("k"), overlap, len(hits), len(shadow),
            )

    # ── writes ───────────────────────────────────────────────────────────────

    async def upsert(self, record: VectorRecord) -> bool:
        scope = record.scope
        try:
            written = await self._primary.upsert(record)
        except Exception:
            # The primary is still the system of record. Its failure is the caller's.
            vector_dual_write_total.labels(scope=scope, outcome="primary_failed").inc()
            raise

        if not written:
            # The primary reports the target is gone (an entity deleted between embedding
            # and write). Writing it to the secondary anyway would seed the store we are
            # about to cut over to with a row the primary deliberately refused.
            vector_dual_write_total.labels(scope=scope, outcome="primary_only").inc()
            return written

        try:
            await self._secondary.upsert(record)
        except Exception as exc:  # noqa: BLE001
            vector_dual_write_total.labels(scope=scope, outcome="secondary_failed").inc()
            logger.error(
                "vector dual-write SECONDARY FAILED (row will be missing at cutover): "
                "scope=%s dim=%s err=%s",
                scope, record.embedding_dim, exc,
            )
            if self._raise_on_secondary_failure:
                raise
            return written

        vector_dual_write_total.labels(scope=scope, outcome="both").inc()
        return written

    # ── index lifecycle ──────────────────────────────────────────────────────

    async def ensure_index(
        self, *, project_id: str, embedding_model_uuid: str, embedding_dimension: int,
    ) -> dict[str, str]:
        """Both stores, primary's names returned.

        The secondary's failure is NOT swallowed here, unlike a row write: an index that
        does not exist means every subsequent write to that store is unindexed, so the
        failure is systematic rather than one lost row. Failing loudly at the one call that
        happens per job start is much cheaper than discovering it at cutover.
        """
        names = await self._primary.ensure_index(
            project_id=project_id, embedding_model_uuid=embedding_model_uuid,
            embedding_dimension=embedding_dimension,
        )
        await self._secondary.ensure_index(
            project_id=project_id, embedding_model_uuid=embedding_model_uuid,
            embedding_dimension=embedding_dimension,
        )
        return names

    async def drop_index(self, *, name: str) -> None:
        """Primary only, deliberately. The two stores name their indexes differently — the
        Postgres names are not even parseable as Neo4j summary names, which is a property
        T23 relies on — so forwarding one store's name to the other would either raise or,
        worse, match something unintended. The secondary's indexes are managed by whoever
        owns the secondary's schema, and T25 is where that becomes the only schema.
        """
        await self._primary.drop_index(name=name)

    async def list_indexes(self) -> list[dict[str, str]]:
        """Primary only. Merging the two lists would hand the prune-orphans admin path a
        set of names from two namespaces with no way to tell which store each came from —
        and it drops what it is given."""
        return await self._primary.list_indexes()
