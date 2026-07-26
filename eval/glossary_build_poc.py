"""POC for the glossary-build planner/executor decomposition (spec 2026-07-27).

Calls gemma DIRECTLY through LM Studio (localhost:1234, $0) to measure, before any
service code exists:

  E1 vertical        — ONE focused call builds ONE entity richly (depth baseline).
  E2 horizontal-naive — ONE call asked to build EVERYTHING with full detail
                        (predicted failure: depth collapse / truncation).
  E3 planner→executor — planner enumerates the worklist (breadth), then one
                        executor call PER item (depth). The proposed shape.

Success: E3 per-entity depth ≈ E1, E3 coverage ≥ E2, all JSON valid, no loops.

Run:  python eval/glossary_build_poc.py            (writes eval/out/glossary_build_poc.json)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request

BASE = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-26b-a4b-qat"

# _NO_THINK — mirrors production compress.py: QAT is a thinking model; without this it
# dumps to reasoning_content and content comes back empty.
NO_THINK = {"reasoning_effort": "none", "chat_template_kwargs": {"thinking": False}}

STORY = """\
Truyện "Mị Đế" — huyền huyễn tu chân khoa học. Tu luyện được lượng hóa bằng khoa học:
linh năng học, trận pháp, luyện khí, vật liệu. Gia tộc là đơn vị quyền lực tối cao;
lòng tốt thường bị xem là điểm yếu.

Lâm Uyên là thiếu chủ dòng chính Lâm gia, thiên phú tuyệt thế, người kế vị mặc định,
thiện lương chính trực nhưng quá tin người. Hôn thê của hắn là Tô Thanh Dao, đại tiểu
thư Tô gia, thông minh lý trí — nàng không yêu Lâm Uyên mà thầm yêu Lâm Trạch, người
của phân gia Lâm gia, bạn thân từ nhỏ của Lâm Uyên, kẻ luôn sống dưới cái bóng của hắn
và khao khát vị trí gia chủ. Huyết Vô Thường, thiên tài ma đạo, đã sát hại em gái của
Tô Thanh Dao; Lâm Uyên đánh bại hắn nhưng tha mạng, và khi tha mạng đã dùng bí thuật
Thanh Tâm Ấn — vô tình để lại "chữ ký" Chân Linh trong thần hồn đối phương. Trong một
lần tranh đoạt cơ duyên, Lâm Uyên rơi vào bẫy do chính Lâm Trạch và Tô Thanh Dao bố trí,
chết trong tuyệt vọng — mở đầu cho trùng sinh."""

KINDS = ["character", "organization", "event", "terminology", "power_system", "relationship", "location", "item"]

ENTITY_SCHEMA_HINT = """\
Trả về DUY NHẤT một JSON object (không markdown, không giải thích) theo dạng:
{"name": "...", "kind": "<một trong: %s>",
 "attributes": {"gender": "...", "role": "...", "social_class": "...", "affiliation": "...",
                "personality": "...", "description": "...", "goals": "...", "secrets": "..."},
 "relations": [{"target_name": "...", "type": "<ally_of|enemy_of|member_of|betrothed_to|loves|killed|spared|betrayed>", "note": "..."}]}
