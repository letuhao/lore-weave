"""POC: type-routed re-ranker (RULE-check vs CRAFT-defer) vs the general "is it better?" judge,
on every proposal across 12 chapters. The type-routed judge AUTO-approves only edits that fix a
CITED convention/canon RULE; it DEFERS subjective craft edits (rephrase/trim/pacing/voice) to the
human — because a general 26B judge is weak on craft and can flatten voice. We measure how often
the general judge over-approves craft (general=APPLY but type-routed=CRAFT/BAD)."""
import asyncio, sys, glob, re, json
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.clients.eval_client import extract_judge_content
from app.engine.self_heal import propose_edits_direct
from app.engine.heal_canon import render_canon, convention_for

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"; MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"
NO_THINK = {"reasoning_effort": "none", "chat_template_kwargs": {"thinking": False, "enable_thinking": False}}
CAST = [
 {"name":"Lâm Uyển","role":"protagonist","relationships":"con của Lâm Chấn Nhạc & Tô Yến; muội của Lâm Tử Hàn","description":"đích nữ bị ghẻ lạnh, phế vật bị vu oan → ma tu nghịch thiên"},
 {"name":"Lâm Chấn Nhạc","role":"phụ thân","relationships":"gia chủ; phụ thân Lâm Uyển","description":"gia chủ lạnh lùng vô tình"},
 {"name":"Tô Yến","role":"mẫu thân","relationships":"mẫu thân ruột của Lâm Uyển","description":"LUÔN khinh miệt con gái, CHƯA TỪNG che chở"},
 {"name":"Lâm Tử Hàn","role":"huynh trưởng","relationships":"huynh trưởng Lâm Uyển","description":"thiên tài được sủng ái, coi thường muội muội; theo CHÍNH đạo (không tu ma công)"},
 {"name":"Hắc Sát Lão Nhân","role":"phản diện","description":"sát thủ NGOÀI gia tộc, một lão già"},
]

GEN_SYS = (
    "You are an impartial fiction editor comparing an ORIGINAL span with a PROPOSED replacement, "
    "using the STORY BIBLE as ground truth. Is the replacement a clear improvement? DEFAULT APPLY "
    'when clearly better. Reply ONLY JSON {"reasoning":"<=20 words","verdict":"APPLY"|"DROP"}.')

TYPED_SYS = (
    "You decide whether a proposed fiction edit is safe to AUTO-APPLY or must be left for the human "
    "author, using the STORY BIBLE as ground truth. Classify: "
    "RULE = the ORIGINAL clearly breaks a SPECIFIC convention/canon rule (modern pronoun, third-person "
    "self-reference, a fact contradicting the bible, wrong name/role) AND the replacement fixes it — "
    "cite the rule. CRAFT = a subjective prose choice (rephrase, trim redundancy, pacing, tone, word "
    "choice) with NO clear rule broken — the author must decide. BAD = the replacement is wrong / worse "
    '/ a no-op. Reply ONLY JSON {"reasoning":"<=20 words","verdict":"RULE"|"CRAFT"|"BAD"}.')

async def judge(llm, system, before, after, issue, canon, rx):
    job = await llm.submit_and_wait(user_id=USER, operation="chat", model_source="user_model",
        model_ref=MODEL, input={"messages":[{"role":"system","content":system+"\n\nSTORY BIBLE:\n"+canon},
        {"role":"user","content":f"ORIGINAL: «{before}»\nPROPOSED: «{after}»\nISSUE: {issue}"}],
        "response_format":{"type":"text"},"temperature":0.3,"max_tokens":400,**NO_THINK},
        job_meta={"usage_purpose":"typerouted_poc","extractor":"poc"})
    c = extract_judge_content(job.result) or ""
    m = re.search(rx, c, re.I)
    return m.group(1).upper() if m else "?"

async def main():
    llm = get_llm_client()
    canon = render_canon(CAST, convention=convention_for(["tiên hiệp"], "vi"))
    A = dict(prop=0, gen_apply=0, rule=0, craft=0, bad=0, agree_apply=0, over_craft=0, over_bad=0)
    for f in sorted(glob.glob("/tmp/drive_ch*_raw.txt")):
        ci = re.search(r"ch(\d+)_raw", f).group(1)
        text = open(f, encoding="utf-8").read()
        proposals, _ = await propose_edits_direct(llm, text, user_id=USER, model_source="user_model",
            model_ref=MODEL, canon=canon, source_language="vi", rerank=False)
        print("CH%s: %d proposals" % (ci, len(proposals)), flush=True)
        for p in proposals:
            gen = await judge(llm, GEN_SYS, p.before, p.after, p.issue, canon, r'"verdict"\s*:\s*"?\s*(APPLY|DROP)')
            typed = await judge(llm, TYPED_SYS, p.before, p.after, p.issue, canon, r'"verdict"\s*:\s*"?\s*(RULE|CRAFT|BAD)')
            A["prop"] += 1
            A["gen_apply"] += gen == "APPLY"
            A["rule"] += typed == "RULE"; A["craft"] += typed == "CRAFT"; A["bad"] += typed == "BAD"
            A["agree_apply"] += (gen == "APPLY" and typed == "RULE")
            A["over_craft"] += (gen == "APPLY" and typed == "CRAFT")
            A["over_bad"] += (gen == "APPLY" and typed == "BAD")
            flag = " <== general over-approves" if (gen == "APPLY" and typed in ("CRAFT", "BAD")) else ""
            print("  [%-9s] gen=%-5s typed=%-5s%s | «%s» -> «%s»" % (
                p.type[:9], gen, typed, flag, p.before[:22], p.after[:24]), flush=True)
    print("\nAGG:", json.dumps(A, ensure_ascii=False))
    print("TYPED_COMPARE_DONE", flush=True)

asyncio.run(main())
