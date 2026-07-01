import json, pathlib, re

ROOT = pathlib.Path(r"D:/Works/source/lore-weave-mvp/docs/specs/2026-06-30-editor-compose-overhaul")
IO = ROOT / "poc/io"
OLD = ROOT / "story-export"
OUT = ROOT / "story-export-v3"
OUT.mkdir(exist_ok=True)
summ = {r["ch"]: r for r in json.load(open(IO / "heal_v3_summary.json", encoding="utf-8"))}

idx = ["# Lâm Uyển — Truyện v3 (verify_k=3 + canon render từ cast)\n",
       "> Cùng bản nháp grounded, heal lại trên model local $0 với verify-vote (k=3) + canon",
       "> render từ cast pipeline. So sánh: v1 `../story-export/`, v2 `../story-export-v2/`.\n",
       "| Chương | x len | sửa | verify-bác | Đọc |", "|---|---|---|---|---|"]
total = 0
for i in range(1, 13):
    n = "%02d" % i
    hf = IO / f"drive_ch{n}_healed_v3.txt"
    prose = hf.read_text(encoding="utf-8") if hf.exists() else ""
    total += len(prose)
    beat = ""
    of = OLD / f"ch{n}.md"
    if of.exists():
        m = re.match(r"# Chương \d+ — (.+)", of.read_text(encoding="utf-8").splitlines()[0])
        beat = m.group(1).strip() if m else ""
    s = summ.get(n, {})
    body = [f"# Chương {n} — {beat}\n",
            f"> heal v3: x{s.get('ratio','?')} · {s.get('edits','?')} sửa · {s.get('refuted','?')} bị verify bác\n",
            prose.strip() + "\n",
            f"\n[← Mục lục](00_index.md)" + (f" · [Chương %02d →](ch%02d.md)" % (i + 1, i + 1) if i < 12 else "")]
    (OUT / f"ch{n}.md").write_text("\n".join(body), encoding="utf-8")
    idx.append(f"| {i} | x{s.get('ratio','?')} | {s.get('edits','?')} | {s.get('refuted','?')} | [ch{n}.md](ch{n}.md) |")
idx.append(f"\n**Tổng: {total:,} ký tự.** Lưu ý trung thực: đại từ ông/bà = 0 toàn bộ (prefilter); "
           "CH01 'mẫu thân ngươi' VẪN còn (verify stochastic + thiên bác) — đúng phần human-gate cần lo.")
(OUT / "00_index.md").write_text("\n".join(idx), encoding="utf-8")
print("story-export-v3:", len(list(OUT.glob("*.md"))), "files,", f"{total:,} chars")
