"""POC: how should the executor be told a kind's SCHEMA? (spec M6)

The wizard's live output proved the executor writes blind: it emits a fixed
character-shaped attribute set for every kind, so `terminology` (whose real
fields are term/definition/category/usage_note) produced EMPTY rows, and
power_system/item/organization got 2 of their 6-7 slots.

Arms (all gemma via LM Studio, $0):
  A  baseline-broken   — the CURRENT hardcoded character fields (proves the bug)
  B  full-schema       — the kind's real fields, codes only, one call per entity
  C  full+hints        — same, plus each field's authoring hint (is the hint worth tokens?)
  D  focused-slice     — required + a small core (<=4 fields), one call per entity
  E  batch-same-kind   — 3 entities of ONE kind in ONE call, one schema (token saving;
                         watch for the E2 monotonic-decay failure across positions)

Metrics: fill-rate (filled/asked), chars/field, valid JSON, prompt tokens (approx),
and for E the per-position decay.

Run: python eval/schema_recall_poc.py   → eval/out/schema_recall_poc.json
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

BASE = "http://localhost:1234/v1/chat/completions"
MODEL = "google/gemma-4-26b-a4b-qat"
NO_THINK = {"reasoning_effort": "none", "chat_template_kwargs": {"thinking": False}}

STORY = """\
Truyện "Mị Đế" — huyền huyễn tu chân khoa học. Tu luyện được lượng hóa bằng khoa học:
linh năng học đo lường và điều khiển linh năng; trận pháp là kỹ thuật xếp đặt cấu trúc
linh năng; luyện khí chế tạo pháp khí từ vật liệu có chỉ số. Thần hồn có năm tầng: Ký ức,
Nhân cách, Ý chí, Đạo tâm, Chân Linh — chỉ Chân Linh bất biến qua trùng sinh. Lâm Uyên sở
hữu Vô Cấu Chân Linh. Thanh Tâm Ấn là bí thuật chữa thần hồn, để lại một dấu ấn cực nhỏ —
chữ ký tần số Chân Linh — trong thần hồn người được chữa."""

# The REAL schemas, as measured from loreweave_glossary.book_attributes for this book.
SCHEMAS = {
    "terminology": [
        ("term", "Tên chuẩn của thuật ngữ."),
        ("definition", "Định nghĩa ngắn gọn, chính xác."),
        ("category", "Nhóm khái niệm mà thuật ngữ thuộc về."),
        ("usage_note", "Cách dùng, sắc thái, hoặc lưu ý khi nhắc tới trong truyện."),
    ],
    "power_system": [
        ("name", "Tên hệ thống sức mạnh."),
        ("description", "Cơ chế hoạt động, nền tảng của nó."),
        ("type", "Loại hệ thống (tu luyện, trận pháp, huyết mạch, ...)."),
        ("effects", "Nó cho phép làm được gì."),
        ("rank", "Thang bậc / cấp độ nếu có."),
        ("user", "Ai sử dụng được nó."),
        ("aliases", "Tên gọi khác."),
    ],
}
# The current (broken) hardcoded set — arm A.
BROKEN_FIELDS = ["gender", "role", "social_class", "affiliation",
                 "personality", "description", "goals", "secrets"]
# Arm D's focused core per kind (required-ish + what actually carries meaning).
FOCUSED = {"terminology": ["term", "definition"], "power_system": ["name", "description", "effects"]}

TERMS = ["Chân Linh", "Trận pháp", "Luyện khí"]
POWERS = ["Linh năng học"]


def call(messages, max_tokens=1400):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.4, **NO_THINK}
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    ch = out["choices"][0]
    approx_prompt_tok = sum(len(m["content"]) for m in messages) // 3
    return ch["message"].get("content") or "", time.time() - t0, approx_prompt_tok


def parse(text):
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


def score(obj, asked):
    """fill-rate + chars/field against the fields we ASKED for."""
    if not isinstance(obj, dict):
        return {"ok": False, "filled": 0, "asked": len(asked), "chars_per_field": 0}
    attrs = obj.get("attributes") if isinstance(obj.get("attributes"), dict) else obj
    vals = [str(attrs.get(f) or "").strip() for f in asked]
    filled = [v for v in vals if v]
    return {"ok": True, "filled": len(filled), "asked": len(asked),
            "fill_rate": round(len(filled) / max(1, len(asked)), 2),
            "chars_per_field": round(sum(len(v) for v in filled) / max(1, len(filled)))}


def build_one(name, kind, fields, hints=False):
    spec = ", ".join(f'"{c}"' + (f" ({h})" if hints else "") for c, h in fields)
    sysmsg = (f"Bạn là biên tập viên từ điển truyện. Trả về DUY NHẤT một JSON object: "
              f'{{"attributes": {{ ... }} }} với ĐÚNG các khoá sau: {spec}. '
              "Mỗi giá trị 1-3 câu CỤ THỂ. Viết bằng tiếng Việt.")
    user = f"BỐI CẢNH:\n{STORY}\n\nXây hồ sơ cho MỘT mục duy nhất: {name} (loại: {kind})."
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]


def run():
    res = {}

    # A — the CURRENT broken prompt (character fields on a terminology entity)
    fields_a = [(f, "") for f in BROKEN_FIELDS]
    txt, dt, tok = call(build_one("Chân Linh", "terminology", fields_a))
    real = [c for c, _ in SCHEMAS["terminology"]]
    obj = parse(txt)
    res["A_baseline_broken"] = {
        "asked_fields": BROKEN_FIELDS, "prompt_tok": tok, "secs": round(dt, 1),
        # scored against the REAL schema — what the glossary would actually accept
        "usable_vs_real_schema": score(obj, real),
    }

    # B/C/D — per-item arms over the same 3 terminology entities
    for arm, fields, hints in (
        ("B_full_schema", SCHEMAS["terminology"], False),
        ("C_full_plus_hints", SCHEMAS["terminology"], True),
        ("D_focused_slice", [f for f in SCHEMAS["terminology"]
                             if f[0] in FOCUSED["terminology"]], False),
    ):
        asked = [c for c, _ in fields]
        rows, toks, secs = [], 0, 0.0
        for n in TERMS:
            txt, dt, tok = call(build_one(n, "terminology", fields, hints))
            toks += tok; secs += dt
            rows.append({"name": n, **score(parse(txt), asked)})
        res[arm] = {"asked_fields": asked, "prompt_tok_total": toks,
                    "secs": round(secs, 1), "items": rows}

    # E — batch 3 same-kind entities in ONE call, ONE schema
    fields = SCHEMAS["terminology"]
    asked = [c for c, _ in fields]
    spec = ", ".join(f'"{c}"' for c, _ in fields)
    sysmsg = ("Bạn là biên tập viên từ điển truyện. Trả về DUY NHẤT một JSON ARRAY, "
              f'mỗi phần tử {{"name": "...", "attributes": {{ {spec} }} }}. '
              "Mỗi giá trị 1-3 câu CỤ THỂ. Viết bằng tiếng Việt.")
    user = (f"BỐI CẢNH:\n{STORY}\n\nXây hồ sơ cho CẢ 3 mục sau (loại: terminology): "
            + ", ".join(TERMS) + ".")
    txt, dt, tok = call([{"role": "system", "content": sysmsg},
                         {"role": "user", "content": user}], max_tokens=2200)
    arr = parse(txt)
    arr = arr if isinstance(arr, list) else []
    res["E_batch_same_kind"] = {
        "asked_fields": asked, "prompt_tok": tok, "secs": round(dt, 1),
        "returned": len(arr),
        # position matters: E2's failure was monotonic decay down the list
        "items": [{"pos": i, "name": (o or {}).get("name"), **score(o, asked)}
                  for i, o in enumerate(arr)],
    }

    # F — power_system (7 fields) full vs focused, to see if width hurts
    for arm, fields in (("F_power_full", SCHEMAS["power_system"]),
                        ("F_power_focused", [f for f in SCHEMAS["power_system"]
                                             if f[0] in FOCUSED["power_system"]])):
        asked = [c for c, _ in fields]
        txt, dt, tok = call(build_one(POWERS[0], "power_system", fields))
        res[arm] = {"asked_fields": asked, "prompt_tok": tok, "secs": round(dt, 1),
                    **score(parse(txt), asked)}
    return res


if __name__ == "__main__":
    out = run()
    os.makedirs("eval/out", exist_ok=True)
    with open("eval/out/schema_recall_poc.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    def agg(rows):
        oks = [r for r in rows if r.get("ok")]
        if not oks:
            return 0.0, 0
        return (round(sum(r["fill_rate"] for r in oks) / len(oks), 2),
                round(sum(r["chars_per_field"] for r in oks) / len(oks)))

    print(f"{'arm':<22}{'fill':>6}{'ch/fld':>8}{'tok':>7}  note")
    a = out["A_baseline_broken"]["usable_vs_real_schema"]
    print(f"{'A baseline(broken)':<22}{a.get('fill_rate', 0):>6}{a['chars_per_field']:>8}"
          f"{out['A_baseline_broken']['prompt_tok']:>7}  scored vs REAL schema")
    for arm in ("B_full_schema", "C_full_plus_hints", "D_focused_slice"):
        fr, cf = agg(out[arm]["items"])
        print(f"{arm:<22}{fr:>6}{cf:>8}{out[arm]['prompt_tok_total']:>7}  per-item x3")
    e = out["E_batch_same_kind"]
    fr, cf = agg(e["items"])
    print(f"{'E batch-3(same kind)':<22}{fr:>6}{cf:>8}{e['prompt_tok']:>7}  "
          f"returned {e['returned']}/3 | per-pos "
          + " ".join(f"{i['pos']}:{i.get('chars_per_field', 0)}" for i in e["items"]))
    for arm in ("F_power_full", "F_power_focused"):
        r = out[arm]
        print(f"{arm:<22}{r.get('fill_rate', 0):>6}{r['chars_per_field']:>8}"
              f"{r['prompt_tok']:>7}  {len(r['asked_fields'])} fields")
    print("saved eval/out/schema_recall_poc.json")
