"""Cheap quality-stack POC — raise CH1 quality before the human gate, on a $0 local model.

Layers under test (each prints a measurable result):
  L1  code pre-filter      — mechanical xưng hô / dup-word (no LLM)
  L2  must-quote enforce   — every LLM finding's quote verified verbatim in text else DROPPED
  L3  decomposed grounded  — single-axis judges (xưng hô / canon / logic), bible-grounded
  L4  self-consistency vote— broad-ungrounded vs grounded judge ×K; real=stable, confab=unstable
  L5  asymmetric verify    — strict "refute-or-confirm, quote-or-drop" pass over candidates

Ground truth on CH1 (established with the user):
  REAL  : "lệnh của mẫu thân ngươi" (3rd-person self-ref), "ông"/"Bà" modern pronouns,
          Tô Yến "từng dốc lòng che chở" (contradicts bible: she NEVER protected her),
          dup-word "từng từng".
  NOT   : "Uyển nhi tuân lệnh" (valid self-address) — judge must NOT flag.
  CONFAB: voluntary-sacrifice-for-brother, "why an outsider/not in the room" (text explains it),
          "fled athletically while crippled" (text shows her staggering & caught).
"""
import asyncio, json, re, sys
sys.path.insert(0, "/app")
from app.clients.llm_client import get_llm_client
from app.clients.eval_client import extract_judge_content

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
MODEL = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"   # Gemma 4 26B, local lm_studio, $0
K = 5
NO_THINK = {"reasoning_effort": "none",
            "chat_template_kwargs": {"thinking": False, "enable_thinking": False}}

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

# ── LLM ────────────────────────────────────────────────────────────────
async def chat(llm, system, user, temperature=0.3, max_tokens=1600):
    job = await llm.submit_and_wait(
        user_id=USER, operation="chat", model_source="user_model", model_ref=MODEL,
        input={"messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "response_format": {"type": "text"}, "temperature": temperature,
               "max_tokens": max_tokens, **NO_THINK},
        job_meta={"usage_purpose": "cheap_stack_poc", "extractor": "poc"})
    if job.status != "completed":
        return ""
    return extract_judge_content(job.result) or ""

def parse_arr(content):
    if not content:
        return []
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    return [r for r in arr if isinstance(r, dict)] if isinstance(arr, list) else []

# ── verbatim / locate (L2 enforcement + L4 bucketing) ──────────────────
def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().strip('"“”').lower())

NT = _norm(TEXT)
# paragraph offset map in normalized space
_paras = TEXT.split("\n\n")
_pnorm = [_norm(p) for p in _paras]

def locate(quote):
    """Return normalized-space start offset of quote in TEXT, or None. Tries full, then a
    6-word shingle (the judge sometimes re-spaces / lightly trims)."""
    nq = _norm(quote)
    if not nq:
        return None
    if nq in NT:
        return NT.index(nq)
    toks = nq.split()
    for i in range(0, max(1, len(toks) - 5)):
        sh = " ".join(toks[i:i + 6])
        if sh in NT:
            return NT.index(sh)
    return None

def bucket(quote):
    """A stable key for a finding's span: the paragraph index it lands in (coarse but
    robust to the judge's quote drift). UNLOCATED quotes get their own per-text key."""
    off = locate(quote)
    if off is None:
        return "UNLOCATED::" + _norm(quote)[:40]
    # walk paragraphs in normalized space
    acc = 0
    for idx, pn in enumerate(_pnorm):
        acc2 = acc + len(pn) + 1
        if off < acc2:
            return f"P{idx:02d}"
        acc = acc2
    return f"P{len(_pnorm)-1:02d}"

# ── L1: code pre-filter (no LLM) ───────────────────────────────────────
def layer1():
    out = []
    for m in re.finditer(r"(?<![\wÀ-ỹ])([Oo]ng|[Bb][aà]|ông ta|bà ta|cô ấy|anh ấy)(?![\wÀ-ỹ])", TEXT):
        w = m.group(0)
        if w.lower() in ("ông", "bà", "ông ta", "bà ta", "cô ấy", "anh ấy"):
            ctx = TEXT[max(0, m.start() - 25): m.end() + 25].replace("\n", " ")
            out.append(("modern_pronoun", w, "…" + ctx + "…"))
    for m in re.finditer(r"\b([\wÀ-ỹ]+)\s+\1\b", TEXT, re.IGNORECASE):
        ctx = TEXT[max(0, m.start() - 20): m.end() + 20].replace("\n", " ")
        out.append(("dup_word", m.group(0), "…" + ctx + "…"))
    return out

