#!/usr/bin/env python3
"""
Generate frontend/src/data/languageCodes.ts from data/language_codes.txt.

Usage (run from repo root):
    python scripts/gen_language_codes.py
"""
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
INPUT = ROOT / "data" / "language_codes.txt"
OUTPUT = ROOT / "frontend" / "src" / "data" / "languageCodes.ts"

entries = []
with INPUT.open(encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if "\t" not in line:
            continue
        code, name = line.split("\t", 1)
        entries.append((code, name))

lines = ["// Auto-generated from data/language_codes.txt — do not edit by hand."]
lines.append("export type LangEntry = { code: string; name: string };")
lines.append("")
lines.append("export const LANGUAGE_CODES: LangEntry[] = [")
for code, name in entries:
    name_escaped = name.replace("'", "\\'")
    lines.append(f"  {{ code: '{code}', name: '{name_escaped}' }},")
lines.append("];")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Written {len(entries)} entries to {OUTPUT}")
