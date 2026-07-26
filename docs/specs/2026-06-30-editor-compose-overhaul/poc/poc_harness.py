#!/usr/bin/env python3
"""
POC harness — drive the real composition journey for the PO's Vietnamese xianxia premise
using Gemma-4 26B QAT (BYOK lm_studio), logging EVERY request/response to poc/io/.

Phases (argv[1]):
  setup      — login, create Book + N empty chapters, resolve/create Work
  structure  — list templates, decompose (premise+template -> scenes), commit, read outline
  write      — draft EVERY scene (Vietnamese) AND persist combined prose into each chapter draft
  profile    — GET the extraction profile (debug; logs its shape)
  extract    — glossary + KG extraction over the written chapters; report entity count
  all        — setup -> structure -> write -> extract

Env: POC_CHAPTERS=N limits write/extract to the first N chapters (smoke). Default = all.
State persists in poc/io/_state.json so phases run separately.
"""
import sys, os, json, time, uuid, pathlib, datetime
import requests

ROOT = pathlib.Path(__file__).resolve().parent
IO = ROOT / "io"; IO.mkdir(exist_ok=True)
STATE_F = IO / "_state.json"

BASE = "http://localhost:3123"
EMAIL = "claude-test@loreweave.dev"; PASSWORD = "Claude@Test2026"
MODEL_REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"   # Gemma-4 26B-A4B QAT (200K)
MODEL_SOURCE = "user_model"
NUM_CHAPTERS = 12
LANG = "vi"
PREMISE_VI = (
    "Truyện tu tiên (tiên hiệp) HẮC ÁM, nhiều drama và phản chuyển. Trọng tâm là tu luyện và chiến "
    "đấu; tình cảm chỉ là yếu tố phụ.\n\n"
    "NỮ CHÍNH: Lâm Uyển — đích nữ Lâm gia (một tu tiên thế gia). Nàng xấu xí, bị cả nhà ghẻ lạnh kể "
    "cả cha mẹ ruột, lại mang linh căn kém cỏi nên bị xem là phế vật. Trong một lần cận kề cái chết, "
    "nàng có được cuốn cổ thư công pháp của Ma nữ thượng cổ Cửu U Ma Cơ và quyết tu luyện ma công đó, "
    "từng bước cải tạo bản thân, quyết một ngày đạt tới sự hoàn mỹ.\n\n"
    "DÀN NHÂN VẬT (giữ tên CỐ ĐỊNH, đúng phong cách tiên hiệp):\n"
    "- Lâm Uyển — nữ chính.\n"
    "- Lâm Chấn Nhạc — gia chủ Lâm gia, phụ thân lạnh lùng.\n"
    "- Tô Yến — mẫu thân (chính thất), sắc sảo, coi trọng danh dự gia tộc.\n"
    "- Lâm Tử Hàn — huynh trưởng, thiên tài được sủng ái, người được ban Trúc Cơ Đan.\n"
    "- Cửu U Ma Cơ — Ma nữ thượng cổ, chủ nhân cuốn cổ thư.\n"
    "- Thanh Vân Tông — tông môn chính đạo về sau khinh miệt Lâm Uyển.\n\n"
    "QUY ƯỚC ĐẶT TÊN: dùng tên Hán-Việt kiểu tiên hiệp (họ + tên kép); xưng hô tu tiên (gia chủ, "
    "trưởng lão, công tử, tiểu thư, đạo hữu, tiền bối). TUYỆT ĐỐI tránh cách gọi hiện đại như "
    "\"ông Lâm\", \"bà Lý\"."
)

# Draft steer (cast + naming convention). Language is now handled by the Work's
# source_language (the bugfix), so the guide only enforces names/genre style.
CAST_GUIDE = (
    "Giữ tên nhân vật CỐ ĐỊNH, đúng phong cách tiên hiệp: Lâm Uyển (nữ chính), phụ thân Lâm Chấn Nhạc "
    "(gia chủ Lâm gia), mẫu thân Tô Yến, huynh trưởng Lâm Tử Hàn, Ma nữ Cửu U Ma Cơ, tông môn Thanh "
    "Vân Tông. Xưng hô tu tiên (gia chủ, trưởng lão, công tử, tiểu thư). Tránh \"ông/bà + họ\" hiện đại."
)

