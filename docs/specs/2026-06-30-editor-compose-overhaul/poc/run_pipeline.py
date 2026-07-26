import asyncio, sys, json
from uuid import UUID
sys.path.insert(0, "/app")
from app.config import settings
from app.db.pool import create_pool, get_pool
from app.db.repositories.motif_retrieve import MotifRetriever
from app.clients.llm_client import get_llm_client
from app.clients.glossary_client import get_glossary_client
from app.clients.kal_client import get_kal_client
from app.engine.plan import ChapterPlan
from app.engine.planning_pipeline import run_planning_pipeline

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
BOOK = UUID("019f1783-ebb4-78de-ac9d-0dfba6539b7c")
PROJ = UUID("019f1783-ecca-7331-afab-9543762a8b68")

async def main():
    await create_pool(settings.composition_db_url)
    premise = open("/tmp/premise.txt", encoding="utf-8").read()
    raw = json.load(open("/tmp/plan.json", encoding="utf-8"))["response"]["result"]["chapters"]
    chapters = [ChapterPlan(chapter_id=c["chapter"]["chapter_id"], title=c["chapter"]["title"],
                            sort_order=i + 1, beat_role=None, intent="") for i, c in enumerate(raw)]
    seen = []
    for c in raw:
        b = c["chapter"].get("beat_role")
        if b and b not in seen:
            seen.append(b)
    beats = [{"key": k, "purpose": k.replace("_", " ")} for k in seen]

    res = await run_planning_pipeline(
        get_llm_client(), MotifRetriever(get_pool()), get_glossary_client(), get_kal_client(),
        user_id=USER, book_id=BOOK, project_id=PROJ, premise=premise, beats=beats, chapters=chapters,
        genre_tags=["xianxia"], model_source="user_model", model_ref=MODEL,
        k_ceiling=3, high_threshold=70, min_scenes=2, max_scenes=4, source_language="vi", self_heal=True)
    d = res.decompose
    tot = sum(len(c.scenes) for c in d.chapters)
    withcast = sum(1 for c in d.chapters for s in c.scenes if s.present_entity_ids)
    hr = res.heal_report
    print("PIPELINE OK: cast=%d motifs=%d arcs=%d | %d ch, %d scenes, %d with present | heal edits=%s/%s findings"
          % (len(res.cast), len(res.motifs), len(res.char_arcs), len(d.chapters), tot, withcast,
             hr.edits_applied if hr else None, len(hr.findings) if hr else 0))
    print("motifs:", [m["name"][:22] for m in res.motifs])
    print("intros:", {a["name"]: a["introduce_at_chapter"] for a in res.char_arcs
                      if a["introduce_at_chapter"] and a["introduce_at_chapter"] > 1})
    print("\nPLAN-HEAL findings:")
    for f in (hr.findings[:8] if hr else []):
        tag = "EDIT" if f.applied else (f.skip_reason or "?")
        print("  [%8s] CH%dS%d %s: %s" % (tag, f.chapter, f.scene, f.type, f.issue[:70]))

asyncio.run(main())
