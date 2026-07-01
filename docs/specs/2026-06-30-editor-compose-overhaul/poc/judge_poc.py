"""JUDGE POC — run INSIDE the composition-service container.
Reads /tmp/ch1.txt, asks Gemma to return JSON findings (each with a VERBATIM span),
then verifies how many spans actually locate in the chapter (the make-or-break risk)."""
import asyncio, json, re, sys

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"

SYSTEM = (
    "Bạn là biên tập viên tiểu thuyết khó tính. Đọc CHƯƠNG dưới đây và liệt kê các LỖI cụ thể "
    "cần sửa (lặp motif/hình ảnh, lặp thông tin đã nói, lỗ hổng logic/nhân quả, vòng lặp cảm xúc, "
    "nhân vật một chiều, nhịp văn). Với MỖI lỗi, trả về một đối tượng JSON gồm: "
    '"type" (loại lỗi), "span" (TRÍCH NGUYÊN VĂN 6-15 từ COPY CHÍNH XÁC từng ký tự từ chương — '
    "KHÔNG diễn giải lại, KHÔNG tóm tắt — để máy định vị được), \"issue\" (lỗi là gì), "
    '"fix" (cách sửa ngắn gọn). Chỉ chọn 6-10 lỗi rõ nhất. '
    'Trả về DUY NHẤT một mảng JSON: [{"type":...,"span":...,"issue":...,"fix":...}]. Không thêm lời nào.'
)

def locate(span, text):
    if not span: return "empty"
    if span in text: return "exact"
    # whitespace-normalized
    n = lambda s: re.sub(r"\s+", " ", s).strip()
    if n(span) in n(text): return "ws"
    # fuzzy: first 6 words contiguous
    ws = n(span).split()
    if len(ws) >= 4 and " ".join(ws[:6]) in n(text): return "prefix6"
    # any 5-word shingle present
    for i in range(len(ws) - 4):
        if " ".join(ws[i:i+5]) in n(text): return "shingle5"
    return "MISS"

async def main():
    sys.path.insert(0, "/app")
    from app.clients.llm_client import get_llm_client
    from app.clients.eval_client import extract_judge_content
    text = open("/tmp/ch1.txt", encoding="utf-8").read()
    llm = get_llm_client()
    job = await llm.submit_and_wait(
        user_id=USER, operation="chat", model_source="user_model", model_ref=MODEL,
        input={"messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": "CHƯƠNG:\n\n" + text}],
               "response_format": {"type": "text"}, "temperature": 0.3, "max_tokens": 2200,
               "reasoning_effort": "none",
               "chat_template_kwargs": {"thinking": False, "enable_thinking": False}},
        job_meta={"usage_purpose": "judge_poc", "extractor": "judge_poc"})
    print("STATUS:", job.status)
    content = extract_judge_content(job.result)
    open("/tmp/judge_out.txt", "w", encoding="utf-8").write(content)
    m = re.search(r"\[.*\]", content, re.DOTALL)
    findings = json.loads(m.group(0)) if m else []
    print("FINDINGS:", len(findings))
    tally = {}
    for i, f in enumerate(findings, 1):
        r = locate(f.get("span", ""), text)
        tally[r] = tally.get(r, 0) + 1
        print(f"\n[{i}] {f.get('type')}  LOCATE={r}")
        print(f"    span: {f.get('span','')[:90]}")
        print(f"    issue: {f.get('issue','')[:90]}")
        print(f"    fix: {f.get('fix','')[:90]}")
    located = sum(v for k, v in tally.items() if k not in ("MISS", "empty"))
    print(f"\nLOCATE-RATE: {located}/{len(findings)}  detail={tally}")

asyncio.run(main())
