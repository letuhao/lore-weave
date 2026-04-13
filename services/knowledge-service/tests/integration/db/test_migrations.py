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