MOTIFS = [
    {"code": "xau_hoa_my", "name": "Xấu hóa mỹ (Ugliness → Perfection)",
     "summary": "Kẻ bị coi là xấu xí, phế vật từng bước lột xác cả về dung mạo lẫn thực lực để vươn tới hoàn mỹ."},
    {"code": "ma_cong_phan_phe", "name": "Ma công phản phệ (Forbidden Power, Corrupting Price)",
     "summary": "Mỗi lần mạnh lên nhờ ma công của Ma nữ lại phải trả giá bằng một phần nhân tính."},
    {"code": "phuc_thu_khinh_miet", "name": "Phục thù kẻ khinh miệt (Revenge on Those Who Scorned Her)",
     "summary": "Báo đáp gia tộc và tông môn đã ruồng bỏ, khinh miệt nàng — đòn payoff cho thiết lập bị chối bỏ."},
    {"code": "tiem_long_tai_uyen", "name": "Tiềm long tại uyên (Underestimated Hidden Potential)",
     "summary": "Tư chất 'kém cỏi' chỉ là vỏ bọc; căn cơ thật sự của nàng phi thường, bị cả thiên hạ đánh giá thấp."},
]

_seq = 0
def log_io(name, method, url, req, resp, status=None):
    global _seq; _seq += 1
    (IO / f"{_seq:03d}_{name}.json").write_text(
        json.dumps({"seq": _seq, "name": name, "method": method, "url": url, "status": status,
                    "request": req, "response": resp}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{'OK' if (status and status<400) else 'ERR'}] {_seq:03d} {name}: HTTP {status}")

def load_state(): return json.loads(STATE_F.read_text(encoding="utf-8")) if STATE_F.exists() else {}
def save_state(s): STATE_F.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

def call(method, path, token=None, json_body=None, name="call", expect=None):
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, url, headers=headers, json=json_body, timeout=1200)
    try: body = r.json()
    except Exception: body = {"_raw": r.text[:3000]}
    log_io(name, method, url, json_body, body, status=r.status_code)
    if expect and r.status_code not in expect:
        raise SystemExit(f"{name}: expected {expect}, got {r.status_code}: {json.dumps(body, ensure_ascii=False)[:600]}")
    return r.status_code, body

def login():
    _, b = call("POST", "/v1/auth/login", json_body={"email": EMAIL, "password": PASSWORD}, name="login", expect={200})
    return b["access_token"]

def poll_job(token, job_id, label, base_path="/v1/composition/jobs", max_polls=400, interval=2.5):
    for i in range(max_polls):
        _, job = call("GET", f"{base_path}/{job_id}", token=token, name=f"{label}_poll{i}")
        if job.get("status") in ("completed", "failed", "cancelled"): return job
        time.sleep(interval)
    raise SystemExit(f"{label}: job {job_id} timed out")

# ---------- phases ----------
def phase_setup(token, s):
    _, book = call("POST", "/v1/books", token=token, name="create_book", expect={201},
                   json_body={"title": "Ma Nữ Nghịch Thiên (POC)", "original_language": LANG,
                              "description": "POC — dark cultivation, ugly MC + succubus grimoire", "summary": PREMISE_VI})
    s["book_id"] = book.get("book_id") or book.get("id")
    s["chapter_ids"] = []
    for i in range(1, NUM_CHAPTERS + 1):
        _, ch = call("POST", f"/v1/books/{s['book_id']}/chapters", token=token, name=f"create_chapter_{i:02d}",
                     expect={201}, json_body={"original_language": LANG, "title": f"Chương {i}", "sort_order": i, "body": ""})
        s["chapter_ids"].append(ch.get("chapter_id") or ch.get("id"))
    st, w = call("POST", f"/v1/composition/books/{s['book_id']}/work", token=token, name="create_work")
    if st >= 400:
        _, w = call("GET", f"/v1/composition/books/{s['book_id']}/work", token=token, name="resolve_work", expect={200})
    s["project_id"] = w.get("project_id") or (w.get("work") or {}).get("project_id")
    save_state(s); print(f"\nSETUP: book={s['book_id']} chapters={len(s['chapter_ids'])} project={s['project_id']}")

