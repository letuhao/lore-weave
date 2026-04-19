import pytest

from app.db.migrate import run_migrations


@pytest.mark.asyncio
async def test_tables_exist(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('knowledge_projects', 'knowledge_summaries')
            """
        )
    names = {r["table_name"] for r in rows}
    assert names == {"knowledge_projects", "knowledge_summaries"}


@pytest.mark.asyncio
async def test_migrations_idempotent(pool):
    # Running migrations a second time must not raise.
    await run_migrations(pool)
    await run_migrations(pool)


@pytest.mark.asyncio
async def test_project_type_check_constraint(pool):
    async with pool.acquire() as conn:
        with pytest.raises(Exception) as exc:
            await conn.execute(
                """
                INSERT INTO knowledge_projects (user_id, name, project_type)
                VALUES (gen_random_uuid(), 'bad', 'nonsense')
                """
            )
        assert "knowledge_projects_project_type_check" in str(exc.value) or "check" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_partial_index_exists(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'knowledge_projects'
              AND indexname = 'idx_knowledge_projects_user'
            """
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_summaries_unique_nulls_not_distinct(pool):
    uid = "00000000-0000-0000-0000-000000000001"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO knowledge_summaries (user_id, scope_type, scope_id, content) VALUES ($1, 'global', NULL, 'a')",
            uid,
        )
        with pytest.raises(Exception) as exc:
            await conn.execute(
                "INSERT INTO knowledge_summaries (user_id, scope_type, scope_id, content) VALUES ($1, 'global', NULL, 'b')",
                uid,
            )
        msg = str(exc.value).lower()
        assert "unique" in msg or "duplicate" in msg


# ─── K10.1 / K10.2 / K10.3 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_tables_exist(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('extraction_pending','extraction_jobs','extraction_errors')
            """
        )
    names = {r["table_name"] for r in rows}
    assert names == {"extraction_pending", "extraction_jobs", "extraction_errors"}


@pytest.mark.asyncio
async def test_k10_3_projects_has_extraction_budget_columns(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'knowledge_projects'
              AND column_name IN (
                'monthly_budget_usd','current_month_spent_usd','current_month_key',
                'stat_entity_count','stat_fact_count','stat_event_count',
                'stat_glossary_count','stat_updated_at'
              )
            """
        )
    names = {r["column_name"] for r in rows}
    assert names == {
        "monthly_budget_usd", "current_month_spent_usd", "current_month_key",
        "stat_entity_count", "stat_fact_count", "stat_event_count",
        "stat_glossary_count", "stat_updated_at",
    }


async def _make_project(conn) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO knowledge_projects (user_id, name, project_type)
        VALUES (gen_random_uuid(), 'k10-test', 'general')
        RETURNING project_id
        """
    )
    return str(row["project_id"])


@pytest.mark.asyncio
async def test_extraction_pending_unique_constraint(pool):
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        event_id = "11111111-1111-1111-1111-111111111111"
        await conn.execute(
            """
            INSERT INTO extraction_pending
              (user_id, project_id, event_id, event_type, aggregate_type, aggregate_id)
            VALUES (gen_random_uuid(), $1, $2, 'chapter.saved', 'chapter', gen_random_uuid())
            """,
            project_id, event_id,
        )
        with pytest.raises(Exception) as exc:
            await conn.execute(
                """
                INSERT INTO extraction_pending
                  (user_id, project_id, event_id, event_type, aggregate_type, aggregate_id)
                VALUES (gen_random_uuid(), $1, $2, 'chapter.saved', 'chapter', gen_random_uuid())
                """,
                project_id, event_id,
            )
        msg = str(exc.value).lower()
        assert "unique" in msg or "duplicate" in msg


@pytest.mark.asyncio
async def test_extraction_pending_partial_index(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'extraction_pending'
              AND indexname = 'idx_extraction_pending_unprocessed'
            """
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_extraction_jobs_scope_check(pool):
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        with pytest.raises(Exception) as exc:
            await conn.execute(
                """
                INSERT INTO extraction_jobs
                  (user_id, project_id, scope, llm_model, embedding_model)
                VALUES (gen_random_uuid(), $1, 'bogus', 'gpt-4', 'text-embedding-3-small')
                """,
                project_id,
            )
        assert "check" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_extraction_jobs_status_check(pool):
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        with pytest.raises(Exception) as exc:
            await conn.execute(
                """
                INSERT INTO extraction_jobs
                  (user_id, project_id, scope, status, llm_model, embedding_model)
                VALUES (gen_random_uuid(), $1, 'all', 'nonsense', 'gpt-4', 'text-embedding-3-small')
                """,
                project_id,
            )
        assert "check" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_extraction_jobs_indexes_exist(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'extraction_jobs'
              AND indexname IN ('idx_extraction_jobs_project','idx_extraction_jobs_active')
            """
        )
    names = {r["indexname"] for r in rows}
    assert names == {"idx_extraction_jobs_project", "idx_extraction_jobs_active"}


# ─── K17.9.1 — project_embedding_benchmark_runs ────────────────────────────


@pytest.mark.asyncio
async def test_benchmark_runs_table_exists(pool):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'project_embedding_benchmark_runs'
            """
        )
    assert row is not None


