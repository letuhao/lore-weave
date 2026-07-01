import json, os, pathlib

ROOT = pathlib.Path(r"D:/Works/source/lore-weave-mvp/docs/specs/2026-06-30-editor-compose-overhaul")
OUT = ROOT / "plan-export"
OUT.mkdir(exist_ok=True)
d = json.load(open(ROOT / "poc/io/030_pipeline_poll27.json", encoding="utf-8"))
res = d["response"]["result"]
premise = d["response"]["input"].get("premise", "")
dec = res["decompose"]
chs = dec["chapters"]

# cast attrs from the glossary TSV: {name: {attr: val}}
attrs = {}
tsv = pathlib.Path(os.environ["TEMP"]) / "cast_attrs.tsv"
for line in tsv.read_text(encoding="utf-8").splitlines():
    parts = line.split("\t")
    if len(parts) == 3:
        attrs.setdefault(parts[0], {})[parts[1]] = parts[2]

cast = res.get("cast", [])
motifs = res.get("motifs", [])
arcs = res.get("char_arcs", [])
hr = res.get("heal_report") or {}
intro = {a["name"]: a.get("introduce_at_chapter") for a in arcs}

# ── 00_overview.md ──
o = ["# Kế hoạch truyện — Tổng quan\n",
     "> Sinh ra bởi planning pipeline (Stages 0–6): cast → motif → tension → char-arc/intro → grounded decompose → plan self-heal.\n",
     "## Tiền đề\n", premise + "\n",
     "## Dàn nhân vật\n",
     "| Tên | Vai | Giới thiệu @chương | Tính cách | Quan hệ | Mô tả |",
     "|---|---|---|---|---|---|"]
for c in cast:
    a = attrs.get(c["name"], {})
    ic = intro.get(c["name"])
    ic = f"ch{ic}" if ic and ic > 1 else "từ đầu"
    o.append(f"| {c['name']} | {c.get('role','')} | {ic} | {a.get('personality','')} | {a.get('relationships','')} | {a.get('description','')} |")
o.append("\n## Motif chủ đề\n")
o.append("| Motif | Vai trò trong arc |\n|---|---|")
for m in motifs:
    o.append(f"| {m.get('name','')} | {m.get('arc_role','')} |")
o.append("\n## Đường tension (theo chương)\n")
o.append("| Chương | Beat | Tension các scene |\n|---|---|---|")
for i, c in enumerate(chs, 1):
    ts = [s.get("tension") for s in c.get("scenes", [])]
    o.append(f"| {i} | {c['chapter'].get('beat_role')} | {ts} |")
o.append("\n## Plan self-heal — các lỗi đã sửa\n")
o.append(f"**{hr.get('edits_applied',0)}/{len(hr.get('findings',[]))} finding đã sửa.**\n")
o.append("| Chương·Scene | Loại | Vấn đề | Cách sửa | Trạng thái |\n|---|---|---|---|---|")
for f in hr.get("findings", []):
    tag = "✅ sửa" if f.get("applied") else (f.get("skip_reason") or "?")
    o.append(f"| CH{f.get('chapter')}·S{f.get('scene')} | {f.get('type','')} | {(f.get('issue','') or '')[:90]} | {(f.get('fix','') or '')[:80]} | {tag} |")
o.append("\n## Mục lục chương\n")
for i, c in enumerate(chs, 1):
    o.append(f"- [Chương {i:02d} — {c['chapter'].get('beat_role')}](ch{i:02d}.md): {(c['chapter'].get('intent') or '')[:80]}")
(OUT / "00_overview.md").write_text("\n".join(o), encoding="utf-8")

# ── chNN.md per chapter ──
for i, c in enumerate(chs, 1):
    ch = c["chapter"]
    intros_here = [n for n, k in intro.items() if k == i]
    p = [f"# Chương {i:02d} — {ch.get('beat_role')}\n",
         f"**Intent (đích chương):** {ch.get('intent','')}\n"]
    if intros_here:
        p.append(f"**Giới thiệu nhân vật mới:** {', '.join(intros_here)}\n")
    p.append(f"_{len(c.get('scenes',[]))} scene · tension {[s.get('tension') for s in c.get('scenes',[])]}_\n")
    for j, s in enumerate(c.get("scenes", []), 1):
        p.append(f"## Scene {j} — tension {s.get('tension')}")
        if s.get("title"):
            p.append(f"**{s['title']}**\n")
        p.append((s.get("synopsis") or "") + "\n")
    p.append(f"\n[← Tổng quan](00_overview.md)" + (f" · [Chương {i+1:02d} →](ch{i+1:02d}.md)" if i < len(chs) else ""))
    (OUT / f"ch{i:02d}.md").write_text("\n".join(p), encoding="utf-8")

print("exported", len(list(OUT.glob("*.md"))), "md files to", OUT)
print("\n".join(sorted(x.name for x in OUT.glob("*.md"))))
