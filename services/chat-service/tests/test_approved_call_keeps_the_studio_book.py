"""TOOL DEEP-DIVE `plan_bootstrap_propose` — the studio's single-book knowledge did not survive
a suspend, so the ONLY calls running with unrepaired arguments were the ones a human approved.

🔴 MEASURED LIVE 2026-08-12, book 019ff497 (studio, gemma-4-26b via lm_studio). The model called
plan_bootstrap_propose with a correct run_id and `book_id=019ff497-e068-77db-89f7-9d8c298fe8cd` —
the book's KNOWLEDGE PROJECT id. chat-service logged the repair on the streaming pass:

    tool arg book_id='019ff497-e068-…' differs from the studio's book 019ff497-dff3-… —
    overriding (the studio works one book at a time; a cross-book target here is a hallucination)

The call then suspended on its Tier-A card, the author approved it, and composition-service was
asked for `/internal/books/019ff497-e068-…/access` — the WRONG id, three times in that turn. The
approved write failed "not found or not accessible" on a book the author owns and had open.

ONE MECHANISM, TWO SITES, and the RUNBOOK's test says that is one defect:
  (a) the approved dispatch in `resume_stream_response` handed the RAW saved args to the
      executor — no context-id fill, no malformed-UUID substitution, no studio override;
  (b) the resumed continuation rebuilt `context_ids` as `{"book_id": …}` with no `studio`, so
      `_inject_context_ids` saw studio=False and the override was dead for the rest of the turn.

Both need the flag PERSISTED, because the /tool-results request carries no studio signal — the
same reason `permission_mode` is already persisted ("the resume continues under the mode the turn
started with").
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"
SUSP = Path(__file__).resolve().parents[1] / "app" / "db" / "suspended_runs.py"
MIG = Path(__file__).resolve().parents[1] / "app" / "db" / "migrate.py"

BOOK = "019ff497-dff3-7f26-9565-7e284f7ca71c"
PROJECT = "019ff497-e068-77db-89f7-9d8c298fe8cd"


def test_the_approved_call_does_not_run_on_the_hallucinated_book():
    """🔴 THE DEFECT. The exact args the live card was approved on."""
    from app.services.stream_service import _repair_saved_book_id

    args = {"book_id": PROJECT, "run_id": "019ff49a-f12b-732f-a0cf-73dd0cfcae76"}
    _repair_saved_book_id(args, book_id=BOOK, studio=True)
    assert args["book_id"] == BOOK, (
        "the approved Tier-A call still dispatches on the book_id the model hallucinated, even "
        "though the repair for it fired one pass earlier and was simply never persisted"
    )
    assert args["run_id"] == "019ff49a-f12b-732f-a0cf-73dd0cfcae76", (
        "the repair touched an argument that is not its business"
    )


def test_a_malformed_book_id_is_a_mistranscription_not_a_cross_book_call():
    """A weak model mistranscribes a UUID; that is never a deliberate cross-book target, so this
    rule holds OFF the studio too — exactly as on the streaming path."""
    from app.services.stream_service import _repair_saved_book_id

    args = {"book_id": BOOK + "e"}
    _repair_saved_book_id(args, book_id=BOOK, studio=False)
    assert args["book_id"] == BOOK


def test_OFF_the_studio_a_different_book_is_still_honored():
    """THE CONTROL, and the reason `studio` had to be persisted rather than inferred from
    book_id: a plain book-surface turn also carries a book, and a valid-but-different book_id
    there is a real cross-book call the streaming path promises to honor. Inferring would turn
    this fix into a silent redirect of someone else's legitimate call."""
    from app.services.stream_service import _repair_saved_book_id

    other = "019ff4cf-2143-7a5f-9cc4-0cf62e286432"
    args = {"book_id": other}
    _repair_saved_book_id(args, book_id=BOOK, studio=False)
    assert args["book_id"] == other, (
        "an off-studio cross-book call is being silently redirected to another book"
    )


