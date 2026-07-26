"""Tests for tier-tag-gate — the central C-TOOL tier gate (Track A / M9a).

Two things must hold: (1) the gate is CORRECT on the real tree (it passes today, and its
write/read verb classification does not false-flag a read-named tool that merely contains a
write NOUN — the `list_merge_candidates` regression), and (2) it is NON-VACUOUS (it actually
fails on a write-verb tool tagged Tier-R — the whole reason it exists).
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "tier-tag-gate.py"

# tier-tag-gate.py has a hyphen, so import it by path.
_spec = importlib.util.spec_from_file_location("tier_tag_gate", GATE)
ttg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ttg)


# ── verb classification (the heart of the write/read decision) ────────────────
def test_leading_read_verb_beats_a_write_noun():
    # `glossary_list_merge_candidates` LISTS candidates — "merge" is a noun. The gate must read
    # the LEADING verb (`list`), or it false-flags a read as a write (the regression it shipped
    # with on first run and this pins forever).
    assert ttg._verb("glossary_list_merge_candidates") == "list"
    assert ttg._verb("glossary_list_ai_suggestions") == "list"


def test_write_verb_behind_a_domain_noun_is_found():
    # `book_chapter_save_draft` — the domain/noun prefix must not hide the verb.
    assert ttg._verb("book_chapter_save_draft") == "save"
    assert ttg._verb("glossary_propose_status_change") == "propose"
    assert ttg._verb("book_chapter_delete") == "delete"


def test_verb_sets_are_disjoint():
    # A verb classified as both read and write would make the gate self-contradictory.
    assert not (ttg.WRITE_VERBS & ttg.READ_VERBS)
    assert not (ttg.WRITE_VERBS & ttg.REVIEW_VERBS)


# ── the Go scanner ────────────────────────────────────────────────────────────
def test_go_scanner_pairs_name_with_tier():
    go = '''
        addTool(srv, "book_chapter_delete",
            "Delete a chapter.",
            lwmcp.NewToolMeta(lwmcp.TierW, lwmcp.ScopeBook, nil, nil),
            s.toolDelete)
        addTool(srv, "book_get_chapter",
            "Read a chapter.",
            lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil),
            s.toolGet)
    '''
    pairs = dict(ttg._scan_go(go))
    assert pairs["book_chapter_delete"] == "W"
    assert pairs["book_get_chapter"] == "R"


# ── NON-VACUOUS: a write tagged R must FAIL ──────────────────────────────────
def test_a_write_verb_tagged_R_is_a_violation():
    go = '''addTool(srv, "book_chapter_delete", "d",
            lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil), h)'''
    tool, tier = ttg._scan_go(go)[0]
    assert tier == "R" and ttg._verb(tool) in ttg.WRITE_VERBS  # this is exactly what main() flags


def test_a_read_verb_tagged_R_is_fine():
    go = '''addTool(srv, "book_get_chapter", "r",
            lwmcp.NewToolMeta(lwmcp.TierR, lwmcp.ScopeBook, nil, nil), h)'''
    tool, tier = ttg._scan_go(go)[0]
    assert tier == "R" and ttg._verb(tool) not in ttg.WRITE_VERBS


# ── the gate PASSES on the real tree (no false positives today) ──────────────
def test_gate_passes_on_the_current_tree():
    r = subprocess.run([sys.executable, str(GATE)], capture_output=True, text=True)
    assert r.returncode == 0, f"tier-tag-gate FAILED on HEAD:\n{r.stdout}\n{r.stderr}"
    assert "every write-named tool carries a non-R tier" in r.stdout
