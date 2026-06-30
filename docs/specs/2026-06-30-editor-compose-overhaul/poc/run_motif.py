import asyncio, sys
from uuid import UUID
sys.path.insert(0, "/app")
from app.config import settings
from app.db.pool import create_pool, get_pool
from app.db.repositories.motif_retrieve import MotifRetriever
from app.clients.llm_client import get_llm_client
from app.engine.motif_plan import select_arc_motifs

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
BOOK = UUID("019f1783-ebb4-78de-ac9d-0dfba6539b7c")
PROJ = UUID("019f1783-ecca-7331-afab-9543762a8b68")

async def main():
    await create_pool(settings.composition_db_url)
    premise = open("/tmp/premise.txt", encoding="utf-8").read()
    retr = MotifRetriever(get_pool())
    llm = get_llm_client()
    selected = await select_arc_motifs(
        llm, retr, user_id=USER, book_id=BOOK, project_id=PROJ,
        premise=premise, genre_tags=["xianxia"], source_language="vi",
        model_source="user_model", model_ref=MODEL)
    print("SELECTED arc motifs:", len(selected))
    for m in selected:
        print(f"\n  [{m.code}] {m.name}")
        print(f"      role: {m.arc_role}")
        print(f"      why:  {m.why}")

asyncio.run(main())
