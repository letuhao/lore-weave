"""TOOL DEEP-DIVE `plan_bootstrap_propose` — the preview offered 2 chapters on a 6-chapter plan.

🔴 MEASURED LIVE 2026-08-13, book 019ff497-dff3-7f26-9565-7e284f7ca71c, run
019ff49a-f12b-732f-a0cf-73dd0cfcae76. The tool succeeded, returned
`{"status": "pending", "new_chapters_count": 2, ...}`, and persisted a real proposal row. Nothing
looked wrong: two chapters, real titles from this book's own glossary, no warning. The book's plan
holds SIX chapters (`outline_node` kind=chapter = 6, all `chapter_id IS NULL`, `chapters` in
book-service = 0), and both offered chapters carried `event_id` `arc_3_event_*`.

THE MECHANISM. `_autocompile_rules_run` calls `compile(created_by, book_id, run_id, arc_id=arc_id)`
once PER PARSED ARC, and each `compile` ends with `save_artifact(..., "package", ...)` scoped to
that arc. This run therefore holds THREE `package` artifacts — arc_1 "The Forged Path", arc_2 "The
Salt's Secret", arc_3 "The Great Unmapping", 20ms apart. `propose` read
`latest_artifact(..., "package")` and previewed the LAST arc only, dropping arcs 1-2 from the very
artifact a human approves from. `apply` replays that persisted diff verbatim, so the loss is real:
four planned chapters would never be created and nothing would say so.

The codebase had already learned this exact lesson one file over, for a sibling kind:
"BY TARGET, not `latest link_report`. Both linkers emit kind `link_report`, so a bare [latest]…"
"""

from types import SimpleNamespace

from app.services.bootstrap_service import compiled_package_across_arcs


def _art(art_id, arc_id, titles, seeds=(), *, package=True):
    content = {
        "glossary_seeds": [{"name": s, "kind_code": "character"} for s in seeds],
    }
    if package:
        content["planning_package"] = {
            "arc_id": arc_id,
            "chapters": [
                {"event_id": f"{arc_id}_event_{i}", "title": t, "ordinal": i}
                for i, t in enumerate(titles, start=1)
            ],
        }
    return SimpleNamespace(id=art_id, content=content)


def test_every_arc_reaches_the_preview():
    """🔴 THE DEFECT, with the live shape: three arcs, two chapters each."""
    arts = [
        _art("a1", "arc_1", ["Iseul finds the first discrepancy.", "The Guild's shadow."]),
        _art("a2", "arc_2", ["Forty years of deception.", "Rho Delkanen's part in it."]),
        _art("a3", "arc_3", ["The truth about the maps.", "A confrontation with the Guild."]),
    ]
    chapters, _ = compiled_package_across_arcs(arts)
    assert len(chapters) == 6, (
        "the preview still shows one arc's chapters; a human would approve 2 of the 6 chapters "
        "their plan actually holds, and the other 4 would never be created"
    )
    assert [c["event_id"] for c in chapters] == [
        "arc_1_event_1", "arc_1_event_2",
        "arc_2_event_1", "arc_2_event_2",
        "arc_3_event_1", "arc_3_event_2",
    ], "the arcs are not in compile order, so apply would create the book out of order"


def test_a_RECOMPILED_arc_is_not_offered_twice():
    """THE RULE A PLAIN CONCAT GETS WRONG. Re-compiling one arc appends another package for it;
    taking every artifact would double-offer that arc's chapters — and `apply` creates by title,
    so a double-offer is a double-create."""
    arts = [
        _art("a1", "arc_1", ["Chapter one."]),
        _art("a2", "arc_2", ["Chapter two."]),
        _art("a3", "arc_1", ["Chapter one, revised."]),  # arc_1 compiled again, later
    ]
    chapters, _ = compiled_package_across_arcs(arts)
    assert len(chapters) == 2, "a re-compiled arc is being offered twice"
    assert chapters[0]["title"] == "Chapter one, revised.", (
        "the STALE version of the re-compiled arc won; latest-per-arc means the newest content"
    )
    assert [c["title"] for c in chapters][1] == "Chapter two.", (
        "re-compiling arc_1 moved it after arc_2; a later re-compile must update an arc in place, "
        "not reorder the book"
    )


def test_glossary_seeds_are_folded_the_same_way():
    """The seeds ride the same artifact and were lost by the same read — a cast proposal would
    seed only the last arc's characters."""
    arts = [
        _art("a1", "arc_1", ["c1"], seeds=["Iseul Vantar"]),
        _art("a2", "arc_2", ["c2"], seeds=["Rho Delkanen"]),
    ]
    _, seeds = compiled_package_across_arcs(arts)
    assert [s["name"] for s in seeds] == ["Iseul Vantar", "Rho Delkanen"]


def test_a_package_with_no_arc_id_is_kept_not_collapsed():
    """THE CONTROL for the dedup key. A whole-run compile (or a pre-per-arc run) writes a package
    with no `arc_id`. Keying those on a shared default would collapse them into one and silently
    drop chapters — the very defect this fixes, re-introduced from the other side."""
    a = _art("a1", None, ["one"])
    b = _art("a2", None, ["two"])
    del a.content["planning_package"]["arc_id"]
    del b.content["planning_package"]["arc_id"]
    chapters, _ = compiled_package_across_arcs([a, b])
    assert len(chapters) == 2, "two arc-less packages were deduped against each other"


def test_an_artifact_with_no_compiled_package_is_skipped():
    """THE CONTROL for the uncompiled case: `propose` still has to be able to tell 'nothing is
    compiled' from 'compiled', and that decision reads the same artifacts."""
    chapters, seeds = compiled_package_across_arcs([_art("a1", "arc_1", ["x"], package=False)])
    assert chapters == [] and seeds == []


def test_propose_actually_reads_EVERY_package():
    """Guard the CALL SITE, not just the fold: a helper-level test stays green while `propose`
    goes on calling `latest_artifact`, and that single call IS the defect."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "app" / "services" / "bootstrap_service.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    fn = body[body.index("    async def propose("): body.index("    async def propose_seed(")]
    assert 'list_artifacts(book_id, run_id, "package")' in fn, (
        "propose still reads a single package artifact, so only one arc reaches the preview"
    )
    assert 'latest_artifact(book_id, run_id, "package")' not in fn, (
        "the latest-only read is still there"
    )
    assert "compiled_package_across_arcs(pkg_arts)" in fn, (
        "the artifacts are read but not folded across arcs"
    )


def test_the_previewed_ordinal_is_the_order_apply_will_create_in():
    """The compiler's ordinal is PER ARC, so a fold of three arcs reads 1,2,1,2,1,2 — three first
    chapters. `apply` ignores ordinal and creates in list order, so the preview must renumber to
    its own position or it describes a book that will never exist."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "app" / "services" / "bootstrap_service.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    fn = body[body.index("    async def propose("): body.index("    async def propose_seed(")]
    assert '"ordinal": i,' in fn and "enumerate(" in fn, (
        "the per-arc ordinal is passed through unchanged, so the preview shows repeated chapter "
        "numbers across arcs"
    )
    assert '"ordinal": ch.get("ordinal")' not in fn
