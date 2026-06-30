import asyncio, sys
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.self_heal import run_self_heal

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

def metrics(t):
    l = t.lower()
    return dict(chars=len(t), lanh=l.count("lạnh"), phe_vat=l.count("phế vật"),
                ma_co=l.count("cửu u ma cơ"))

async def main():
    text = open("/tmp/ch1.txt", encoding="utf-8").read()
    llm = get_llm_client()
    healed, rep = await run_self_heal(
        llm, user_id=USER, model_source="user_model", model_ref=MODEL,
        chapter=text, source_language="vi")
    open("/tmp/healed_ch1.txt", "w", encoding="utf-8").write(healed)
    print(f"JUDGE findings={rep.rejudge_before} located={rep.located} "
          f"edits_applied={rep.edits_applied} REJUDGE_after={rep.rejudge_after}")
    for f in rep.findings:
        tag = "EDIT" if f.edited else (f.skip_reason or "?")
        print(f"  [{tag:>12}] {f.type}: {f.span[:55]}")
    print("BEFORE", metrics(text))
    print("AFTER ", metrics(healed))
    print("len ratio %.3f" % (len(healed) / max(1, len(text))))

asyncio.run(main())