def phase_structure(token, s):
    _, body = call("GET", "/v1/composition/templates", token=token, name="list_templates", expect={200})
    templates = body.get("templates", body if isinstance(body, list) else [])
    pref = ["web novel", "story circle", "kish", "three-act", "generic"]
    def score(t):
        n = (t.get("name") or "").lower()
        for i, p in enumerate(pref):
            if p in n: return (i, -len(t.get("beats", [])))
        return (99, -len(t.get("beats", [])))
    tmpl = sorted(templates, key=score)[0]
    s["template"] = {"id": tmpl["id"], "name": tmpl["name"]}
    print(f"template: {tmpl['name']} ({len(tmpl.get('beats',[]))} beats)")
    st, dec = call("POST", f"/v1/composition/works/{s['project_id']}/outline/decompose", token=token, name="decompose",
                   json_body={"structure_template_id": tmpl["id"], "premise": PREMISE_VI,
                              "model_source": MODEL_SOURCE, "model_ref": MODEL_REF,
                              "thread_state": True})  # Phase-0 slice-2: cross-chapter threading
    if isinstance(dec, dict) and dec.get("job_id") and dec.get("status") in ("pending", "running"):
        job = poll_job(token, dec["job_id"], "decompose"); dec = job.get("result")
    chapters = [{"chapter_id": ch["chapter"]["chapter_id"], "title": ch["chapter"]["title"],
                 "intent": ch["chapter"].get("intent", ""), "beat_role": ch["chapter"].get("beat_role"),
                 "scenes": [{"title": sc["title"], "synopsis": sc["synopsis"], "tension": sc.get("tension"),
                             "present_entity_ids": sc.get("present_entity_ids", [])} for sc in ch.get("scenes", [])]}
                for ch in dec.get("chapters", [])]
    call("POST", f"/v1/composition/works/{s['project_id']}/outline/decompose/commit", token=token, name="commit_decompose",
         json_body={"arc_title": dec.get("arc_title", "Arc 1"), "chapters": chapters, "replace": True,
                    "idempotency_key": str(uuid.uuid4())}, expect={200, 201})
    save_state(s); print(f"\nSTRUCTURE: {len(chapters)} chapters, {sum(len(c['scenes']) for c in chapters)} scenes")

def scenes_by_chapter(token, s):
    _, outline = call("GET", f"/v1/composition/works/{s['project_id']}/outline", token=token, name="outline", expect={200})
    by_ch = {}
    for n in outline.get("nodes", []):
        if n.get("kind") == "scene":
            by_ch.setdefault(n.get("chapter_id"), []).append(n)
    for cid in by_ch: by_ch[cid].sort(key=lambda n: n.get("story_order", 0))
    return by_ch

def gen_scene(token, s, node, label):
    st, gen = call("POST", f"/v1/composition/works/{s['project_id']}/generate", token=token, name=label,
                   json_body={"mode": "auto", "outline_node_id": node["id"], "model_source": MODEL_SOURCE,
                              "model_ref": MODEL_REF, "operation": "draft_scene",
                              "guide": os.environ.get("POC_GUIDE", CAST_GUIDE), "reasoning": "auto"})
    if isinstance(gen, dict) and gen.get("job_id") and gen.get("status") in ("pending", "running"):
        job = poll_job(token, gen["job_id"], label, max_polls=600, interval=3.0)
        return (job.get("result") or {}).get("text", "")
    return (gen or {}).get("text", "") or ((gen or {}).get("result") or {}).get("text", "")

def to_tiptap_doc(scene_pairs):
    """Build a Tiptap JSON doc (the canonical chapter format, body_format='json') —
    a heading per scene + a paragraph per prose paragraph, so read mode + the editor
    render proper blocks (mirrors what the editor saves)."""
    content = []
    for title, text in scene_pairs:
        if title:
            content.append({"type": "heading", "attrs": {"level": 3},
                            "content": [{"type": "text", "text": title}]})
        for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
            content.append({"type": "paragraph", "content": [{"type": "text", "text": para}]})
    return {"type": "doc", "content": content}

