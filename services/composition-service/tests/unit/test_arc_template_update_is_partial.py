"""TOOLV2 LOOP #155 — updating an arc template was impossible, on BOTH surfaces.

composition_arc_template_edit's description promises "only the fields you pass change". Measured on
its first invocation, every update failed identically:

    null value in column "visibility" of relation "arc_template" violates not-null constraint

and the field the caller asked to change was not written. It failed with one field supplied, with
all fields supplied, and through the legacy composition_arc_template_update as well. The op had
never worked.

ArcTemplateRepo.patch is correct: it builds its SET list from `model_dump(exclude_unset=True)`, so
a field the caller never mentioned stays untouched. The MCP handler defeated it by rebuilding the
patch model from a plain `model_dump()` — which materialises every optional field as an explicit
None — so the repo saw them all as set and emitted `visibility = NULL`.

The unified tool already drops unset fields with `_present()` before delegating, and `_present`'s
own docstring says a flat-superset op tool "must never force None onto a field whose default is a
non-None value". That care was undone one line later.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"
BODY = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _update_handler() -> str:
    start = BODY.index("async def composition_arc_template_update(")
    nxt = BODY.find("\nasync def ", start + 10)
    return BODY[start: nxt if nxt != -1 else len(BODY)]


def test_the_patch_model_is_built_from_set_fields_only():
    h = _update_handler()
    assert "exclude_unset=True" in h, (
        "the patch model is rebuilt from every field again — unset options become explicit None "
        "and the update writes NULL over columns the caller never mentioned"
    )


def test_the_plain_model_dump_form_does_not_come_back():
    h = _update_handler()
    assert 'ArcTemplatePatchArgs(**args.model_dump(exclude={"arc_id", "expected_version"}))' not in h


def test_the_repo_still_expects_partial_semantics():
    """If the repo ever stopped using exclude_unset, the flag above would be pointless and this
    guard should fail loudly rather than let the pair drift apart."""
    repo = (
        Path(__file__).resolve().parents[2]
        / "app" / "db" / "repositories" / "arc_template_repo.py"
    ).read_text(encoding="utf-8")
    assert "args.model_dump(exclude_unset=True)" in repo, (
        "the repo no longer derives its SET list from set-fields-only; the handler's exclude_unset "
        "assumes it does"
    )
