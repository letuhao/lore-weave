"""Validate (A) verify-vote + (B) canon-from-pipeline-cast end-to-end on the $0 local model.
Renders the heal canon via heal_canon.render_canon from the PERSISTED cast (the same
attributes the planning pipeline seeded), then heals CH1 with verify_k=3 — confirming the
CH01 'mẫu thân ngươi' false-refute is gone."""
import asyncio, sys
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.self_heal import run_self_heal
from app.engine.heal_canon import render_canon, convention_for

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

# The persisted cast (name + glossary attribute codes) — exactly what render_canon receives
# from the pipeline's seeded cast (see plan-export/00_overview.md cast table).
CAST = [
 {"name":"Lâm Uyển","role":"protagonist","personality":"Kiên cường; Quyết đoán; Lạnh lùng; Nghịch thiên cải mệnh; Người bị ruồng bỏ","relationships":"Con gái của Lâm Chấn Nhạc và Tô Yến; Muội muội của Lâm Tử Hàn; Truyền nhân của Cửu U Ma Cơ","description":"Đích nữ bị ghẻ lạnh của Lâm gia, từ phế vật trở thành ma tu nghịch thiên."},
 {"name":"Lâm Chấn Nhạc","role":"antagonist","personality":"Lạnh lùng; Trọng lợi; Quyền uy; Phụ thân vô tình","relationships":"Gia chủ Lâm gia; Phụ thân của Lâm Uyển, Lâm Tử Hàn; Phu quân của Tô Yến","description":"Gia chủ Lâm gia, người coi trọng danh tiếng gia tộc hơn tình thâm."},
 {"name":"Tô Yến","role":"antagonist","personality":"Thủ đoạn; Thực dụng; Khắt khe; Mẫu thân sắc sảo","relationships":"Chính thất Lâm gia; Mẫu thân của Lâm Uyển và Lâm Tử Hàn; Phu nhân của Lâm Chấn Nhạc","description":"Người mẹ coi trọng danh dự gia tộc, luôn khinh miệt đứa con gái phế vật."},
 {"name":"Lâm Tử Hàn","role":"rival","personality":"Kiêu ngạo; Thiên tư cao; Tự phụ; Thiên tài sủng ái","relationships":"Huynh trưởng của Lâm Uyển; Con trai của Lâm Chấn Nhạc và Tô Yến","description":"Thiên tài của Lâm gia, người luôn đứng trên đỉnh cao và coi thường muội muội."},
 {"name":"Cửu U Ma Cơ","role":"mentor","personality":"Thần bí; Tàn nhẫn; Uy áp cực lớn; Ma tôn thượng cổ","relationships":"Chủ nhân cuốn cổ thư; Linh hồn dẫn dắt Lâm Uyển","description":"Ma nữ thượng cổ, người truyền thừa ma công cho Lâm Uyển."},
 {"name":"Thanh Vân Tông","role":"antagonist","personality":"Đạo đức giả; Khắt khe; Thế lực lớn; Chính đạo giả tạo","relationships":"Tông môn chính đạo đối đầu với ma tu","description":"Thế lực chính đạo luôn khinh miệt và truy sát Lâm Uyển sau khi nàng tu ma."},
 {"name":"Mộ Dung Tuyết","role":"foil","personality":"Kiêu kỳ; Thanh cao; Bề ngoài hoàn mỹ","relationships":"Đối thủ của Lâm Uyển","description":"Thiên kim danh môn chính phái."},
 {"name":"Diệp Phàm","role":"ally","personality":"Trung thành; Ẩn nhẫn; Thông tuệ; Kẻ lẩn trốn","relationships":"Đồng đạo tu ma; Người hỗ trợ Lâm Uyển trong bóng tối","description":"Một tu sĩ ma đạo ẩn danh, giúp Lâm Uyển thu thập tài nguyên tu luyện."},
 {"name":"Hắc Sát Lão Nhân","role":"antagonist","personality":"Tàn độc; Tham lam; Thủ đoạn quỷ quyệt; Kẻ săn lùng","relationships":"Trưởng lão ẩn thế của một thế lực hắc ám; Kẻ muốn đoạt xá Lâm Uyển","description":"Một lão quái vật tu luyện tà thuật, luôn rình rập để cướp đoạt ma công của Lâm Uyển."},
]

async def main():
    llm = get_llm_client()
    canon = render_canon(CAST, convention=convention_for(["tiên hiệp"], "vi"))   # (B)
    print("=== CANON rendered from pipeline cast (%d chars) ===" % len(canon))
    print(canon[:600], "...\n")
    prose = open("/tmp/drive_ch01_raw.txt", encoding="utf-8").read()
    healed, rep = await run_self_heal(
        llm, user_id=USER, model_source="user_model", model_ref=MODEL,
        chapter=prose, source_language="vi", canon=canon,
        vote_k=5, min_votes=2, verify=True, verify_k=3, prefilter=True)   # (A) verify_k=3
    open("/tmp/drive_ch01_healed_v3.txt", "w", encoding="utf-8").write(healed)
    edited = [x for x in rep.findings if x.edited]
    refuted = [x for x in rep.findings if x.skip_reason == "refuted"]
    print("CH01 | x%.3f | voted=%d edits=%d refuted=%d | rejudge %d->%s" % (
        len(healed)/len(prose), rep.rejudge_before, rep.edits_applied, len(refuted),
        rep.rejudge_before, rep.rejudge_after))
    for x in rep.findings:
        tag = "EDIT" if x.edited else (x.skip_reason or "?")
        print("  [%-12s] %-9s %s" % (x.type[:12], tag, x.issue[:66]))
    print("\nRESIDUAL 'mẫu thân ngươi' present? ->", "mẫu thân ngươi" in healed)

asyncio.run(main())
