"""Is the judge's veto a LAZY blind spot (fixable) or a TRUE one (needs a bigger model)?
Same Gemma 4 26B. Compare the OLD skeptical-snap judge vs a SMART judge (neutral default +
chain-of-thought + comparative 'is the fix better?'), 3 votes each, on 2 real findings (incl.
'mẫu thân ngươi' that the old judge refused 3/3) + 1 confab (should be refuted = precision check)."""
import asyncio, sys, re, json
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.clients.eval_client import extract_judge_content

USER="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"; MODEL="019ebb72-27a2-72f3-a42d-d2d0e0ded179"
NO_THINK={"reasoning_effort":"none","chat_template_kwargs":{"thinking":False,"enable_thinking":False}}

RULES=("QUY ƯỚC tiên hiệp: người đang TRỰC TIẾP nói KHÔNG tự xưng ngôi ba (mẫu thân nói 'lệnh của "
       "mẫu thân ngươi' là SAI, phải 'lệnh của ta'). CANON: Tô Yến LUÔN khinh miệt con gái, CHƯA TỪNG "
       "che chở. 'lão' là cách gọi BÌNH THƯỜNG cho một lão già trong tiên hiệp (không phải lỗi).")

# (original, replacement, expected_real)
FINDINGS=[
 ("Đây là lệnh của mẫu thân ngươi.", "Đây là lệnh của ta.", True),   # mẫu thân ngươi — the blind spot
 ("đứa con gái mà mình từng dốc lòng che chở", "đứa con gái mà mình từng khinh miệt", True),  # canon
 ("Lão không phải người của Lâm gia", "Y không phải người của Lâm gia", False),  # CONFAB (lão is fine)
]

OLD_SYS=("Bạn là thẩm định viên hoài nghi, mặc định BÁC BỎ. Cho QUY ƯỚC và một FINDING (câu gốc + đề "
         "xuất sửa). FINDING có phải lỗi THẬT không? Chỉ trả JSON {\"verdict\":\"CONFIRMED\"|\"REFUTED\"}.\n\n"+RULES)

SMART_SYS=("Bạn là biên tập tiên hiệp công tâm. Cho QUY ƯỚC/CANON và một cặp (câu GỐC → đề xuất SỬA), "
           "hãy SUY LUẬN TỪNG BƯỚC: (1) Đối chiếu câu gốc với quy ước — nó tuân thủ hay vi phạm, vì sao? "
           "(2) Bản sửa có đúng quy ước HƠN bản gốc không? (3) Kết luận: nên ÁP DỤNG bản sửa (nếu nó cải "
           "thiện) hay BỎ (nếu câu gốc đã ổn / bản sửa sai). Mặc định ÁP DỤNG nếu bản sửa rõ ràng tốt hơn. "
           "Trả JSON {\"reasoning\":\"...\",\"verdict\":\"APPLY\"|\"DROP\"}.\n\n"+RULES)

async def ask(llm, system, user, temp=0.5):
    job=await llm.submit_and_wait(user_id=USER, operation="chat", model_source="user_model",
        model_ref=MODEL, input={"messages":[{"role":"system","content":system},
        {"role":"user","content":user}], "response_format":{"type":"text"},"temperature":temp,
        "max_tokens":600,**NO_THINK}, job_meta={"usage_purpose":"smart_judge_poc","extractor":"poc"})
    c=extract_judge_content(job.result) or ""
    m=re.search(r'"verdict"\s*:\s*"?\s*(CONFIRMED|REFUTED|APPLY|DROP)',c,re.IGNORECASE)
    if not m: return "?"
    v=m.group(1).upper()
    return "KEEP" if v in ("CONFIRMED","APPLY") else "DROP"

async def vote(llm, system, user, k=3):
    rs=await asyncio.gather(*[ask(llm,system,user) for _ in range(k)])
    return sum(1 for r in rs if r=="KEEP"), rs

async def main():
    llm=get_llm_client()
    print("%-34s | OLD skeptical | SMART CoT+compare | đúng kỳ vọng" % "finding")
    print("-"*90)
    for orig,repl,real in FINDINGS:
        u_old=f"FINDING: câu gốc «{orig}» → đề xuất «{repl}»"
        u_smart=f"GỐC: «{orig}»\nSỬA: «{repl}»"
        ko,_=await vote(llm,OLD_SYS,u_old)
        ks,_=await vote(llm,SMART_SYS,u_smart)
        want="REAL→keep" if real else "CONFAB→drop"
        old_ok = (ko>=1)==real
        smart_ok = (ks>=1)==real
        print("%-34s |   %d/3 keep   |    %d/3 keep      | %-12s OLD:%s SMART:%s" % (
            orig[:34], ko, ks, want, "✓" if old_ok else "✗", "✓" if smart_ok else "✗"))

asyncio.run(main())