def phase_write(token, s):
    limit = int(os.environ.get("POC_CHAPTERS", "0")) or len(s["chapter_ids"])
    by_ch = scenes_by_chapter(token, s)
    for ci, cid in enumerate(s["chapter_ids"][:limit], 1):
        scenes = by_ch.get(cid, [])
        pairs = []
        for si, node in enumerate(scenes, 1):
            print(f"  ch{ci} scene{si}/{len(scenes)}: {node.get('title')}")
            text = gen_scene(token, s, node, f"gen_ch{ci:02d}_sc{si:02d}")
            if text: pairs.append((node.get("title", ""), text))
        if pairs:
            doc = to_tiptap_doc(pairs)
            payload = {"body": doc, "body_format": "json", "commit_message": "POC draft"}
            st, _ = call("PATCH", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token,
                         name=f"persist_ch{ci:02d}", json_body=payload)
            if st == 409:  # stale version — fetch + retry with expected_draft_version
                _, d = call("GET", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token, name=f"draftget_ch{ci:02d}")
                call("PATCH", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token, name=f"persist_ch{ci:02d}_retry",
                     json_body={**payload, "expected_draft_version": d.get("draft_version")})
        chars = sum(len(t) for _, t in pairs)
        print(f"  ch{ci} persisted ({chars} chars, {len(pairs)} scenes, {len(to_tiptap_doc(pairs)['content'])} blocks)")
    print("WRITE done")

def _rep_metrics(text):
    """Cheap baseline detectors the self-heal passes target — so we can diff
    before/after a stitch (or a future pass)."""
    import re
    low = text.lower()
    # scene-title leakage: a short ALL-or-Title line surrounded by blank lines / a md heading
    titles = len(re.findall(r"(?m)^\s{0,3}#{1,3}\s+\S", text)) + \
             len(re.findall(r"(?m)^(?:Cảnh|Scene)\s+\d", text))
    return {
        "chars": len(text),
        "scene_title_markers": titles,
        "phe_vat": low.count("phế vật"),                 # the re-explained "trash/no-root" fact
        "lanh": low.count("lạnh"),                       # the over-used cold-motif stem
        "ma_co": low.count("cửu u ma cơ"),               # foreshadow over-repetition
    }

def phase_drive(token, s):
    """Task C — draft EVERY scene of all 12 chapters (grounded /generate) and save the
    assembled raw prose per chapter (drive_chNN_raw.txt) + persist the chapter draft.
    Assembles from the JUST-drafted current nodes (not chapter_scene_drafts) so stale
    archived-node drafts never pollute the prose. Self-heal is a separate in-container pass."""
    by_ch = scenes_by_chapter(token, s)
    cids = s["chapter_ids"]
    start = int(os.environ.get("POC_DRIVE_FROM", "1"))
    for ci, cid in enumerate(cids, 1):
        if ci < start:
            continue
        scenes = by_ch.get(cid, [])
        pairs = []
        for si, node in enumerate(scenes, 1):
            print(f"  CH{ci:02d} scene{si}/{len(scenes)}: {node.get('title')}", flush=True)
            text = gen_scene(token, s, node, f"drive_ch{ci:02d}_sc{si:02d}")
            if text:
                pairs.append((node.get("title", ""), text))
        raw = "\n\n".join(t for _, t in pairs)
        (IO / f"drive_ch{ci:02d}_raw.txt").write_text(raw, encoding="utf-8")
        if pairs:
            doc = to_tiptap_doc(pairs)
            st, _ = call("PATCH", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token,
                         name=f"drive_persist_ch{ci:02d}",
                         json_body={"body": doc, "body_format": "json", "commit_message": "drive draft"},
                         expect={200, 409})
            if st == 409:
                _, dft = call("GET", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token,
                              name=f"drive_get_ch{ci:02d}")
                call("PATCH", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token,
                     name=f"drive_persist_ch{ci:02d}_retry",
                     json_body={"body": doc, "body_format": "json", "commit_message": "drive draft",
                                "expected_draft_version": dft.get("draft_version")}, expect={200})
        print(f"  CH{ci:02d} drafted: {len(raw)} chars, {len(pairs)} scenes", flush=True)
    print("DRIVE DRAFT done")

