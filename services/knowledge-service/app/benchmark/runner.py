"""C12b-a — on-demand K17.9 benchmark orchestration.

``run_project_benchmark`` is the request-path sibling of the CLI
``_run_cli`` in ``eval/run_benchmark.py``: same sequence of load →
run → persist, same harness classes, but exposed as a reusable async
function so the public POST endpoint can invoke it without shelling
out to a subprocess.

Isolation (Option A — empty-project guard): benchmark passages are
tagged ``source_type="benchmark_entity"`` by the fixture loader.
``KNOWN_SOURCE_TYPES`` is the single source of truth for "real" user
source types (chapter, chat, glossary); this orchestrator refuses to
run against any project that already contains passages of those
types, matching the fixture loader's documented assumption that
benchmarks target a dedicated project.

Concurrency (single-worker caveat): per-project sentinel set
``_running`` serialises concurrent POSTs within the same uvicorn
worker. Check-and-add is purely synchronous — immune to ``await``
insertions during future refactors (an earlier draft used
``asyncio.Lock`` with a pre-check; review-impl MED flagged that
pattern as fragile because atomicity depended on "no await between
lock.locked() and async with lock:", which a later edit could
silently break without tests noticing). Multi-worker deploys need
a distributed lock (Postgres ``pg_try_advisory_lock``) — tracked
as a TODO until we actually scale past one worker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import asyncpg

from app.clients.embedding_client import EmbeddingClient
from app.context.selectors.passages import EMBEDDING_MODEL_TO_DIM
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.passages import KNOWN_SOURCE_TYPES, SUPPORTED_PASSAGE_DIMS
from app.db.repositories.projects import ProjectsRepo
from eval.fixture_loader import BENCHMARK_SOURCE_TYPE, load_golden_set_as_passages
from eval.mode3_query_runner import Mode3QueryRunner
from eval.persist import persist_benchmark_report
from eval.run_benchmark import (
    AsyncBenchmarkRunner,
    BenchmarkReport,
    _default_golden_path,
    _default_run_id,
    load_golden_set,
)

__all__ = [
    "BenchmarkRunError",
    "FixtureLoadIncompleteError",
    "NoEmbeddingModelError",
    "UnknownEmbeddingModelError",
    "NotBenchmarkProjectError",
    "BenchmarkAlreadyRunningError",
    "BenchmarkRunResult",
    "run_project_benchmark",
]

logger = logging.getLogger(__name__)


class BenchmarkRunError(Exception):
    """Base class for benchmark orchestration failures."""


class NoEmbeddingModelError(BenchmarkRunError):
    """Project has no ``embedding_model`` / ``embedding_dimension`` set."""


class UnknownEmbeddingModelError(BenchmarkRunError):
    """Project's ``embedding_model`` is not in ``EMBEDDING_MODEL_TO_DIM`` —
    the harness can't look up the right vector index dim."""


class NotBenchmarkProjectError(BenchmarkRunError):
    """Project already contains real (chapter/chat/glossary) passages.
    K17.9 assumes a dedicated benchmark project per ``eval/fixture_loader.py``.
    """


class BenchmarkAlreadyRunningError(BenchmarkRunError):
    """Another benchmark is already in-flight for this project in this
    worker. FE should 409 and let the user retry."""


class FixtureLoadIncompleteError(BenchmarkRunError):
    """Fixture loader embedded fewer entities than the golden set
    contains (embedding provider flake, usually). We refuse to persist
    a run scored against an incomplete fixture — the resulting low
    recall would look like a retrieval regression and mislead the FE.
    Router maps this to 502 ``embedding_provider_flake``."""


@dataclass(frozen=True)
class BenchmarkRunResult:
    """Projection of the harness report the router returns to the FE.

    Keeps the wire shape small — the full ``raw_report`` stays in
    ``project_embedding_benchmark_runs`` and the FE can re-read it via
    the existing ``GET /benchmark-status`` endpoint if it needs the
    per-query breakdown.
    """

    run_id: str
    embedding_model: str
    passed: bool
    recall_at_3: float
    mrr: float
    avg_score_positive: float
    negative_control_max_score: float
    stddev_recall: float
    stddev_mrr: float
    runs: int


# Per-(user, project) in-flight sentinel. Single-threaded asyncio
# means dict/set mutations don't race without an ``await`` between
# them — so check-and-add with a plain set is atomic by construction
# and can't be broken by inserting an ``await`` later. The earlier
# ``asyncio.Lock`` variant required the reviewer to verify no await
# crept between ``lock.locked()`` and ``async with lock:``.
_running: set[tuple[str, str]] = set()


def _try_mark_running(user_id: UUID, project_id: UUID) -> tuple[str, str] | None:
    """Atomic check-and-add. Returns the sentinel key on success, or
    ``None`` if a benchmark is already in-flight for this project."""
    key = (str(user_id), str(project_id))
    if key in _running:
        return None
    _running.add(key)
    return key


def _mark_done(key: tuple[str, str]) -> None:
    _running.discard(key)


_REAL_PASSAGE_COUNT_CYPHER = """
MATCH (p:Passage)
WHERE p.user_id = $user_id
  AND p.project_id = $project_id
  AND p.source_type IN $real_types
RETURN count(p) AS n
"""


async def _has_real_passages(user_id: str, project_id: str) -> bool:
    """True if the project already holds any passage whose source_type
    is in ``KNOWN_SOURCE_TYPES``. ``benchmark_entity`` is excluded so
    re-runs don't self-block.
    """
    from app.db.neo4j_helpers import run_read

    async with neo4j_session() as session:
        result = await run_read(
            session,
            _REAL_PASSAGE_COUNT_CYPHER,
            user_id=user_id,
            project_id=project_id,
            real_types=sorted(KNOWN_SOURCE_TYPES),
        )
        record = await result.single()
    return bool(record) and int(record["n"]) > 0


