"""Re-run all 12 chapters with the DIRECT auditor + compare WITH vs WITHOUT the re-ranker.
The auditor runs once per chapter (rerank=True gives the per-edit recommend); then:
  - WITHOUT rerank (autonomous) = apply the deterministic edits only (semantic left for the human);
  - WITH rerank (autonomous)    = apply deterministic + the semantic edits the re-ranker approved.
Reports per-chapter counts + every semantic edit's approve/decline + reason. $0 local Gemma."""
import asyncio, sys, glob, re, json
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.self_heal import propose_edits_direct, apply_self_heal_edits
from app.engine.heal_canon import render_canon, convention_for

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
CAST = [
 {"name":"Lâm Uyển","role":"protagonist","relationships":"con của Lâm Chấn Nhạc & Tô Yến; muội của Lâm Tử Hàn","description":"đích nữ bị ghẻ lạnh, phế vật bị vu oan → ma tu nghịch thiên, thề báo thù"},
 {"name":"Lâm Chấn Nhạc","role":"phụ thân","relationships":"gia chủ; phụ thân Lâm Uyển","description":"gia chủ lạnh lùng vô tình, trọng danh tiếng"},
 {"name":"Tô Yến","role":"mẫu thân","relationships":"mẫu thân ruột của Lâm Uyển","description":"LUÔN khinh miệt con gái phế vật, CHƯA TỪNG che chở"},
 {"name":"Lâm Tử Hàn","role":"huynh trưởng","relationships":"huynh trưởng của Lâm Uyển","description":"thiên tài được sủng ái, coi thường muội muội"},
 {"name":"Cửu U Ma Cơ","role":"mentor","description":"ma nữ thượng cổ, chủ cổ thư, dẫn dắt Lâm Uyển"},
 {"name":"Thanh Vân Tông","role":"phản diện","description":"chính đạo giả tạo, truy sát ma tu"},
 {"name":"Mộ Dung Tuyết","role":"foil","description":"thiên kim danh môn chính phái"},
 {"name":"Diệp Phàm","role":"ally","description":"tu sĩ ma đạo ẩn danh giúp Lâm Uyển"},
 {"name":"Hắc Sát Lão Nhân","role":"phản diện","description":"sát thủ NGOÀI gia tộc, một lão già rình cướp ma công"},
]

async def main():
    llm = get_llm_client()
    canon = render_canon(CAST, convention=convention_for(["tiên hiệp"], "vi"))
    rows = []
    for f in sorted(glob.glob("/tmp/drive_ch*_raw.txt")):
        ci = re.search(r"ch(\d+)_raw", f).group(1)
        text = open(f, encoding="utf-8").read()
        if not text.strip():
            continue
        proposals, rep = await propose_edits_direct(
            llm, text, user_id=USER, model_source="user_model", model_ref=MODEL,
            canon=canon, source_language="vi", rerank=True)
        det = [p for p in proposals if p.tier == "deterministic"]
        sem = [p for p in proposals if p.tier == "semantic"]
        sem_ok = [p for p in sem if p.recommended]
        norr = apply_self_heal_edits(text, proposals, set(p.id for p in det))
        rr = apply_self_heal_edits(text, proposals, set(p.id for p in proposals if p.recommended))
        open("/tmp/drive_ch%s_norerank.txt" % ci, "w", encoding="utf-8").write(norr)
        open("/tmp/drive_ch%s_rerank.txt" % ci, "w", encoding="utf-8").write(rr)
        rows.append(dict(ch=ci, found=rep.rejudge_before, located=len(proposals), det=len(det),
                         sem=len(sem), sem_approved=len(sem_ok),
                         norr_edits=len(det), rr_edits=len(det) + len(sem_ok),
                         norr_ratio=round(len(norr) / len(text), 3),
                         rr_ratio=round(len(rr) / len(text), 3)))
        print("CH%s | found=%d located=%d (det=%d sem=%d) | rerank approved %d/%d sem | "
              "auto-edits norerank=%d rerank=%d | x %.3f/%.3f" % (
              ci, rep.rejudge_before, len(proposals), len(det), len(sem), len(sem_ok), len(sem),
              len(det), len(det) + len(sem_ok), rows[-1]["norr_ratio"], rows[-1]["rr_ratio"]), flush=True)
        for p in sem:
            print("    sem[%s] «%s» -> %s | %s" % (
                "APPROVE" if p.recommended else "decline", p.before[:24], p.after[:28],
                (p.rerank_reason or "")[:46]), flush=True)
    json.dump(rows, open("/tmp/compare_rerank_summary.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("COMPARE_DONE", flush=True)

asyncio.run(main())
