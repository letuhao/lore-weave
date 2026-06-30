import json, pathlib

ROOT = pathlib.Path(r"D:/Works/source/lore-weave-mvp/docs/specs/2026-06-30-editor-compose-overhaul")
IO = ROOT / "poc/io"
OUT = ROOT / "story-export"
OUT.mkdir(exist_ok=True)
d = json.load(open(IO / "030_pipeline_poll27.json", encoding="utf-8"))
chs = d["response"]["result"]["decompose"]["chapters"]

idx = ["# Lâm Uyển — Truyện (12 chương, grounded + self-healed)\n",
       "> Sinh ra end-to-end bởi planning pipeline → grounded draft (Gemma 4 26B) → chapter self-heal.\n",
       "| Chương | Beat | Số ký tự | Đọc |", "|---|---|---|---|"]
total = 0
for i, c in enumerate(chs, 1):
    n = "%02d" % i
    hf = IO / f"drive_ch{n}_healed.txt"
    prose = hf.read_text(encoding="utf-8") if hf.exists() else ""
    total += len(prose)
    beat = c["chapter"].get("beat_role", "")
    intent = c["chapter"].get("intent", "")
    body = [f"# Chương {n} — {beat}\n", f"> _{intent}_\n", prose.strip() + "\n",
            f"\n[← Mục lục](00_index.md)" + (f" · [Chương %02d →](ch%02d.md)" % (i + 1, i + 1) if i < len(chs) else "")]
    (OUT / f"ch{n}.md").write_text("\n".join(body), encoding="utf-8")
    idx.append(f"| {i} | {beat} | {len(prose)} | [ch{n}.md](ch{n}.md) |")
idx.append(f"\n**Tổng: {total:,} ký tự văn xuôi qua {len(chs)} chương.**")
idx.append("\nPlan (synopsis) ở `../plan-export/`. Bản raw chưa heal ở `../poc/io/drive_chNN_raw.txt`.")
(OUT / "00_index.md").write_text("\n".join(idx), encoding="utf-8")
print("story-export:", len(list(OUT.glob("*.md"))), "files,", f"{total:,} chars total")