def phase_pipeline(token, s):
    """Task C drive — run the MULTI-STEP planning pipeline through the real endpoint
    (pipeline=true → worker job), then commit the grounded+healed plan to the outline.
    Dumps cast/motifs/intros + the plan-heal findings + per-chapter scenes."""
    tmpl_id = s.get("template", {}).get("id")
    st, dec = call("POST", f"/v1/composition/works/{s['project_id']}/outline/decompose", token=token,
                   name="pipeline", json_body={"structure_template_id": tmpl_id, "premise": PREMISE_VI,
                   "model_source": MODEL_SOURCE, "model_ref": MODEL_REF, "pipeline": True})
    if isinstance(dec, dict) and dec.get("job_id") and dec.get("status") in ("pending", "running"):
        job = poll_job(token, dec["job_id"], "pipeline", max_polls=1400, interval=5.0); dec = job.get("result")
    d = dec.get("decompose", dec) if isinstance(dec, dict) else {}
    chs = d.get("chapters", [])
    hr = dec.get("heal_report") or {}
    print("\nPIPELINE PLAN: cast=%d motifs=%d arcs=%d | %d ch, %d scenes | heal edits=%s/%s findings" % (
        len(dec.get("cast", [])), len(dec.get("motifs", [])), len(dec.get("char_arcs", [])),
        len(chs), sum(len(c.get("scenes", [])) for c in chs),
        hr.get("edits_applied"), len(hr.get("findings", []))))
    print("motifs:", [m.get("name", "")[:24] for m in dec.get("motifs", [])])
    print("intros:", {a.get("name"): a.get("introduce_at_chapter") for a in dec.get("char_arcs", [])
                      if a.get("introduce_at_chapter") and a["introduce_at_chapter"] > 1})
    # commit the plan to the outline (so scenes become nodes the drafter can target)
    commit_chapters = [{"chapter_id": c["chapter"]["chapter_id"], "title": c["chapter"].get("title", ""),
                        "intent": c["chapter"].get("intent", ""), "beat_role": c["chapter"].get("beat_role"),
                        "scenes": [{"title": sc.get("title", ""), "synopsis": sc.get("synopsis", ""),
                                    "tension": sc.get("tension"), "present_entity_ids": sc.get("present_entity_ids", [])}
                                   for sc in c.get("scenes", [])]} for c in chs]
    call("POST", f"/v1/composition/works/{s['project_id']}/outline/decompose/commit", token=token,
         name="pipeline_commit", json_body={"arc_title": d.get("arc_title", "Arc 1"),
         "chapters": commit_chapters, "replace": True, "idempotency_key": str(uuid.uuid4())}, expect={200, 201})
    save_state(s)
    print("\nPIPELINE committed. Per-chapter (first 4):")
    for i, c in enumerate(chs[:4], 1):
        print("  CH%02d [%s] scenes=%d tensions=%s" % (i, c["chapter"].get("beat_role"),
              len(c.get("scenes", [])), [sc.get("tension") for sc in c.get("scenes", [])]))

