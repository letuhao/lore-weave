"""TOOLV2 LOOP #253 — the same false sequencing, in four more places, after #247 "fixed" it.

#247 established the fact: the K17.9 benchmark became advisory on 2026-07-27 and gates nothing.
It corrected the sites its census found. That census was a grep for two phrases, and it missed
these, which say the same thing in different words:

    mcp/server.py           "… Then call kg_run_benchmark, then kg_build (target=\"graph\")."
    tools/definitions.py    "… then kg_run_benchmark, then kg_build_graph."
    tools/project_tools.py  the changed=False branch: "already configured — next call
                             kg_run_benchmark, then kg_build_graph"
    tools/definitions.py    "the step BETWEEN kg_project_create and kg_run_benchmark"

The third is the one that stings: #247 corrected the changed=True note in that same function and
left its sibling branch alone. So a caller setting a model for the first time was told the truth,
and a caller re-running the tool — the exact caller most likely to be confused already — got the
retired instruction back. That is the half-fix shape #252's guard was written to catch, committed
by me, one iteration later.

Twice now a phrase-grep has under-counted (#247 missed "enables" while grepping "enabled"). So this
guard does not enumerate sites. It scans EVERY python file under app/ for the sequencing pattern
itself, and any new occurrence anywhere fails it — including in a file that does not exist yet.

What is deliberately still allowed: saying that an EMBEDDING MODEL is a precondition both
kg_run_benchmark and kg_build require. That is true — the benchmark needs a model to benchmark.
Only the ordering claim, "do the benchmark, then you may build", is false.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

# "kg_run_benchmark … then … build" in one breath, in either order, across line breaks and the
# adjacent-string-literal joins these descriptions are assembled from.
_SEQUENCING = re.compile(
    r"kg_run_benchmark[^.]{0,120}?then[^.]{0,60}?kg_build"
    r"|then[^.]{0,60}?kg_run_benchmark[^.]{0,120}?then[^.]{0,60}?kg_build",
    re.IGNORECASE | re.DOTALL,
)


def _sources() -> list[Path]:
    return sorted(APP.rglob("*.py"))


def _flat(path: Path) -> str:
    """Source with adjacent-string-literal joins collapsed.

    These descriptions are assembled from implicitly-concatenated literals, so a sentence that
    is contiguous ON THE WIRE is split by `" \\n "` in the source. Every naive phrase assertion
    written against this codebase so far has tripped on exactly that — three times in this loop
    alone. Match the wire form, not the formatting.
    """
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    return re.sub(r'"\s*\n\s*"', "", text)


def test_no_file_sequences_the_benchmark_before_the_build():
    offenders = []
    for path in _sources():
        for m in _SEQUENCING.finditer(_flat(path)):
            offenders.append(f"{path.relative_to(APP)}: …{m.group(0)[:110]}…")
    assert offenders == [], (
        "these sites tell a caller to run the benchmark before building. K17.9 has been "
        "advisory since 2026-07-27 and gates nothing:\n  " + "\n  ".join(offenders)
    )


def test_both_branches_of_the_set_model_note_agree():
    """The changed=True and changed=False notes are the same statement to the same caller. #247
    corrected one and left the other, so re-running the tool re-taught the retired sequencing."""
    body = _flat(APP / "tools" / "project_tools.py")
    assert body.count("kg_run_benchmark is OPTIONAL") == 2, (
        "expected the OPTIONAL wording in BOTH the changed=True and changed=False notes"
    )
    assert "next call kg_run_benchmark" not in body


def test_the_true_precondition_claim_is_untouched():
    """An embedding model IS required by both tools — the benchmark needs something to
    benchmark. Sweeping that away with the false ordering claim would trade one wrong statement
    for another."""
    body = _flat(APP / "tools" / "project_tools.py")
    assert "`kg_run_benchmark` and `kg_build_graph` both require" in body


def test_the_pattern_would_actually_catch_the_wording_it_was_written_for():
    """A guard that cannot go red is decoration. Exercise the regex against the four real strings
    this iteration removed, so a later 'simplification' of the pattern is caught here."""
    for sample in (
        'Then call kg_run_benchmark, then kg_build (target="graph").',
        "then kg_run_benchmark, then kg_build_graph.",
        "already configured — next call kg_run_benchmark, then kg_build_graph",
        'call kg_project_set_embedding_model then kg_run_benchmark first, then kg_build_graph',
    ):
        assert _SEQUENCING.search(sample), f"the pattern no longer matches: {sample!r}"
