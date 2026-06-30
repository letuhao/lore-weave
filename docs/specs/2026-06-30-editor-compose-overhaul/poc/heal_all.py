import asyncio, sys, glob, re
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.self_heal import run_self_heal

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

async def main():
    llm = get_llm_client()
    for f in sorted(glob.glob("/tmp/drive_ch*_raw.txt")):
        ci = re.search(r"ch(\d+)_raw", f).group(1)
        prose = open(f, encoding="utf-8").read()
        if not prose.strip():
            print("CH%s: empty (skip)" % ci, flush=True)
            continue
        healed, rep = await run_self_heal(llm, user_id=USER, model_source="user_model",
                                          model_ref=MODEL, chapter=prose, source_language="vi")
        open("/tmp/drive_ch%s_healed.txt" % ci, "w", encoding="utf-8").write(healed)
        edited = [x.type for x in rep.findings if x.edited]
        print("CH%s: %d->%d chars | findings=%d edits=%d (%s)" % (
            ci, len(prose), len(healed), rep.rejudge_before, rep.edits_applied,
            ", ".join(edited[:5])), flush=True)
    print("HEAL ALL done")

asyncio.run(main())