Thuộc tính nào không áp dụng cho kind này thì bỏ qua; mỗi giá trị viết 1-3 câu CỤ THỂ, có chi tiết riêng.""" % ("|".join(KINDS))


def call(messages: list[dict], max_tokens: int = 2200) -> tuple[str, float, str]:
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.4, **NO_THINK}
    t0 = time.time()
    req = urllib.request.Request(
        BASE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    ch = out["choices"][0]
    return ch["message"].get("content") or "", time.time() - t0, ch.get("finish_reason", "?")


def parse_json(text: str):
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def depth(entity: dict) -> dict:
    attrs = entity.get("attributes") or {}
    vals = [str(v) for v in attrs.values() if v]
    return {
        "n_attrs": len(vals),
        "chars_per_attr": round(sum(len(v) for v in vals) / max(1, len(vals))),
        "n_relations": len(entity.get("relations") or []),
    }


def e1_vertical() -> dict:
    sys_p = "Bạn là biên tập viên hồ sơ nhân vật cho tiểu thuyết huyền huyễn. " + ENTITY_SCHEMA_HINT
    user = (f"BỐI CẢNH TRUYỆN:\n{STORY}\n\n"
            "Xây dựng hồ sơ THẬT CHI TIẾT cho MỘT nhân vật duy nhất: Tô Thanh Dao.")
    text, dt, fin = call([{"role": "system", "content": sys_p}, {"role": "user", "content": user}])
    ent = parse_json(text)
    return {"ok": ent is not None, "secs": round(dt, 1), "finish": fin,
            "depth": depth(ent) if ent else None, "raw_head": text[:200]}


def e2_horizontal_naive() -> dict:
    sys_p = ("Bạn là biên tập viên hồ sơ cho tiểu thuyết huyền huyễn. Trả về DUY NHẤT một JSON "
             "ARRAY các entity object, mỗi object theo dạng sau:\n" + ENTITY_SCHEMA_HINT)
    user = (f"BỐI CẢNH TRUYỆN:\n{STORY}\n\n"
            "Xây dựng hồ sơ THẬT CHI TIẾT cho TẤT CẢ nhân vật, gia tộc, sự kiện, thuật ngữ, "
            "hệ thống sức mạnh và quan hệ mà đoạn trên thiết lập — đầy đủ thuộc tính cho từng cái.")
    text, dt, fin = call([{"role": "system", "content": sys_p}, {"role": "user", "content": user}], max_tokens=4000)
    ents = parse_json(text)
    ents = ents if isinstance(ents, list) else ([ents] if ents else [])
    return {"ok": bool(ents), "secs": round(dt, 1), "finish": fin, "coverage": len(ents),
            "names": [e.get("name") for e in ents if isinstance(e, dict)],
            "depths": [depth(e) for e in ents if isinstance(e, dict)]}


def e3_planner_executor() -> dict:
    # planner: BREADTH ONLY — enumerate, no detail
    plan_sys = ("Bạn là người lập kế hoạch xây dựng từ điển truyện. Trả về DUY NHẤT một JSON array: "
                '[{"name":"...","kind":"<%s>","why":"1 câu"}]. '
                "KHÔNG viết thuộc tính chi tiết — chỉ liệt kê." % "|".join(KINDS))
    plan_user = (f"BỐI CẢNH TRUYỆN:\n{STORY}\n\n"
                 "Liệt kê MỌI entity đáng đưa vào từ điển truyện (nhân vật, gia tộc, sự kiện, "
                 "thuật ngữ, hệ thống sức mạnh, quan hệ). Đã có sẵn: Lâm Uyên, Lâm gia — bỏ qua 2 cái đó.")
    ptext, pdt, pfin = call([{"role": "system", "content": plan_sys}, {"role": "user", "content": plan_user}], max_tokens=1200)
    worklist = parse_json(ptext) or []
    items = [w for w in worklist if isinstance(w, dict) and w.get("name")]

    # executor: DEPTH, one call per item (cap at 6 for POC runtime)
    built, exec_secs = [], 0.0
    sys_p = "Bạn là biên tập viên hồ sơ cho tiểu thuyết huyền huyễn. " + ENTITY_SCHEMA_HINT
    for w in items[:6]:
        user = (f"BỐI CẢNH TRUYỆN:\n{STORY}\n\n"
                f"Xây dựng hồ sơ THẬT CHI TIẾT cho MỘT entity duy nhất: {w['name']} (kind: {w.get('kind','?')}).")
        text, dt, fin = call([{"role": "system", "content": sys_p}, {"role": "user", "content": user}])
        exec_secs += dt
        ent = parse_json(text)
        built.append({"name": w["name"], "ok": ent is not None, "finish": fin,
                      "depth": depth(ent) if ent else None})
    return {"planner_ok": bool(items), "planner_secs": round(pdt, 1), "planner_finish": pfin,
            "worklist": [(w.get("name"), w.get("kind")) for w in items],
            "coverage": len(items), "built": built, "exec_secs": round(exec_secs, 1)}


if __name__ == "__main__":
    res = {}
    for name, fn in (("E1_vertical", e1_vertical),
                     ("E2_horizontal_naive", e2_horizontal_naive),
                     ("E3_planner_executor", e3_planner_executor)):
        print(f"== {name} ...", flush=True)
        try:
            res[name] = fn()
        except Exception as exc:  # noqa: BLE001 — POC: record and continue
            res[name] = {"error": str(exc)}
        print(json.dumps(res[name], ensure_ascii=False)[:600], flush=True)
    import os
    os.makedirs("eval/out", exist_ok=True)
    with open("eval/out/glossary_build_poc.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("saved eval/out/glossary_build_poc.json")
    sys.exit(0)
