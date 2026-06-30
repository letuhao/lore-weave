import asyncio, sys, json
from uuid import UUID
sys.path.insert(0, "/app")
from app.config import settings
from app.db.pool import create_pool, get_pool
from app.db.repositories.motif_retrieve import MotifRetriever
from app.clients.llm_client import get_llm_client
from app.clients.kal_client import get_kal_client
from app.engine.plan import ChapterPlan
from app.engine.motif_plan import select_arc_motifs
from app.engine.character_plan import plan_character_arcs
from app.engine.grounded_plan import grounded_decompose

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
BOOK = UUID("019f1783-ebb4-78de-ac9d-0dfba6539b7c")
PROJ = UUID("019f1783-ecca-7331-afab-9543762a8b68")

async def main():
    await create_pool(settings.composition_db_url)
    premise = open("/tmp/premise.txt", encoding="utf-8").read()
    raw = json.load(open("/tmp/plan.json", encoding="utf-8"))["response"]["result"]["chapters"]
    chapters = [ChapterPlan(chapter_id=c["chapter"]["chapter_id"], title=c["chapter"]["title"],
                            sort_order=i + 1, beat_role=c["chapter"].get("beat_role"),
                            intent=c["chapter"].get("intent", "")) for i, c in enumerate(raw)]
    beats = [ch.beat_role for ch in chapters]
    llm = get_llm_client()
    kal = get_kal_client()

    # canonical cast = the KAL roster (entity_id+name); is_new inferred by premise membership
    roster = await kal.roster(BOOK, user_id=UUID(USER))
    cast_decompose = [{"entity_id": e["entity_id"], "name": e["name"]} for e in roster]
    cast_chars = [{"name": e["name"], "role": "", "is_new": e["name"] not in premise} for e in roster]

    # Stage 1 — motifs
    motifs_sel = await select_arc_motifs(llm, MotifRetriever(get_pool()), user_id=USER, book_id=BOOK,
                                         project_id=PROJ, premise=premise, genre_tags=["xianxia"],
                                         source_language="vi", model_source="user_model", model_ref=MODEL)
    motifs = [{"name": m.name, "arc_role": m.arc_role} for m in motifs_sel]
    # Stage 3 — char arcs + intro schedule
    arcs = await plan_character_arcs(llm, user_id=USER, model_source="user_model", model_ref=MODEL,
                                     premise=premise, cast=cast_chars, beat_roles=beats, source_language="vi")
    arc_dicts = [{"name": a.name, "introduce_at_chapter": a.introduce_at_chapter} for a in arcs]
    print("motifs:", [m["name"] for m in motifs])
    print("intros:", {a.name: a.introduce_at_chapter for a in arcs if a.introduce_at_chapter and a.introduce_at_chapter > 1})

    # Stage 4 — grounded decompose
    res = await grounded_decompose(llm, user_id=USER, model_source="user_model", model_ref=MODEL,
                                   premise=premise, arc_title="Arc 1", beats=[{"key": b, "purpose": ""} for b in set(beats) if b],
                                   chapters=chapters, cast=cast_decompose, motifs=motifs, char_arcs=arc_dicts,
                                   k_ceiling=3, high_threshold=70, min_scenes=2, max_scenes=4, source_language="vi")
    byid = {e["entity_id"]: e["name"] for e in roster}
    tot = sum(len(c.scenes) for c in res.chapters)
    withcast = sum(1 for c in res.chapters for s in c.scenes if s.present_entity_ids)
    print(f"\nGROUNDED PLAN: {len(res.chapters)} ch, {tot} scenes, {withcast} with present cast")
    for i, c in enumerate(res.chapters[:5], 1):
        print(f"\n=== CH{i:02d} [{c.chapter.beat_role}] tensions={[s.tension for s in c.scenes]}")
        for j, s in enumerate(c.scenes, 1):
            names = [byid.get(x, x[:6]) for x in s.present_entity_ids]
            print(f"  S{j} ({s.tension}) [{','.join(names) or '-'}]: {s.synopsis[:95]}")

asyncio.run(main())