def phase_satellite(token, s):
    """Satellite-edit POC — does the SMALL model do a SURGICAL span edit well via
    mechanism (2) (only the span is sent + returned)? Pick a 'lạnh'-dense window from
    the stitched ch1, run selection-edit(rewrite) with a guide to thin that motif,
    and check: (a) the motif drops IN the span, (b) the span stays ~same length (no
    expansion when isolated), (c) meaning preserved. Tests whether structural
    isolation makes a small model behave surgically."""
    ci = int(os.environ.get("POC_STITCH_CH", "1"))
    src = (IO / f"stitch_ch{ci:02d}_stitched.txt")
    text = src.read_text(encoding="utf-8") if src.exists() else \
           (IO / f"stitch_ch{ci:02d}_raw_concat.txt").read_text(encoding="utf-8")
    # find the ~450-char window with the most "lạnh" occurrences (the motif to thin)
    W = 450; low = text.lower(); best_i, best_n = 0, -1
    for i in range(0, max(1, len(text) - W), 50):
        n = low[i:i + W].count("lạnh")
        if n > best_n: best_i, best_n = i, n
    # snap to paragraph-ish boundaries (avoid mid-word)
    span = text[best_i:best_i + W]
    span = span[span.find(" ") + 1:]  # drop a leading partial word
    print(f"SATELLITE: span={len(span)} chars, 'lạnh' x{span.lower().count('lạnh')} (most-dense window)")
    print(f"\n--- BEFORE ---\n{span}\n")
    guide = ("Chỉ viết lại đúng đoạn này. GIẢM lặp từ 'lạnh/lạnh lẽo/lạnh lùng' — đa dạng hóa "
             "hình ảnh (giữ tối đa 1 lần). GIỮ NGUYÊN nghĩa, sự kiện, giọng văn và ĐỘ DÀI tương đương; "
             "KHÔNG thêm tình tiết mới.")
    st, res = call("POST", f"/v1/composition/works/{s['project_id']}/selection-edit", token=token,
                   name=f"satellite_ch{ci:02d}",
                   json_body={"operation": "rewrite", "selection": span, "guide": guide,
                              "model_source": MODEL_SOURCE, "model_ref": MODEL_REF,
                              "reasoning": "off"}, expect={200, 202})
    if isinstance(res, dict) and res.get("job_id") and res.get("status") in ("pending", "running"):
        job = poll_job(token, res["job_id"], f"satellite_ch{ci:02d}", max_polls=300, interval=2.0)
        res = job.get("result") or {}
    out = (res or {}).get("text", "") if isinstance(res, dict) else ""
    (IO / f"satellite_ch{ci:02d}_before.txt").write_text(span, encoding="utf-8")
    (IO / f"satellite_ch{ci:02d}_after.txt").write_text(out, encoding="utf-8")
    print(f"--- AFTER ({len(out)} chars, 'lạnh' x{out.lower().count('lạnh')}) ---\n{out}\n")
    print(f"SATELLITE RESULT: len {len(span)}→{len(out)} (ratio {len(out)/max(1,len(span)):.2f})  "
          f"lạnh {span.lower().count('lạnh')}→{out.lower().count('lạnh')}")

def phase_stitch(token, s):
    """Self-heal POC step 1 — measure the EXISTING 1-pass `stitch` baseline.
    The prior POC raw-concatenated scenes (never stitched); this drafts ch1's scenes
    onto the CURRENT nodes, marks them done (the stitch gate), runs stitch, and diffs
    the stitched chapter vs the raw concat so we can see how much the existing advisory
    pass already fixes before building NEW self-heal passes. POC_STITCH_CH=1-based."""
    ci = int(os.environ.get("POC_STITCH_CH", "1"))
    redraft = os.environ.get("POC_STITCH_REDRAFT", "1") != "0"  # 0 = reuse the DB drafts (isolate the stitch variable)
    cid = s["chapter_ids"][ci - 1]
    raw_path = IO / f"stitch_ch{ci:02d}_raw_concat.txt"
    if redraft:
        scenes = scenes_by_chapter(token, s).get(cid, [])
        print(f"STITCH baseline: ch{ci} {cid} — {len(scenes)} scenes (redraft)")
        texts = []
        for si, node in enumerate(scenes, 1):
            print(f"  draft ch{ci} scene{si}/{len(scenes)}: {node.get('title')}")
            text = gen_scene(token, s, node, f"stitch_gen_ch{ci:02d}_sc{si:02d}")
            if text:
                texts.append(text)
            # mark the scene done so the stitch trigger-gate (all scenes done) passes
            call("PATCH", f"/v1/composition/outline/nodes/{node['id']}",
                 token=token, name=f"stitch_done_ch{ci:02d}_sc{si:02d}",
                 json_body={"status": "done"}, expect={200})
        raw_concat = "\n\n".join(texts)
        raw_path.write_text(raw_concat, encoding="utf-8")
    else:
        raw_concat = raw_path.read_text(encoding="utf-8")  # the prior run's drafts == what's in the DB
        print(f"STITCH A/B: ch{ci} {cid} — reusing {len(raw_concat)} chars of existing DB drafts")
    st, res = call("POST", f"/v1/composition/works/{s['project_id']}/chapters/{cid}/stitch",
                   token=token, name=f"stitch_ch{ci:02d}",
                   json_body={"model_source": MODEL_SOURCE, "model_ref": MODEL_REF}, expect={200, 202})
    if isinstance(res, dict) and res.get("job_id") and res.get("status") in ("pending", "running"):
        job = poll_job(token, res["job_id"], f"stitch_ch{ci:02d}", max_polls=600, interval=3.0)
        res = job.get("result") or {}
    stitched = (res or {}).get("text", "")
    (IO / f"stitch_ch{ci:02d}_stitched.txt").write_text(stitched, encoding="utf-8")
    rm_raw, rm_st = _rep_metrics(raw_concat), _rep_metrics(stitched)
    print(f"\nSTITCH BASELINE ch{ci} — stitched={(res or {}).get('stitched')} "
          f"assembly={(res or {}).get('assembly_mode')} truncated={(res or {}).get('truncated')}")
    print(f"  {'metric':<22}{'raw_concat':>12}{'stitched':>12}")
    for k in rm_raw:
        print(f"  {k:<22}{rm_raw[k]:>12}{rm_st[k]:>12}")
    print(f"\n  --- stitched head (600 chars) ---\n{stitched[:600]}")