@pytest.mark.asyncio
async def test_benchmark_runs_unique_enforced(pool):
    """Second INSERT with same (project_id, embedding_model, run_id)
    must fail on the UNIQUE — not silently duplicate."""
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        await conn.execute(
            """
            INSERT INTO project_embedding_benchmark_runs
              (project_id, embedding_model, run_id, passed)
            VALUES ($1, 'bge-m3', 'run-1', true)
            """,
            project_id,
        )
        with pytest.raises(Exception) as exc:
            await conn.execute(
                """
                INSERT INTO project_embedding_benchmark_runs
                  (project_id, embedding_model, run_id, passed)
                VALUES ($1, 'bge-m3', 'run-1', false)
                """,
                project_id,
            )
        msg = str(exc.value).lower()
        assert "unique" in msg or "duplicate" in msg


@pytest.mark.asyncio
async def test_benchmark_runs_latest_index_exists(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'project_embedding_benchmark_runs'
              AND indexname = 'idx_benchmark_runs_project_latest'
            """
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_benchmark_runs_cascade_delete(pool):
    """Deleting a project purges its benchmark history — prevents
    orphaned rows pointing at a dead project_id."""
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        await conn.execute(
            """
            INSERT INTO project_embedding_benchmark_runs
              (project_id, embedding_model, run_id, passed)
            VALUES ($1, 'bge-m3', 'run-1', true)
            """,
            project_id,
        )
        await conn.execute(
            "DELETE FROM knowledge_projects WHERE project_id = $1",
            project_id,
        )
        remaining = await conn.fetchval(
            "SELECT count(*) FROM project_embedding_benchmark_runs WHERE project_id = $1",
            project_id,
        )
        assert remaining == 0


@pytest.mark.asyncio
async def test_benchmark_runs_passed_not_null(pool):
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        with pytest.raises(Exception) as exc:
            await conn.execute(
                """
                INSERT INTO project_embedding_benchmark_runs
                  (project_id, embedding_model, run_id)
                VALUES ($1, 'bge-m3', 'run-null-passed')
                """,
                project_id,
            )
        msg = str(exc.value).lower()
        assert "null" in msg or "not-null" in msg or "not null" in msg


@pytest.mark.asyncio
async def test_benchmark_runs_accepts_full_harness_row(pool):
    """Review-impl add: populate every column the K17.9 harness will
    eventually emit. Catches a DDL typo on any of the metric / JSONB
    columns that would silently pass the smaller existence tests but
    blow up the first real harness write."""
    import json
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        row = await conn.fetchrow(
            """
            INSERT INTO project_embedding_benchmark_runs
              (project_id, embedding_provider_id, embedding_model, run_id,
               recall_at_3, mrr, avg_score_positive, stddev,
               negative_control_pass, passed, raw_report)
            VALUES ($1, $2, 'bge-m3', 'full-row-run',
                    0.833, 0.712, 0.645, 0.041,
                    true, true, $3::jsonb)
            RETURNING benchmark_run_id, recall_at_3, mrr, avg_score_positive,
                      stddev, negative_control_pass, passed, raw_report,
                      embedding_provider_id
            """,
            project_id,
            "00000000-0000-0000-0000-000000000aaa",
            json.dumps({"queries": [{"q": "who is arthur", "top3": ["a", "b"]}]}),
        )
    assert row["benchmark_run_id"] is not None  # uuidv7 default fired
    assert row["recall_at_3"] == pytest.approx(0.833)
    assert row["mrr"] == pytest.approx(0.712)
    assert row["avg_score_positive"] == pytest.approx(0.645)
    assert row["stddev"] == pytest.approx(0.041)
    assert row["negative_control_pass"] is True
    assert row["passed"] is True
    # JSONB round-trips; asyncpg returns as str or dict depending on codec.
    parsed = (
        row["raw_report"] if isinstance(row["raw_report"], dict)
        else json.loads(row["raw_report"])
    )
    assert parsed["queries"][0]["q"] == "who is arthur"


@pytest.mark.asyncio
async def test_benchmark_runs_cascade_preserves_other_projects(pool):
    """Review-impl add: ON DELETE CASCADE on project_id must purge
    THIS project's rows without touching other projects'. A bug that
    wiped the whole table would pass the simpler cascade test."""
    async with pool.acquire() as conn:
        p1 = await _make_project(conn)
        p2 = await _make_project(conn)
        for project_id, run_id in [(p1, "p1-run"), (p2, "p2-run")]:
            await conn.execute(
                """
                INSERT INTO project_embedding_benchmark_runs
                  (project_id, embedding_model, run_id, passed)
                VALUES ($1, 'bge-m3', $2, true)
                """,
                project_id, run_id,
            )
        await conn.execute(
            "DELETE FROM knowledge_projects WHERE project_id = $1",
            p1,
        )
        p1_left = await conn.fetchval(
            "SELECT count(*) FROM project_embedding_benchmark_runs WHERE project_id = $1",
            p1,
        )
        p2_left = await conn.fetchval(
            "SELECT count(*) FROM project_embedding_benchmark_runs WHERE project_id = $1",
            p2,
        )
        assert p1_left == 0, "p1 rows should cascade on delete"
        assert p2_left == 1, "p2 rows should NOT be affected by p1's delete"


@pytest.mark.asyncio
async def test_project_cascade_deletes_extraction_rows(pool):
    async with pool.acquire() as conn:
        project_id = await _make_project(conn)
        await conn.execute(
            """
            INSERT INTO extraction_pending
              (user_id, project_id, event_id, event_type, aggregate_type, aggregate_id)
            VALUES (gen_random_uuid(), $1, gen_random_uuid(), 'chapter.saved', 'chapter', gen_random_uuid())
            """,
            project_id,
        )
        await conn.execute(
            """
            INSERT INTO extraction_jobs
              (user_id, project_id, scope, llm_model, embedding_model)
            VALUES (gen_random_uuid(), $1, 'all', 'gpt-4', 'text-embedding-3-small')
            """,
            project_id,
        )
        await conn.execute(
            "DELETE FROM knowledge_projects WHERE project_id = $1",
            project_id,
        )
        pending = await conn.fetchval(
            "SELECT count(*) FROM extraction_pending WHERE project_id = $1",
            project_id,
        )
        jobs = await conn.fetchval(
            "SELECT count(*) FROM extraction_jobs WHERE project_id = $1",
            project_id,
        )
        assert pending == 0
        assert jobs == 0