def test_it_never_ADDS_a_book_id_the_tool_did_not_ask_for():
    """THE CONTROL for the missing schema. The resume dispatch has no tool_defs, so this repair
    may only ADJUST a key already present. Adding one to a tool that does not declare it (or
    that resolves book ambiently) is what the schema check exists to prevent."""
    from app.services.stream_service import _repair_saved_book_id

    args = {"run_id": "019ff49a-f12b-732f-a0cf-73dd0cfcae76"}
    _repair_saved_book_id(args, book_id=BOOK, studio=True)
    assert "book_id" not in args, (
        "the resume repair invented a book_id argument without ever seeing the tool's schema"
    )


def test_the_approved_dispatch_actually_calls_the_repair():
    """Guard the CALL SITE, not the helper: a helper-level test stays green when the fix is
    never wired in, and this defect IS a missing wiring."""
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    at = body.index("async def resume_stream_response(")
    resume = body[at:]
    call = resume.index("_repair_saved_book_id(_tool_args")
    dispatch = resume.index("envelope = await knowledge_client.mcp_execute_tool(")
    assert call < dispatch, (
        "the approved args are repaired after (or instead of) being dispatched, which repairs "
        "nothing"
    )


def test_the_resumed_turn_still_knows_it_is_a_studio_turn():
    """Site (b). `_inject_context_ids` keys the single-book override off context_ids['studio'];
    a resume that rebuilds the dict without it disables the override for the whole rest of the
    turn — which is what let composition_package_tree and plan_propose_spec run on the wrong
    book right after the approval."""
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert '"studio": bool(susp.studio)' in body, (
        "the resumed continuation no longer carries the studio flag, so the single-book "
        "override is dead for every tool called after an approval"
    )


def test_the_studio_flag_is_PERSISTED_across_the_suspend():
    """The /tool-results request carries no studio signal, so an in-memory fix cannot work: the
    flag has to ride the suspended run, exactly as permission_mode does. A column added without
    a matching write and read is a mechanism that never runs."""
    susp = SUSP.read_text(encoding="utf-8").replace("\r\n", "\n")
    mig = MIG.read_text(encoding="utf-8").replace("\r\n", "\n")
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert "column_name='studio'" in mig and "ADD COLUMN studio BOOLEAN" in mig, (
        "chat_suspended_runs has no studio column, so nothing can be carried"
    )
    assert "studio: bool = False" in susp, "SuspendedRun cannot hold the flag"
    assert susp.count('studio=bool(row["studio"])') == 2, (
        "one of the two loaders drops the flag, so which loader ran decides whether the "
        "override works"
    )
    # 🔴 WAS `"pinned_step_tools, book_id, studio)" in susp` — pinned to the CLOSING PAREN, so it
    # went red the moment a legitimate column was added beside it (chapter_id/project_id, "the
    # OTHER TWO context ids", 2026-08-24). The intent is "the INSERT writes the flag", not "studio
    # is the last column forever". Check the column list and the VALUES binding instead, which is
    # what actually fails if the flag is dropped.
    _insert = susp[susp.index("INSERT INTO chat_suspended_runs"):]
    _cols = _insert[: _insert.index("VALUES")]
    assert "book_id, studio" in _cols, "the INSERT column list never names the flag"
    assert "bool(studio)" in susp, "the INSERT never binds the flag"
    # 🔴 ANCHOR ON THE SAVE CALL, NOT ON THE EXPRESSION. The first draft of this guard grepped
    # the whole file for `studio=bool((context_ids or {}).get("studio")),` — which is ALSO how
    # both `_inject_context_ids` call sites pass it. Deleting the one at the suspend left two
    # matches and the guard stayed GREEN on the injected defect. An anchor that matches three
    # places is not an anchor.
    at = body.index("await save_suspended_run(")
    save_call = body[at: body.index("\n            )", at)]
    assert 'studio=bool((context_ids or {}).get("studio"))' in save_call, (
        "the suspend does not record whether it was a studio turn, so every resumed row reads "
        "False and the column changes nothing"
    )
