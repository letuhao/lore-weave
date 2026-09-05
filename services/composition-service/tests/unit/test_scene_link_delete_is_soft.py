"""TOOLV2 LOOP #219 — scene_link_delete was described as a hard delete. It is a soft archive.

Measured: after deleting two scene links the rows were still present with is_archived = true, and
the repository confirms it —

    UPDATE scene_link SET is_archived = true WHERE project_id = $1 AND id = $2 AND NOT is_archived

The implementation was deliberately changed and the description was left behind. The handler's own
comment records the change and the reason: "was `undo_hint: None` — an explicit 'no undo' over a
HARD delete that destroyed the author's declared connection and its authored label. The delete is
now soft, so the hint can name a real reverse op."

It matters beyond tidiness. A caller told "hard delete" treats an accidental unlink as unrecoverable
and will not look for the row; told it is archived, the same caller knows the connection and its
label survive. And the sibling composition_motif_link_delete really IS hard — #204 measured its row
count going to 0 against a table with no lifecycle column — so the two "delete" tools genuinely
differ and only one description was true.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
REPO = Path(__file__).resolve().parents[2] / "app" / "db" / "repositories" / "scene_links.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _scene_link_delete_description() -> str:
    start = BODY.index('name="composition_scene_link_delete"')
    return BODY[start: BODY.index("meta=require_meta", start)]


def test_the_hard_delete_claim_is_gone():
    assert "hard delete" not in _scene_link_delete_description(), (
        "scene_link_delete claims a hard delete again; measured, it sets is_archived"
    )


def test_the_description_states_what_actually_happens_and_why_it_matters():
    desc = _scene_link_delete_description()
    assert "SOFT archive" in desc
    assert "is_archived" in desc, "name the mechanism, so the claim is checkable"
    # The consequence a caller acts on: the authored label is not destroyed.
    assert "label" in desc


def test_the_repository_really_soft_archives():
    """If the repo ever goes back to DELETE FROM, this description becomes the false one and the
    guard above would be pinning a lie."""
    repo = REPO.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "UPDATE scene_link SET is_archived = true" in repo
    assert "DELETE FROM scene_link" not in repo


def test_the_motif_link_sibling_keeps_its_accurate_hard_delete_wording():
    """#204 measured motif_link_delete removing the row from a table with no lifecycle column.
    That description is TRUE and must not be swept along with this correction."""
    start = BODY.index('name="composition_motif_link_delete"')
    assert "hard delete" in BODY[start: BODY.index("meta=require_meta", start)]
