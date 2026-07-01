"""Regenerate (heal-correct) CH1 with the full cheap-stack: grounded judge + vote(5) +
verify + mechanical prefilter — on the $0 local model. Goal: fewest errors before the
human / stronger-model gate, NOT perfection."""
import asyncio, sys
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.self_heal import run_self_heal

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"   # Gemma 4 26B, local, $0
TEXT = open("/tmp/ch01_prose.txt", encoding="utf-8").read()

BIBLE = """THẾ LOẠI: Tiên hiệp HẮC ÁM — trọng tu luyện/chiến đấu/báo thù. KHÔNG phải ngôn tình ngược.

QUY ƯỚC XƯNG HÔ (tiên hiệp):
- Ngôi kể dùng: hắn / y / nàng / lão / thị / người nọ. TUYỆT ĐỐI KHÔNG dùng đại từ HIỆN ĐẠI làm ngôi kể: "ông", "bà", "ông ta", "bà ta", "cô ấy", "anh ấy".
- Con nói với cha mẹ tự xưng "hài nhi" / "nữ nhi", KHÔNG tự gọi mình bằng tên riêng.
- Người đang TRỰC TIẾP nói không được tự xưng ngôi ba: chính mẫu thân nói "lệnh của mẫu thân ngươi" là SAI, phải là "lệnh của ta".

CANON NHÂN VẬT (hành vi & mô tả phải khớp):
- Lâm Uyển: nữ chính, đích nữ bị ghẻ lạnh, phế vật → ma tu nghịch thiên. Bị VU OAN tội trộm linh dược (thực chất linh dược bị đánh tráo) để bảo vệ huynh trưởng. Nàng là NẠN NHÂN, không tự nguyện hy sinh; nàng thề báo thù.
- Lâm Chấn Nhạc: gia chủ, phụ thân lạnh lùng vô tình, trọng danh tiếng hơn tình thâm.
- Tô Yến: mẫu thân RUỘT (chính thất). LUÔN khinh miệt đứa con gái phế vật; thủ đoạn, thực dụng, khắt khe. CHƯA TỪNG dốc lòng che chở hay thương yêu Lâm Uyển.
- Lâm Tử Hàn: huynh trưởng, thiên tài được sủng ái, coi thường muội muội, đứng nhìn nàng bị hại.
- Hắc Sát Lão Nhân: sát thủ tàn độc NGOÀI gia tộc, được phái đến diệt khẩu (dùng người ngoài để gia tộc phủi tay)."""

async def main():
    llm = get_llm_client()
    healed, rep = await run_self_heal(
        llm, user_id=USER, model_source="user_model", model_ref=MODEL,
        chapter=TEXT, source_language="vi",
        canon=BIBLE, vote_k=5, min_votes=2, verify=True, prefilter=True)
    open("/tmp/ch01_healed_v2.txt", "w", encoding="utf-8").write(healed)
    print("len: %d -> %d  (x%.3f)" % (len(TEXT), len(healed), len(healed) / len(TEXT)))
    print("findings(voted)=%d  located=%d  edits=%d  rejudge %s -> %s\n" % (
        rep.rejudge_before, rep.located, rep.edits_applied, rep.rejudge_before, rep.rejudge_after))
    for f in rep.findings:
        tag = "EDIT" if f.edited else (f.skip_reason or "?")
        print("  [%-9s] %-10s «%s»" % (f.type[:9], tag, f.span[:48]))
        print("              ↳ %s" % f.issue[:90])

asyncio.run(main())
