"""Drive the cheap-stack self-heal over ALL chapters (CH1-12) with a BOOK-LEVEL canon
(all 9 cast + convention) so canon errors involving later-introduced characters are
catchable too. $0 local model. Goal: fewest errors, then human/stronger gate."""
import asyncio, sys, glob, re, json
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.engine.self_heal import run_self_heal

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"   # Gemma 4 26B, local, $0

BOOK_BIBLE = """THẾ LOẠI: Tiên hiệp HẮC ÁM — trọng tu luyện/chiến đấu/báo thù. KHÔNG phải ngôn tình ngược.

QUY ƯỚC XƯNG HÔ (tiên hiệp):
- Ngôi kể dùng: hắn / y / nàng / lão / thị / người nọ. TUYỆT ĐỐI KHÔNG dùng đại từ HIỆN ĐẠI làm ngôi kể: "ông", "bà", "ông ta", "bà ta", "cô ấy", "anh ấy".
- Con nói với cha mẹ tự xưng "hài nhi" / "nữ nhi", KHÔNG tự gọi mình bằng tên riêng.
- Người đang TRỰC TIẾP nói không được tự xưng ngôi ba (mẫu thân nói "lệnh của mẫu thân ngươi" là SAI, phải là "lệnh của ta").
- Xưng hô tu tiên: gia chủ, trưởng lão, công tử, tiểu thư, đạo hữu, tiền bối, tông chủ. TRÁNH cách gọi hiện đại ("ông Lâm", "bà Tô").

CANON NHÂN VẬT (hành vi & mô tả phải khớp):
- Lâm Uyển: NỮ CHÍNH. Đích nữ Lâm gia bị ghẻ lạnh, linh căn phế vật, bị VU OAN trộm linh dược → bị trục xuất, suýt chết, được cổ thư của Cửu U Ma Cơ, tu ma công nghịch thiên, quyết đạt tới hoàn mỹ, thề báo thù. Kiên cường, lạnh lùng, quyết đoán. Là NẠN NHÂN bị hãm, KHÔNG tự nguyện hy sinh.
- Lâm Chấn Nhạc: gia chủ Lâm gia, phụ thân LẠNH LÙNG VÔ TÌNH, trọng danh tiếng gia tộc hơn tình thâm.
- Tô Yến: mẫu thân RUỘT (chính thất). LUÔN khinh miệt đứa con gái phế vật; thủ đoạn, thực dụng, khắt khe. CHƯA TỪNG dốc lòng che chở hay thương yêu Lâm Uyển.
- Lâm Tử Hàn: huynh trưởng, thiên tài được sủng ái (được ban Trúc Cơ Đan), kiêu ngạo tự phụ, coi thường muội muội, đứng nhìn nàng bị hại.
- Cửu U Ma Cơ: MA NỮ THƯỢNG CỔ, chủ nhân cuốn cổ thư, linh hồn/ý niệm dẫn dắt Lâm Uyển tu ma công. Thần bí, tàn nhẫn, uy áp cực lớn. KHÔNG phải người sống cùng thời với nàng.
- Thanh Vân Tông: thế lực CHÍNH ĐẠO giả tạo, đạo đức giả, khắt khe; về sau khinh miệt và truy sát Lâm Uyển vì nàng tu ma.
- Mộ Dung Tuyết: thiên kim danh môn CHÍNH PHÁI, kiêu kỳ, thanh cao, bề ngoài hoàn mỹ; đối thủ (foil) của Lâm Uyển.
- Diệp Phàm: tu sĩ MA ĐẠO ẩn danh, đồng minh hỗ trợ Lâm Uyển trong bóng tối (thu thập tài nguyên tu luyện); trung thành, ẩn nhẫn, thông tuệ.
- Hắc Sát Lão Nhân: lão quái tu TÀ THUẬT, sát thủ tàn độc NGOÀI Lâm gia; tham lam, thủ đoạn quỷ quyệt; rình rập để đoạt xá / cướp ma công của Lâm Uyển."""

async def main():
    llm = get_llm_client()
    summary = []
    for f in sorted(glob.glob("/tmp/drive_ch*_raw.txt")):
        ci = re.search(r"ch(\d+)_raw", f).group(1)
        prose = open(f, encoding="utf-8").read()
        if not prose.strip():
            print("CH%s: empty (skip)" % ci, flush=True)
            continue
        healed, rep = await run_self_heal(
            llm, user_id=USER, model_source="user_model", model_ref=MODEL,
            chapter=prose, source_language="vi", canon=BOOK_BIBLE,
            vote_k=5, min_votes=2, verify=True, prefilter=True)
        open("/tmp/drive_ch%s_healed_v2.txt" % ci, "w", encoding="utf-8").write(healed)
        edited = [x for x in rep.findings if x.edited]
        refuted = [x for x in rep.findings if x.skip_reason == "refuted"]
        summary.append(dict(ch=ci, len0=len(prose), len1=len(healed),
                            ratio=round(len(healed) / len(prose), 3),
                            voted=rep.rejudge_before, located=rep.located,
                            edits=rep.edits_applied, refuted=len(refuted),
                            rejudge_after=rep.rejudge_after))
        print("CH%s | x%.3f | voted=%d located=%d edits=%d refuted=%d | rejudge %d->%s" % (
            ci, summary[-1]["ratio"], rep.rejudge_before, rep.located,
            rep.edits_applied, len(refuted), rep.rejudge_before, rep.rejudge_after), flush=True)
        for x in edited:
            print("    EDIT [%-12s] %s" % (x.type[:12], x.issue[:72]), flush=True)
    json.dump(summary, open("/tmp/heal_v2_summary.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("HEAL_V2_ALL_DONE", flush=True)

asyncio.run(main())