# ── L3: decomposed grounded single-axis judges ─────────────────────────
AXES = {
 "xung_ho": "CHỈ tìm lỗi XƯNG HÔ / đại từ trái QUY ƯỚC XƯNG HÔ bên dưới. Bỏ qua mọi loại lỗi khác.",
 "canon":   "CHỈ tìm câu/mô tả/hành vi MÂU THUẪN với CANON NHÂN VẬT bên dưới. Bỏ qua mọi loại lỗi khác.",
 "logic":   ("CHỈ tìm lỗ hổng nhân-quả / logic NỘI TẠI trong chương. KHÔNG suy diễn tình tiết "
             "ngoài văn bản; nếu chương ĐÃ TỰ giải thích điều đó thì KHÔNG tính là lỗi. Bỏ qua lỗi khác."),
}
def axis_system(rule):
    return (f"Bạn là biên tập tiên hiệp khắt khe. {rule}\n\n"
            "Mỗi lỗi PHẢI trích NGUYÊN VĂN 4-15 chữ COPY ĐÚNG TỪNG KÝ TỰ từ chương (không diễn giải) "
            'vào trường "quote". Trả về DUY NHẤT một mảng JSON: '
            '[{"axis":"...","quote":"...","issue":"...","fix":"..."}]. Không văn xuôi quanh nó.\n\n'
            + BIBLE)

# ── L4: judges run K times ─────────────────────────────────────────────
BROAD_SYS = ("Bạn là độc giả/biên tập truyện. Đọc chương và liệt kê mọi MÂU THUẪN logic hoặc "
             "mâu thuẫn nhân vật bạn thấy. Với mỗi lỗi trả JSON {\"quote\":\"đoạn liên quan\","
             "\"issue\":\"...\"}. Trả về DUY NHẤT mảng JSON.")  # ungrounded, no must-quote — mirrors Gemma outsider
GROUNDED_SYS = ("Bạn là biên tập tiên hiệp khắt khe. Tìm lỗi XƯNG HÔ, lỗi MÂU THUẪN CANON, và lỗ hổng "
                "LOGIC NỘI TẠI. KHÔNG suy diễn tình tiết ngoài văn bản; nếu chương đã tự giải thích thì "
                "không tính. Mỗi lỗi PHẢI trích NGUYÊN VĂN 4-15 chữ copy đúng từng ký tự vào \"quote\". "
                'Trả về DUY NHẤT mảng JSON [{"axis":"...","quote":"...","issue":"...","fix":"..."}].\n\n' + BIBLE)

async def run_k(llm, system, k=K):
    """Run a judge k times (temp 0.7 for stochastic variation). Return list of finding-lists."""
    tasks = [chat(llm, system, "CHƯƠNG:\n\n" + TEXT, temperature=0.7) for _ in range(k)]
    return [parse_arr(c) for c in await asyncio.gather(*tasks)]

def vote(runs):
    """Aggregate findings across runs by span bucket. Return {bucket: {runs:set, reps:[...]}}."""
    agg = {}
    for ri, fl in enumerate(runs):
        seen = set()
        for f in fl:
            q = f.get("quote", "")
            b = bucket(q)
            if b in seen:
                continue
            seen.add(b)
            d = agg.setdefault(b, {"runs": set(), "reps": [], "located": not b.startswith("UNLOC")})
            d["runs"].add(ri)
            if len(d["reps"]) < 1:
                d["reps"].append({"quote": q, "issue": f.get("issue", "")[:90]})
    return agg

# ── L5: asymmetric verify ──────────────────────────────────────────────
VERIFY_SYS = ("Bạn là thẩm định viên hoài nghi, mặc định BÁC BỎ. Cho một CHƯƠNG, một FINDING và đoạn "
              "QUOTE. Xác định finding có phải lỗi THẬT trong chương không, ĐỐI CHIẾU với QUY ƯỚC/CANON "
              "bên dưới. BÁC BỎ nếu: quote không có trong chương; hoặc 'lỗi' thực ra đã được chương giải "
              "thích; hoặc finding suy diễn tình tiết ngoài văn bản. Chỉ CONFIRM khi chỉ ra được đúng chữ "
              'sai. Trả JSON {"verdict":"CONFIRMED"|"REFUTED","reason":"..."}.\n\n' + BIBLE)

