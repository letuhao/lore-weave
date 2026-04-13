import asyncpg

_knowledge_pool: asyncpg.Pool | None = None
_glossary_pool: asyncpg.Pool | None = None


async def create_pools(knowledge_dsn: str, glossary_dsn: str) -> None:
    """Create both pools. If the second pool fails, the first is cleaned up."""
    global _knowledge_pool, _glossary_pool
    _knowledge_pool = await asyncpg.create_pool(
        knowledge_dsn,
        min_size=2,
        max_size=10,
        command_timeout=5,
    )
    try:
        _glossary_pool = await asyncpg.create_pool(
            glossary_dsn,
            min_size=2,
            max_size=10,
            command_timeout=5,
        )
    except Exception:
        await _knowledge_pool.close()
        _knowledge_pool = None
        raise


async def close_pools() -> None:
    global _knowledge_pool, _glossary_pool
    if _knowledge_pool:
        await _knowledge_pool.close()
        _knowledge_pool = None
    if _glossary_pool:
        await _glossary_pool.close()
        _glossary_pool = None


def get_knowledge_pool() -> asyncpg.Pool:
    if _knowledge_pool is None:
        raise RuntimeError("knowledge pool not initialised")
    return _knowledge_pool


def get_glossary_pool() -> asyncpg.Pool:
    if _glossary_pool is None:
        raise RuntimeError("glossary pool not initialised")
    return _glossary_pool