# Xianxia ontology: the System genre is already seeded; adopt it + its kinds onto the
# book so the extraction profile resolves (the per-book ontology persists in the DB → reusable).
XIANXIA_KINDS = ["character", "location", "organization", "power_system", "item", "event",
                 "plot_arc", "species", "terminology", "trope", "relationship", "social_setting"]

def phase_ontology(token, s):
    call("POST", f"/v1/glossary/books/{s['book_id']}/adopt", token=token, name="adopt_ontology",
         json_body={"genres": ["xianxia"], "kinds": XIANXIA_KINDS}, expect={200, 201})
    _, prof = call("GET", f"/v1/glossary/books/{s['book_id']}/extraction-profile", token=token,
                   name="extraction_profile_after", expect={200})
    kinds = prof.get("kinds", [])
    print(f"ONTOLOGY: adopted xianxia + {len(XIANXIA_KINDS)} kinds; profile now resolves {len(kinds)} kinds")

def phase_profile(token, s):
    call("GET", f"/v1/glossary/books/{s['book_id']}/extraction-profile", token=token, name="extraction_profile", expect={200})
    print("profile logged — inspect io/*_extraction_profile.json")

def phase_extract(token, s):
    limit = int(os.environ.get("POC_CHAPTERS", "0")) or len(s["chapter_ids"])
    chapter_ids = s["chapter_ids"][:limit]
    _, prof = call("GET", f"/v1/glossary/books/{s['book_id']}/extraction-profile", token=token, name="extraction_profile", expect={200})
    # Build {kind: {attr: 'default'}} from the auto-resolved profile.
    extraction_profile = {}
    kinds = prof.get("kinds") or prof.get("profile") or []
    if isinstance(kinds, list):
        for k in kinds:
            code = k.get("code") or k.get("kind_code") or k.get("kind")
            attrs = k.get("attributes") or k.get("attrs") or []
            extraction_profile[code] = {(a.get("code") or a.get("attr_code")): "default" for a in attrs} if attrs else {}
    elif isinstance(kinds, dict):
        extraction_profile = {kc: {ac: "default" for ac in av} for kc, av in kinds.items()}
    body = {"chapter_ids": chapter_ids, "extraction_profile": extraction_profile,
            "model_source": MODEL_SOURCE, "model_ref": MODEL_REF, "thinking_enabled": False}
    st, job = call("POST", f"/v1/extraction/books/{s['book_id']}/extract-glossary", token=token, name="extract_start", json_body=body)
    if st >= 400:
        print(f"extract start failed {st}"); return
    jid = job.get("job_id") or job.get("id")
    if jid:
        poll_job(token, jid, "extract", base_path="/v1/extraction/jobs", max_polls=400, interval=3.0)
    # report glossary entity count
    _, ents = call("GET", f"/v1/glossary/books/{s['book_id']}/entities?limit=200", token=token, name="glossary_entities")
    items = ents.get("items", ents if isinstance(ents, list) else [])
    print(f"EXTRACT done — glossary entities: {len(items)}")

