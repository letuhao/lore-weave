import asyncio, sys
from uuid import UUID
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.clients.glossary_client import get_glossary_client
from app.engine.cast_plan import propose_cast

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
BOOK = "019f1783-ebb4-78de-ac9d-0dfba6539b7c"

async def main():
    premise = open("/tmp/premise.txt", encoding="utf-8").read()
    llm = get_llm_client()
    cast = await propose_cast(llm, user_id=USER, model_source="user_model", model_ref=MODEL,
                              premise=premise, source_language="vi", genre_tags=["xianxia"])
    print("proposed:", len(cast))
    gl = get_glossary_client()
    ents = [{"kind_code": "character", "name": c.name, "evidence": c.summary or c.role} for c in cast]
    seeded = await gl.seed_entities(UUID(BOOK), source_language="vi", entities=ents)
    print("seeded:", len(seeded))
    for e in seeded:
        print("  ", e.get("name"), e.get("entity_id"), e.get("status"))

asyncio.run(main())