async def verify(llm, quote, issue):
    c = await chat(llm, VERIFY_SYS,
                   f"CHƯƠNG:\n\n{TEXT}\n\nFINDING: {issue}\nQUOTE: \"{quote}\"", temperature=0.2)
    m = re.search(r"\{.*\}", c, re.DOTALL)
    if not m:
        return ("PARSE_FAIL", c[:80])
    try:
        d = json.loads(m.group(0))
        return (str(d.get("verdict", "?")).upper(), str(d.get("reason", ""))[:120])
    except Exception:
        return ("PARSE_FAIL", c[:80])

# ── driver ─────────────────────────────────────────────────────────────
async def main():
    llm = get_llm_client()
    R = {}

    print("=" * 72); print("L1 — CODE PRE-FILTER (no LLM)"); print("=" * 72)
    l1 = layer1()
    R["L1"] = l1
    for t, w, ctx in l1:
        print(f"  [{t}] «{w}»  {ctx}")
    print(f"  → {len(l1)} mechanical findings\n")

    print("=" * 72); print("L3 — DECOMPOSED GROUNDED SINGLE-AXIS JUDGES (+L2 must-quote)"); print("=" * 72)
    R["L3"] = {}
    for name, rule in AXES.items():
        raw = parse_arr(await chat(llm, axis_system(rule), "CHƯƠNG:\n\n" + TEXT, temperature=0.3))
        kept, dropped = [], []
        for f in raw:
            (kept if locate(f.get("quote", "")) is not None else dropped).append(f)
        R["L3"][name] = {"kept": kept, "dropped_no_quote": len(dropped)}
        print(f"\n  AXIS={name}: {len(kept)} kept, {len(dropped)} DROPPED (quote not verbatim → L2)")
        for f in kept:
            print(f"    ✓ «{f.get('quote','')[:55]}» — {f.get('issue','')[:80]}")
        for f in dropped:
            print(f"    ✗drop «{f.get('quote','')[:55]}» (no verbatim match)")

    print("\n" + "=" * 72); print(f"L4 — SELF-CONSISTENCY VOTE (K={K})  real=stable / confab=unstable"); print("=" * 72)
    broad = vote(await run_k(llm, BROAD_SYS))
    grnd = vote(await run_k(llm, GROUNDED_SYS))
    R["L4"] = {"broad": {b: sorted(d["runs"]) for b, d in broad.items()},
               "grounded": {b: sorted(d["runs"]) for b, d in grnd.items()}}
    def show(tag, agg):
        print(f"\n  [{tag}]  (keep ≥2/{K})")
        for b, d in sorted(agg.items(), key=lambda x: -len(x[1]["runs"])):
            n = len(d["runs"]); keep = "KEEP " if n >= 2 else "drop "
            rep = d["reps"][0] if d["reps"] else {"quote": "", "issue": ""}
            loc = "loc" if d["located"] else "UNLOC"
            print(f"    {keep}{n}/{K} [{loc}] {b}: «{rep['quote'][:45]}» {rep['issue'][:55]}")
    show("BROAD / ungrounded", broad)
    show("GROUNDED", grnd)

    print("\n" + "=" * 72); print("L5 — ASYMMETRIC VERIFY (refute-or-confirm over candidates)"); print("=" * 72)
    # candidates = grounded L3 kept ∪ grounded-vote survivors (≥2/K)
    cand = {}
    for name in AXES:
        for f in R["L3"][name]["kept"]:
            cand[bucket(f.get("quote", ""))] = (f.get("quote", ""), f.get("issue", ""))
    for b, d in grnd.items():
        if len(d["runs"]) >= 2 and d["reps"]:
            cand.setdefault(b, (d["reps"][0]["quote"], d["reps"][0]["issue"]))
    R["L5"] = {}
    for b, (q, iss) in cand.items():
        v, reason = await verify(llm, q, iss)
        R["L5"][b] = {"quote": q, "verdict": v, "reason": reason}
        print(f"  {v:10s} {b}: «{q[:45]}»  — {reason[:70]}")

    json.dump({k: (v if k != "L4" else v) for k, v in R.items()},
              open("/tmp/poc_stack_out.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    print("\n  saved /tmp/poc_stack_out.json")

asyncio.run(main())