def phase_motifs(token, s):
    for m in MOTIFS:
        call("POST", "/v1/composition/motifs", token=token, name=f"motif_{m['code']}",
             json_body={"code": m["code"], "name": m["name"], "kind": "sequence", "summary": m["summary"],
                        "genre_tags": ["xianxia", "cultivation", "dark"], "language": "vi", "visibility": "private"},
             expect={200, 201, 409})
    print(f"MOTIFS: {len(MOTIFS)} ensured")

def phase_grounding(token, s):
    """POC Part 2 — does a LATER chapter's scene exploit the KG/glossary/prev-chapter
    latent state? Call grounding for a chapter-2 scene and inspect what context it pulls
    (present entities from ch1, timeline, canon, lore, open-promises)."""
    by_ch = scenes_by_chapter(token, s)
    cid = s["chapter_ids"][1]  # chapter 2
    scenes = by_ch.get(cid, [])
    if not scenes:
        print("no ch2 scenes — run structure first"); return
    node = scenes[0]
    st, g = call("GET", f"/v1/composition/works/{s['project_id']}/scenes/{node['id']}/grounding",
                 token=token, name="grounding_ch2", expect={200, 404})
    if st == 404:
        print("grounding 404 — scene/work not found"); return
    blocks = g.get("blocks") or []
    items = g.get("items") or g.get("addressable") or []
    warns = g.get("warnings") or []
    # try to surface the present-entity names the packer pulled from the KG
    names = []
    for b in blocks:
        t = (b.get("kind") or b.get("type") or "")
        nm = b.get("name") or b.get("title")
        if nm: names.append(f"{t}:{nm}")
    print(f"GROUNDING ch2 '{node.get('title')}': tokens={g.get('token_count')} "
          f"blocks={len(blocks)} items={len(items)} warnings={warns}")
    print("  pulled:", ", ".join(names[:25]) if names else "(no named blocks — see io/*_grounding_ch2.json)")

def phase_mdtest(token, s):
    """Validate the server-side universal formatter: send a MARKDOWN body and confirm
    the stored draft is canonical Tiptap blocks (heading + paragraphs), not a raw string."""
    cid = s["chapter_ids"][1]  # an empty chapter
    md = "### Cảnh thử\n\nĐây là đoạn văn thứ nhất của cảnh.\n\nĐây là đoạn văn thứ hai."
    call("PATCH", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token, name="mdtest_patch",
         json_body={"body": md, "body_format": "markdown", "commit_message": "md formatter test"}, expect={200})
    _, d = call("GET", f"/v1/books/{s['book_id']}/chapters/{cid}/draft", token=token, name="mdtest_get", expect={200})
    body = d.get("body")
    doc = body if isinstance(body, dict) else (json.loads(body) if isinstance(body, str) else {})
    types = [n.get("type") for n in (doc or {}).get("content", [])]
    print(f"MDTEST: draft_format={d.get('draft_format')} blocks={types}")

def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    s = load_state(); token = login(); s["_run_at"] = datetime.datetime.now().isoformat()
    if phase in ("motifs", "all"): phase_motifs(token, s)
    if phase in ("setup", "all"): phase_setup(token, s)
    if phase in ("ontology", "all"): phase_ontology(token, s)
    if phase in ("structure", "all"): phase_structure(token, s)
    if phase in ("write", "all"): phase_write(token, s)
    if phase == "profile": phase_profile(token, s)
    if phase in ("extract", "all"): phase_extract(token, s)
    if phase == "mdtest": phase_mdtest(token, s)
    if phase == "stitch": phase_stitch(token, s)
    if phase == "satellite": phase_satellite(token, s)
    if phase == "pipeline": phase_pipeline(token, s)
    if phase == "drive": phase_drive(token, s)
    if phase == "grounding": phase_grounding(token, s)
    save_state(s)

if __name__ == "__main__":
    main()
