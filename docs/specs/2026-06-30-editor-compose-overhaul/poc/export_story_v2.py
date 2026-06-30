import json, pathlib, re

ROOT = pathlib.Path(r"D:/Works/source/lore-weave-mvp/docs/specs/2026-06-30-editor-compose-overhaul")
IO = ROOT / "poc/io"
OLD = ROOT / "story-export"
OUT = ROOT / "story-export-v2"
OUT.mkdir(exist_ok=True)
summ = {r["ch"]: r for r in json.load(open(IO / "heal_v2_summary.json", encoding="utf-8"))}

idx = ["# Lâm Uyển — Truyện v2 (heal lại bằng cheap-stack: grounded judge + vote-5 + verify + prefilter)\n",
       "> Cùng bản nháp grounded, heal lại trên model local $0 với canon cấp-sách (9 nhân vật).",
       "> So sánh: bản v1 ở `../story-export/`, bản nháp thô ở `../poc/io/drive_chNN_raw.txt`.\n",
       "| Chương | Beat | x len | sửa | verify-bác | Đọc |", "|---|---|---|---|---|---|"]
total = 0
for i in range(1, 13):
    n = "%02d" % i
    hf = IO / f"drive_ch{n}_healed_v2.txt"
    prose = hf.read_text(encoding="utf-8") if hf.exists() else ""
    total += len(prose)
    # beat + intent from the v1 export header/blockquote
    beat, intent = "", ""
    of = OLD / f"ch{n}.md"
    if of.exists():
        lines = of.read_text(encoding="utf-8").splitlines()
        m = re.match(r"# Chương \d+ — (.+)", lines[0]) if lines else None
        beat = m.group(1).strip() if m else ""
        for ln in lines[:4]:
            mm = re.match(r"> _(.+)_", ln)
            if mm:
                intent = mm.group(1).strip()
                break
    s = summ.get(n, {})
    body = [f"# Chương {n} — {beat}\n", f"> _{intent}_\n",
            f"> heal v2: x{s.get('ratio','?')} · {s.get('edits','?')} sửa · {s.get('refuted','?')} finding bị verify bác\n",
            prose.strip() + "\n",
            f"\n[← Mục lục](00_index.md)" + (f" · [Chương %02d →](ch%02d.md)" % (i + 1, i + 1) if i < 12 else "")]
    (OUT / f"ch{n}.md").write_text("\n".join(body), encoding="utf-8")
    idx.append(f"| {i} | {beat} | x{s.get('ratio','?')} | {s.get('edits','?')} | {s.get('refuted','?')} | [ch{n}.md](ch{n}.md) |")
idx.append(f"\n**Tổng: {total:,} ký tự qua 12 chương.** Bug đã biết: dup-word collapser có thể flatten điệp ngữ hợp lệ (xem SESSION).")
(OUT / "00_index.md").write_text("\n".join(idx), encoding="utf-8")
print("story-export-v2:", len(list(OUT.glob("*.md"))), "files,", f"{total:,} chars")