async def run_project_benchmark(
    *,
    user_id: UUID,
    project_id: UUID,
    runs: int,
    pool: asyncpg.Pool,
    projects_repo: ProjectsRepo,
    embedding_client: EmbeddingClient,
    model_source: str = "user_model",
    embedding_provider_id: UUID | None = None,
    golden_path: str | Path | None = None,
) -> BenchmarkRunResult:
    """Validate → acquire lock → load fixture → run harness → persist.

    Raises ``BenchmarkRunError`` subclasses on validation failures
    (router maps to 409). The caller is responsible for the 404 check
    on a missing/cross-user project *before* calling — this function
    assumes the project is owned.

    TODO (model_source): the project row doesn't carry a source tag
    for the embedding model. Default to ``"user_model"`` matches how
    K12.4 expects users to have their own BYOK provider wired up.
    Platform-model benchmarks would need a new project column.
    """
    project = await projects_repo.get(user_id, project_id)
    if project is None:
        # Defensive: router should have 404'd already.
        raise BenchmarkRunError("project not found (caller should 404 upstream)")

    if not project.embedding_model or not project.embedding_dimension:
        raise NoEmbeddingModelError(
            "project has no embedding_model/embedding_dimension configured",
        )

    embedding_dim = EMBEDDING_MODEL_TO_DIM.get(project.embedding_model)
    if embedding_dim is None:
        raise UnknownEmbeddingModelError(
            f"embedding model {project.embedding_model!r} not in "
            "EMBEDDING_MODEL_TO_DIM — extend the map before running",
        )
    # Guard: EMBEDDING_MODEL_TO_DIM carries some models (e.g. nomic-
    # embed-text at dim 768) whose dim isn't in SUPPORTED_PASSAGE_DIMS.
    # Those models skip the L3 selector silently in production; here
    # we'd fail later inside upsert_passage with a ValueError — convert
    # to a clean 409 instead.
    if embedding_dim not in SUPPORTED_PASSAGE_DIMS:
        raise UnknownEmbeddingModelError(
            f"embedding model {project.embedding_model!r} uses dim "
            f"{embedding_dim} which has no :Passage vector index",
        )

    if await _has_real_passages(str(user_id), str(project_id)):
        raise NotBenchmarkProjectError(
            "project contains real (chapter/chat/glossary) passages; "
            "benchmarks require a dedicated project",
        )

    running_key = _try_mark_running(user_id, project_id)
    if running_key is None:
        raise BenchmarkAlreadyRunningError(
            "a benchmark is already running for this project",
        )

    try:
        golden = load_golden_set(golden_path or _default_golden_path())
        async with neo4j_session() as session:
            loaded = await load_golden_set_as_passages(
                session,
                embedding_client,
                golden,
                user_id=str(user_id),
                project_id=str(project_id),
                user_uuid=user_id,
                model_source=model_source,
                embedding_model=project.embedding_model,
                embedding_dim=embedding_dim,
            )
            expected = len(golden.entities)
            logger.info(
                "C12b-a: loaded %d/%d fixture passages for project %s",
                loaded, expected, project_id,
            )
            # review-impl LOW #4: partial loads (embedder flake) must
            # not persist a false-negative run. The benchmark would
            # score zero recall on the entities whose fixture didn't
            # embed, which is indistinguishable from a retrieval
            # regression at report-read time. Fail loud, let the FE
            # surface "provider flake, retry" instead.
            if loaded < expected:
                raise FixtureLoadIncompleteError(
                    f"fixture load incomplete: {loaded}/{expected} "
                    "entities embedded — not persisting benchmark run",
                )
            runner = Mode3QueryRunner(
                session,
                embedding_client,
                user_id=str(user_id),
                project_id=str(project_id),
                user_uuid=user_id,
                model_source=model_source,
                embedding_model=project.embedding_model,
                embedding_dim=embedding_dim,
            )
            report = await AsyncBenchmarkRunner(golden, runner).run(runs=runs)

        run_id = _default_run_id()
        passed = report.passes_thresholds()
        await persist_benchmark_report(
            pool,
            project_id=project_id,
            embedding_provider_id=embedding_provider_id,
            embedding_model=project.embedding_model,
            run_id=run_id,
            report=report,
        )
    finally:
        _mark_done(running_key)

    logger.info(
        "C12b-a: benchmark %s for project %s (run_id=%s, model=%s)",
        "PASSED" if passed else "FAILED",
        project_id, run_id, project.embedding_model,
    )

    return _project_report(run_id, project.embedding_model, report, passed)


def _project_report(
    run_id: str, embedding_model: str, report: BenchmarkReport, passed: bool,
) -> BenchmarkRunResult:
    return BenchmarkRunResult(
        run_id=run_id,
        embedding_model=embedding_model,
        passed=passed,
        recall_at_3=report.recall_at_3,
        mrr=report.mrr,
        avg_score_positive=report.avg_score_positive,
        negative_control_max_score=report.negative_control_max_score,
        stddev_recall=report.stddev_recall,
        stddev_mrr=report.stddev_mrr,
        runs=report.runs,
    )


def _reset_locks_for_tests() -> None:
    """Test-only helper: clear the in-flight sentinel set. Each test
    that pokes at running-state should call this in setup to isolate.
    Not intended for production code paths."""
    _running.clear()
