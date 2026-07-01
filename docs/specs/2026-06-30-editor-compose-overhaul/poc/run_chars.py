import asyncio, sys, json
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.cast_plan import propose_cast
from app.engine.character_plan import plan_character_arcs

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

async def main():
    premise = open("/tmp/premise.txt", encoding="utf-8").read()
    d = json.load(open("/tmp/plan.json", encoding="utf-8"))
    beats = [c["chapter"].get("beat_role") for c in d["response"]["result"]["chapters"]]
    llm = get_llm_client()
    cast_objs = await propose_cast(llm, user_id=USER, model_source="user_model", model_ref=MODEL,
                                   premise=premise, source_language="vi", genre_tags=["xianxia"])
    cast = [{"name": c.name, "role": c.role, "is_new": c.is_new} for c in cast_objs]
    arcs = await plan_character_arcs(llm, user_id=USER, model_source="user_model", model_ref=MODEL,
                                     premise=premise, cast=cast, beat_roles=beats, source_language="vi")
    print("beats:", beats)
    print("character arcs:", len(arcs))
    for a in arcs:
        intro = (f"intro@ch{a.introduce_at_chapter}"
                 if a.introduce_at_chapter and a.introduce_at_chapter > 1 else "from start")
        print(f"\n  {a.name} ({a.role}) — {intro}")
        print(f"      {a.arc[:120]}")

asyncio.run(main())
