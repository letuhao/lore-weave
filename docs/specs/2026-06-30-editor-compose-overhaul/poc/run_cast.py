import asyncio, sys
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.cast_plan import propose_cast

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

async def main():
    premise = open("/tmp/premise.txt", encoding="utf-8").read()
    llm = get_llm_client()
    cast = await propose_cast(llm, user_id=USER, model_source="user_model", model_ref=MODEL,
                              premise=premise, source_language="vi", genre_tags=["xianxia"])
    named = sum(1 for c in cast if not c.is_new)
    print(f"CAST proposed: {len(cast)}  (named={named}, new={len(cast)-named})")
    for c in cast:
        tag = "NEW" if c.is_new else "named"
        print(f"\n  [{tag:>5}] {c.name}  — {c.role} / {c.archetype}")
        if c.summary: print(f"          {c.summary[:80]}")
        if c.relationships: print(f"          rel: {c.relationships[:80]}")
        if c.traits: print(f"          traits: {', '.join(c.traits[:6])}")

asyncio.run(main())
