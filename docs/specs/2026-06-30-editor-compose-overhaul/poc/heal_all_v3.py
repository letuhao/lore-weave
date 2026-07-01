"""Re-drive CH1-12 with the improved stack: canon RENDERED from the cast (B) + verify_k=3
(A, majority-refute → fixes the CH01 false-refute). $0 local model. Refreshes story-export-v2."""
import asyncio, sys, glob, re, json
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.self_heal import run_self_heal
from app.engine.heal_canon import render_canon, convention_for

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

# The persisted cast (name + glossary attribute codes) — render_canon turns it into the bible.
CAST = [
 {"name":"Lâm Uyển","role":"protagonist","personality":"Kiên cường; Quyết đoán; Lạnh lùng; Nghịch thiên cải mệnh; Người bị ruồng bỏ","relationships":"Con gái của Lâm Chấn Nhạc và Tô Yến; Muội muội của Lâm Tử Hàn; Truyền nhân của Cửu U Ma Cơ","description":"Đích nữ bị ghẻ lạnh của Lâm gia, từ phế vật trở thành ma tu nghịch thiên; bị vu oan, thề báo thù."},
 {"name":"Lâm Chấn Nhạc","role":"antagonist","personality":"Lạnh lùng; Trọng lợi; Quyền uy; Phụ thân vô tình","relationships":"Gia chủ Lâm gia; Phụ thân của Lâm Uyển, Lâm Tử Hàn; Phu quân của Tô Yến","description":"Gia chủ Lâm gia, coi trọng danh tiếng gia tộc hơn tình thâm."},
 {"name":"Tô Yến","role":"antagonist","personality":"Thủ đoạn; Thực dụng; Khắt khe; Mẫu thân sắc sảo","relationships":"Chính thất Lâm gia; Mẫu thân ruột của Lâm Uyển và Lâm Tử Hàn","description":"Người mẹ ruột LUÔN khinh miệt đứa con gái phế vật; chưa từng che chở Lâm Uyển."},
 {"name":"Lâm Tử Hàn","role":"rival","personality":"Kiêu ngạo; Thiên tư cao; Tự phụ; Thiên tài sủng ái","relationships":"Huynh trưởng của Lâm Uyển; Con trai của Lâm Chấn Nhạc và Tô Yến","description":"Thiên tài được sủng ái của Lâm gia, coi thường muội muội, đứng nhìn nàng bị hại."},
 {"name":"Cửu U Ma Cơ","role":"mentor","personality":"Thần bí; Tàn nhẫn; Uy áp cực lớn; Ma tôn thượng cổ","relationships":"Chủ nhân cuốn cổ thư; Linh hồn dẫn dắt Lâm Uyển","description":"Ma nữ thượng cổ truyền thừa ma công cho Lâm Uyển; không sống cùng thời."},
 {"name":"Thanh Vân Tông","role":"antagonist","personality":"Đạo đức giả; Khắt khe; Thế lực lớn; Chính đạo giả tạo","relationships":"Tông môn chính đạo đối đầu với ma tu","description":"Thế lực chính đạo khinh miệt và truy sát Lâm Uyển sau khi nàng tu ma."},
 {"name":"Mộ Dung Tuyết","role":"foil","personality":"Kiêu kỳ; Thanh cao; Bề ngoài hoàn mỹ","relationships":"Đối thủ của Lâm Uyển","description":"Thiên kim danh môn chính phái."},
 {"name":"Diệp Phàm","role":"ally","personality":"Trung thành; Ẩn nhẫn; Thông tuệ; Kẻ lẩn trốn","relationships":"Đồng đạo tu ma; Người hỗ trợ Lâm Uyển trong bóng tối","description":"Tu sĩ ma đạo ẩn danh, giúp Lâm Uyển thu thập tài nguyên tu luyện."},
 {"name":"Hắc Sát Lão Nhân","role":"antagonist","personality":"Tàn độc; Tham lam; Thủ đoạn quỷ quyệt; Kẻ săn lùng","relationships":"Trưởng lão ẩn thế thế lực hắc ám; Kẻ muốn đoạt xá Lâm Uyển","description":"Lão quái tu tà thuật, sát thủ NGOÀI gia tộc, rình rập cướp đoạt ma công của Lâm Uyển."},
]

async def main():
    llm = get_llm_client()
    canon = render_canon(CAST, convention=convention_for(["tiên hiệp"], "vi"))
    print("canon: %d chars\n" % len(canon), flush=True)
    summary = []
    for f in sorted(glob.glob("/tmp/drive_ch*_raw.txt")):
        ci = re.search(r"ch(\d+)_raw", f).group(1)
        prose = open(f, encoding="utf-8").read()
        if not prose.strip():
            print("CH%s: empty (skip)" % ci, flush=True); continue
        healed, rep = await run_self_heal(
            llm, user_id=USER, model_source="user_model", model_ref=MODEL,
            chapter=prose, source_language="vi", canon=canon,
            vote_k=5, min_votes=2, verify=True, verify_k=3, prefilter=True)
        open("/tmp/drive_ch%s_healed_v3.txt" % ci, "w", encoding="utf-8").write(healed)
        refuted = sum(1 for x in rep.findings if x.skip_reason == "refuted")
        summary.append(dict(ch=ci, len0=len(prose), len1=len(healed),
                            ratio=round(len(healed)/len(prose), 3), voted=rep.rejudge_before,
                            edits=rep.edits_applied, refuted=refuted, rejudge_after=rep.rejudge_after))
        print("CH%s | x%.3f | voted=%d edits=%d refuted=%d | rejudge %d->%s" % (
            ci, summary[-1]["ratio"], rep.rejudge_before, rep.edits_applied, refuted,
            rep.rejudge_before, rep.rejudge_after), flush=True)
    json.dump(summary, open("/tmp/heal_v3_summary.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("HEAL_V3_ALL_DONE", flush=True)

asyncio.run(main())
