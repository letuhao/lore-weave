import pathlib, re
raw = re.search(r"```\n(.*?)\n```", pathlib.Path(
    r"d:/Works/source/lore-weave/docs/plans/2026-08-12-frontend-journey-loop-GOAL.md"
).read_text(encoding="utf-8"), re.S).group(1)
new = re.sub(r"\s+", " ", raw).lower()   # collapse the wrapping

proven = [
 ("one at a time, in a derived order",           "one journey at a time"),
 ("never choose/reorder/batch/skip/defer",       "never choose, reorder, batch, skip or defer"),
 ("on conclusion, immediately take the next",    "immediately derive"),
 ("do not return control while work remains",    "do not return control while executable work remains"),
 ("the goal is NOT complete while work remains", "goal is not complete"),
 ("the ledger is the progress authority",        "progress authority"),
 ("never stop with ready-for-next / continue?",  "ready for next"),
 ("never stop with a HANDOFF or PROGRESS REPORT","progress report"),
 ("non-terminal words listed",                   "mostly works"),
 ("a failed verification does not advance",      "does not advance"),
 ("CODE leg + falsifier red on the original",    "falsifier proven red on the original"),
 ("LIVE leg against the real deployed thing",    "images verified current"),
 ("DATA leg + never type a denominator",         "never a typed denominator"),
 ("fix the defect wherever it lives",            "it lives"),
 ("PROSE IS NOT THE LEVER",                      "prose is not the lever"),
 ("defer, record, continue",                     "record the question"),
]
missing = [n for n, k in proven if k not in new]
print(f"invariants carried: {len(proven)-len(missing)}/{len(proven)}   (was 11/16 before fixing the checker)\n")
print("GENUINELY MISSING:")
for n in missing:
    print("   -", n)
