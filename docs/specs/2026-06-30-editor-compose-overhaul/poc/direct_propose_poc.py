"""POC the user's diagnosis: a SIMPLE high-recall judge that outputs {original, replacement,
explanation} directly (like a bare prompt) — NO verify/vote pre-filter — surfaces far more
actionable edits than our over-filtered pipeline. The human gate (M6) does the filtering.
Same $0 Gemma 4 26B. Run on CH1 raw."""
import asyncio, sys, json, re
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.clients.eval_client import extract_judge_content
from app.engine.self_heal import locate_span

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
NO_THINK = {"reasoning_effort": "none", "chat_template_kwargs": {"thinking": False, "enable_thinking": False}}
TEXT = open("/tmp/drive_ch01_raw.txt", encoding="utf-8").read()

# Light canon = cast names + convention as CONTEXT (so canon errors are catchable), but NO
# suppression guardrails ("don't infer / already-explained") — those killed recall.
CANON = """Bối cảnh tiên hiệp hắc ám. Nhân vật: Lâm Uyển (nữ chính, đích nữ bị ghẻ lạnh, bị vu oan),
Lâm Chấn Nhạc (phụ thân, gia chủ lạnh lùng), Tô Yến (mẫu thân RUỘT, LUÔN khinh miệt con gái — chưa
từng che chở), Lâm Tử Hàn (huynh trưởng thiên tài), Hắc Sát Lão Nhân (sát thủ ngoài gia tộc).
Quy ước xưng hô tiên hiệp: dùng hắn/y/nàng/lão/thị; KHÔNG dùng "ông/bà/cô ấy/anh ấy"; người trực
tiếp nói không tự xưng ngôi ba ("lệnh của mẫu thân ngươi" là SAI)."""

SYSTEM = (
    "Bạn là biên tập tiểu thuyết tiên hiệp khắt khe. Tìm MỌI điểm bất thường trong CHƯƠNG: lỗi "
    "logic/nhân-quả, chuyển cảnh gãy, diễn đạt vụng/tối nghĩa, lặp thông tin, XƯNG HÔ sai (đại từ "
    "hiện đại, tự xưng ngôi ba, tên/vai vế sai), mâu thuẫn nhân vật so với bối cảnh, chính tả. "
    "Với MỖI điểm trả một object JSON: "
    '{"type": loại lỗi, '
    '"original": TRÍCH NGUYÊN VĂN một đoạn NGẮN 4-20 chữ COPY ĐÚNG TỪNG KÝ TỰ từ chương (để tìm-thay tự động), '
    '"replacement": câu/cụm đã sửa (độ dài tương đương, KHÔNG viết lại cả đoạn), '
    '"explanation": lý do ngắn. '
    "Liệt kê HẾT các điểm bạn thấy (đừng tự ý bỏ bớt). Trả về DUY NHẤT một mảng JSON, không văn xuôi.\n\n"
    "BỐI CẢNH:\n" + CANON
)

def parse(content):
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        # salvage truncated array
        arr = []
        for obj in re.findall(r"\{[^{}]*\}", content, re.DOTALL):
            try:
                arr.append(json.loads(obj))
            except Exception:
                pass
    return [r for r in arr if isinstance(r, dict)]

async def main():
    llm = get_llm_client()
    job = await llm.submit_and_wait(
        user_id=USER, operation="chat", model_source="user_model", model_ref=MODEL,
        input={"messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": "CHƯƠNG:\n\n" + TEXT}],
               "response_format": {"type": "text"}, "temperature": 0.4,
               "max_tokens": 3000, **NO_THINK},
        job_meta={"usage_purpose": "direct_propose_poc", "extractor": "poc"})
    raw = parse(extract_judge_content(job.result) or "")
    print("judge returned %d findings\n" % len(raw))
    kept = 0
    for f in raw:
        orig = (f.get("original") or "").strip()
        loc = locate_span(orig, TEXT)
        tag = "LOCATED" if loc else "drop(no-quote)"
        if loc:
            kept += 1
        print("[%-14s] %-16s «%s»" % (tag, (f.get("type") or "")[:16], orig[:46]))
        print("     → %s" % (f.get("replacement") or "")[:80])
        print("     ↳ %s" % (f.get("explanation") or "")[:80])
    print("\nSUMMARY: %d findings, %d locatable (splice-ready) — vs pipeline's ~4 (mostly pronouns)." % (len(raw), kept))

asyncio.run(main())
