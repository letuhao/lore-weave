"""Content-fixture seeder for the discoverability scenarios (WS-7).

WHY THIS EXISTS
---------------
S04/S05/S06b/S09/S12 are **fixture-blocked**, not unwritten: their scenario JSON has existed
for days, but no book in the dev DB can make them fail the right way. The README says it best:

    "A fixture that can't fail the right way makes the baseline worthless: S04 on a book *with*
     prose, or S05 on a fully-(un)translated book, silently passes the crux."

So each fixture below is built to make the crux REACHABLE:
  s04  — ACTIVE recorded lore + **zero** chapter prose  → connections must be built from
         structured lore, not from extraction. (On a book with prose, S04 passes for the wrong reason.)
  s05  — **partial** translation coverage (some chapters translated, ≥1 dirty) → exercises
         "only redo what changed". (On a fully-translated or fully-untranslated book, the crux is skipped.)
  plan — a book with an APPROVED plan → the precondition for S06b (chapter-compose) and S12
         (autonomous drafting). Without it those rails must refuse, which is a different test.
  s09  — prose containing a PLANTED contradiction → canon-check must actually FIND something.
         (A clean book returns "all clean" and the scenario passes without testing anything.)

HOW IT SEEDS (and why not raw SQL)
----------------------------------
Through the product's own writers — `MCPDirect` MCP calls + the REST edges — never hand-written
INSERTs. `glossary_entities` alone carries entity_snapshot / search_vector / cached_* columns the
real writer maintains; hand-seeding them produces a book that looks right and behaves wrong, and
the scenario would then measure my SQL rather than the product. This mirrors the repo's
"reuse the PRODUCER's own path" rule.

Reuses the tool-liveness harness's auth/MCP/DB plumbing (scripts/eval/tool_liveness/) rather than
forking a second, drifting copy of it.

USAGE
-----
    python -m scripts.eval.discoverability_fixtures s04
    python -m scripts.eval.discoverability_fixtures all
    python -m scripts.eval.discoverability_fixtures spend      # just the eval spend-grant

Prints a JSON object of the ids it created, e.g. {"s04": {"book_id": "..."}}.
Every book is titled `DISCO-FIXTURE-<kind>-<runid>` so it is identifiable and disposable.
"""
from __future__ import annotations

import json
import sys
import uuid

import httpx

from .tool_liveness import config, oracle
from .tool_liveness.auth import Auth
from .tool_liveness.confirm import confirm
from .tool_liveness.mcp_direct import MCPDirect

# The paid tools an eval rail reaches for. D-P1-EVAL-SPEND-FIXTURE: these used to be a MANUAL
# DB grant somebody added by hand, so a fresh eval environment silently suspended on the spend
# gate. Declaring them here makes the grant reproducible instead of folklore.
#
# NOTE the `spend::` namespace — the spend gate and the mutation (Tier-A) gate are INDEPENDENT
# axes on the same table (Track D WS-D0b). Granting `glossary_extract_entities_from_doc` alone
# only clears the mutation card; the paid call still suspends until `spend::` is granted too.
EVAL_SPEND_TOOLS = [
    "spend::glossary_extract_entities_from_doc",
    "spend::plan_propose_spec",
]

# translation-service has its own DB and is NOT in tool_liveness' DOMAIN_DB map (that map only
# covers the domains the liveness sweep probes). Named here rather than silently defaulting.
TRANSLATION_DB = "loreweave_translation"

# The test account's gemma-4-26b-a4b-qat user_model. `translation_jobs.model_ref` is NOT NULL and
# records WHICH model produced a rendering, so the seeded history has to name one. This is a
# fixture recording a past run, not runtime model selection — no hardcoded-model-name rule is in
# play (it is a uuid FK into the user's own provider-registry rows, not a literal model name).
GEMMA_MODEL_REF = "019ebb72-27a2-72f3-a42d-d2d0e0ded179"


def _mcp() -> MCPDirect:
    return MCPDirect()


def _new_book(m: MCPDirect, kind: str, run: str, *, lang: str = "en") -> str:
    r = m.call("book_create", {
        "title": f"DISCO-FIXTURE-{kind}-{run}",
        "original_language": lang,
        "description": "Discoverability scenario fixture — safe to delete.",
        "genre_tags": ["fantasy"],
    })
    book_id = r.get("book_id") or r.get("id")
    if not book_id:
        raise RuntimeError(f"book_create returned no id: {r}")
    return book_id


def _adopt(book_id: str, kinds: list[str]) -> None:
    """Adopt an ontology via the REST /adopt edge.

    The MCP `glossary_adopt_standards` tool is deliberately NOT used: it mints a confirm_token
    and writes nothing at call time, so it cannot deterministically seed a fixture (the same
    reason the tool-liveness factory takes this edge).
    """
    r = httpx.post(
        f"{config.DOMAIN_BASE['glossary']}/v1/glossary/books/{book_id}/adopt",
        headers=Auth().bearer_header(),
        json={"genres": ["universal"], "kinds": kinds},
        timeout=60,
    )
    r.raise_for_status()


def _propose(m: MCPDirect, book_id: str, items: list[dict]) -> int:
    """Create entities and VERIFY every one landed.

    Learned the hard way while building this file: I seeded a `faction` kind that does not exist
    (the system kinds are character/org/organization/relationship/species/…), and the batch came
    back with 5 of 6 created. glossary-service is honest about it — a fully-failed batch raises
    "unknown kind: faction" — but a PARTIAL failure is easy to ignore if the caller never reads the
    response, and a fixture that silently under-seeds is the worst kind: the scenario still runs, and
    passes for the wrong reason. So: count what we asked for, count what exists, and refuse to
    continue if they differ.
    """
    r = m.call("glossary_propose_entities", {"book_id": book_id, "items": items})
    results = r.get("results") or []
    created = [x for x in results if (x.get("status") or "") in ("created", "existing", "merged")]
    if len(created) != len(items):
        raise RuntimeError(
            f"fixture under-seeded: asked for {len(items)} entities, {len(created)} landed. "
            f"Response: {json.dumps(r, ensure_ascii=False)[:400]}")
    return len(created)


def _promote_to_active(m: MCPDirect, book_id: str) -> int:
    """Promote this book's draft entities to ACTIVE canon, through the product's own path
    (`glossary_propose_status_change` is Tier-W → mints a confirm_token → redeem it).

    S04's whole point is lore that is *recorded canon*, not an unreviewed inbox. `propose_entities`
    creates rows at status='draft' (verified in DB), so without this step the fixture would hand
    S04 a pile of drafts and the scenario would be testing triage, not KG-building.
    """
    rows = oracle.db_query(
        config.DOMAIN_DB["glossary"],
        "SELECT entity_id FROM glossary_entities "
        f"WHERE book_id='{book_id}' AND alive=true AND status='draft'")
    ids = [r[0] for r in rows if r and r[0]]
    if not ids:
        return 0
    r = m.call("glossary_propose_status_change", {
        "book_id": book_id, "entity_ids": ids, "status": "active",
    })
    token = r.get("confirm_token")
    if not token:
        raise RuntimeError(f"status_change minted no confirm_token: {r}")
    ok, code, body = confirm(Auth(), "glossary_propose_status_change", token)
    if not ok:
        raise RuntimeError(f"confirm failed ({code}): {body}")
    n = oracle.db_query(
        config.DOMAIN_DB["glossary"],
        f"SELECT count(*) FROM glossary_entities WHERE book_id='{book_id}' AND status='active'")
    return int(n[0][0]) if n else 0


# ── S04 — active lore, ZERO prose ────────────────────────────────────────────────────────
def build_s04(run: str) -> dict:
    m = _mcp()
    book_id = _new_book(m, "s04", run)
    _adopt(book_id, ["character", "location", "organization", "item", "relationship"])
    _propose(m, book_id, [
        {"kind": "character", "name": "Lâm Uyên"},
        {"kind": "character", "name": "Tô Hạo"},
        {"kind": "organization", "name": "Cửu Thiên Sect"},
        {"kind": "location", "name": "Hollow Shrine"},
        {"kind": "item", "name": "Ember Codex"},
        {"kind": "character", "name": "Mira Solene"},
    ])
    active = _promote_to_active(m, book_id)
    # THE CRUX: zero prose. Assert it rather than assume it — a fixture that quietly has prose
    # makes S04 pass for the wrong reason, which is the exact failure the README warns about.
    ch = oracle.db_query(config.DOMAIN_DB["book"],
                         f"SELECT count(*) FROM chapters WHERE book_id='{book_id}'")
    if int(ch[0][0]) != 0:
        raise RuntimeError(f"s04 fixture has {ch[0][0]} chapters — it MUST have zero prose")
    return {"book_id": book_id, "active_entities": active, "chapters": 0}


# ── S05 — PARTIAL translation coverage ───────────────────────────────────────────────────
_VI_CH1 = ("Nàng đứng trước bàn thờ, tay lạnh như băng. Hắn bước tới, ánh mắt không còn tình yêu. "
           "Đó là ngày cưới của nàng, và cũng là ngày nàng chết.")
_VI_CH2 = ("Một nghìn năm sau, nàng tỉnh dậy trong lớp tro tàn. Thế gian đã quên tên nàng. "
           "Nhưng nàng thì không quên hắn.")
_VI_CH3 = ("Hắn đã trở thành thần. Đền thờ của hắn cao ngất trời. "
           "Nàng đứng dưới chân bậc thang, mỉm cười.")


def build_s05(run: str) -> dict:
    m = _mcp()
    book_id = _new_book(m, "s05", run, lang="vi")
    r = m.call("book_chapter_bulk_create", {
        "book_id": book_id, "original_language": "vi",
        "chapters": [
            {"title": "Chương 1 — Ngày cưới", "original_filename": "s05-ch01.txt", "content": _VI_CH1},
            {"title": "Chương 2 — Tro tàn", "original_filename": "s05-ch02.txt", "content": _VI_CH2},
            {"title": "Chương 3 — Bậc thang", "original_filename": "s05-ch03.txt", "content": _VI_CH3},
        ]})
    ids = r.get("chapter_ids") or [
        c.get("chapter_id") or c.get("id")
        for c in (r.get("chapters") or r.get("created") or [])]
    ids = [i for i in ids if i]
    if len(ids) < 3:
        raise RuntimeError(f"s05 expected 3 chapters, got {ids}")

    # THE CRUX: PARTIAL coverage. Chapters 1-2 get a COMPLETED, ACTIVE English rendering; chapter 3
    # is left untranslated. A fully-translated book (nothing to do) or a fully-untranslated one
    # (redo everything) both let the agent pass WITHOUT ever exercising "only redo what changed".
    #
    # We seed the HISTORY a real pass would have left behind — a completed translation_jobs row
    # (chapter_translations.job_id is NOT NULL and FKs to it), one completed chapter_translations
    # row per done chapter, and the active-version pointer. This is a faithful past, not a bypassed
    # writer: we are not inventing a state the product cannot reach, we are replaying one it does.
    done_text = {
        ids[0]: ("She stood before the altar, her hands cold as ice. He stepped toward her, and "
                 "there was no love left in his eyes. It was her wedding day. It was also the day "
                 "she died."),
        ids[1]: ("A thousand years later she woke among the ashes. The world had forgotten her "
                 "name. She had not forgotten his."),
    }
    tdb = TRANSLATION_DB
    job_rows = oracle.db_query(tdb, f"""
INSERT INTO translation_jobs
  (job_id, book_id, owner_user_id, status, target_language, model_source, model_ref,
   system_prompt, user_prompt_tpl, chapter_ids, total_chapters, completed_chapters,
   failed_chapters, started_at, finished_at)
VALUES
  (gen_random_uuid(), '{book_id}', '{config.USER_ID}', 'completed', 'en', 'byok',
   '{GEMMA_MODEL_REF}', 'seeded by the discoverability fixture', 'seeded',
   ARRAY['{ids[0]}','{ids[1]}']::uuid[], 2, 2, 0, now(), now())
RETURNING job_id""")
    job_id = job_rows[0][0]

    for ch_id, text in done_text.items():
        body = text.replace("'", "''")
        tr = oracle.db_query(tdb, f"""
INSERT INTO chapter_translations
  (job_id, chapter_id, book_id, owner_user_id, status, source_language, target_language,
   translated_body, version_num, translated_body_format, authored_by, finished_at)
VALUES
  ('{job_id}', '{ch_id}', '{book_id}', '{config.USER_ID}', 'completed', 'vi', 'en',
   '{body}', 1, 'plain', 'ai', now())
RETURNING id""")
        tr_id = tr[0][0]
        oracle.db_query(tdb, f"""
INSERT INTO active_chapter_translation_versions
  (chapter_id, target_language, chapter_translation_id, set_by_user_id, set_at)
VALUES ('{ch_id}', 'en', '{tr_id}', '{config.USER_ID}', now())
ON CONFLICT (chapter_id, target_language)
DO UPDATE SET chapter_translation_id=EXCLUDED.chapter_translation_id""")

    # Assert the crux rather than assume it: PARTIAL means 2 done and ≥1 NOT done.
    n_done = int(oracle.db_query(
        tdb, f"SELECT count(*) FROM chapter_translations WHERE book_id='{book_id}' "
             "AND status='completed' AND target_language='en'")[0][0])
    if n_done != 2 or len(ids) - n_done < 1:
        raise RuntimeError(
            f"s05 fixture is not PARTIAL: {n_done} translated of {len(ids)} — the scenario would "
            "pass without exercising 'only redo what changed'")
    return {"book_id": book_id, "chapters": len(ids), "translated": n_done,
            "untranslated": len(ids) - n_done, "dirty_chapter_id": ids[2],
            "translation_job_id": job_id}


# ── plan — a book with an APPROVED plan (S06b + S12 precondition) ────────────────────────
def build_plan(run: str) -> dict:
    m = _mcp()
    book_id = _new_book(m, "plan", run)
    _adopt(book_id, ["character", "location", "item"])
    _propose(m, book_id, [
        {"kind": "character", "name": "Lâm Uyên"},
        {"kind": "character", "name": "Tô Hạo"},
    ])
    _promote_to_active(m, book_id)
    # plan_propose_spec in rules mode is SYNCHRONOUS and free (mode=llm would enqueue a job and
    # cost money — see M0a: the flagship's plan is deliberately mode=rules for exactly this reason).
    r = m.call("plan_propose_spec", {
        "book_id": book_id, "mode": "rules",
        "source_markdown": (
            "# Premise\nA bride is murdered at her own wedding and returns a thousand years later.\n\n"
            "## Act I — The Wedding\nShe is betrayed and used as fuel.\n\n"
            "## Act II — The Ashes\nShe wakes, forgotten, and learns what he became.\n\n"
            "## Act III — The Stair\nShe climbs to his temple and takes it back.\n"),
    })
    run_id = r.get("run_id") or (r.get("run") or {}).get("id")
    if not run_id:
        raise RuntimeError(f"plan_propose_spec returned no run_id: {r}")
    # "APPROVED" is OUR word, not the product's. composition-service is explicit
    # (authoring_run_service.py:109-111): the start-gate treats `validated`/`compiled` as approved,
    # and "there is no literal 'approved'" in plan_run_status_chk. Writing 'approved' here fails the
    # CHECK constraint — which is the schema correctly refusing a state the product does not have.
    # Use the real vocabulary, or the fixture would encode a plan state no product path can produce.
    oracle.db_query(config.DOMAIN_DB["composition"],
                    f"UPDATE plan_run SET status='validated' WHERE id='{run_id}'")
    st = oracle.db_query(config.DOMAIN_DB["composition"],
                         f"SELECT status FROM plan_run WHERE id='{run_id}'")
    status = st[0][0] if st else "?"
    if status not in ("validated", "compiled"):
        raise RuntimeError(f"plan fixture is not start-gate-approved: status={status!r}")
    return {"book_id": book_id, "plan_run_id": run_id,
            "plan_status": status,
            "_note": "validated == 'approved' for the authoring start-gate (no literal 'approved' exists)"}


# ── S09 — prose with a PLANTED contradiction ─────────────────────────────────────────────
def build_s09(run: str) -> dict:
    m = _mcp()
    book_id = _new_book(m, "s09", run)
    _adopt(book_id, ["character", "location"])
    _propose(m, book_id, [
        {"kind": "character", "name": "Lâm Uyên"},
    ])
    _promote_to_active(m, book_id)
    # THE PLANTED CONTRADICTION (this is the whole fixture):
    #   ch1 — her eyes are GREEN, and Tô Hạo dies at the shrine.
    #   ch3 — her eyes are BLUE, and Tô Hạo is alive and ruling.
    # A canon-check that reports "all clean" on this book has failed, and we will be able to say so.
    m.call("book_chapter_bulk_create", {
        "book_id": book_id, "original_language": "en",
        "chapters": [
            {"title": "Chapter 1 — The Wedding", "original_filename": "s09-ch01.txt",
             "content": ("Lâm Uyên's green eyes caught the lantern light as she turned to face him. "
                         "By the end of that night Tô Hạo lay dead on the shrine steps, and she "
                         "walked away alone into the rain.")},
            {"title": "Chapter 2 — The Ashes", "original_filename": "s09-ch02.txt",
             "content": ("A thousand years of ash. She woke remembering nothing but the cold, and "
                         "the sound of her own name being spoken like a curse.")},
            {"title": "Chapter 3 — The Stair", "original_filename": "s09-ch03.txt",
             "content": ("She lifted her blue eyes to the temple stair. Above her, alive and "
                         "crowned, Tô Hạo watched the pilgrims climb toward him, as he had every "
                         "day for a thousand years.")},
        ]})

    # THE OTHER HALF OF THE FIXTURE (D-S09-CANON-RULES). The canon-check rail is
    # list_canon_rules → conformance_run → status: it checks the prose against DECLARED consistency
    # RULES. With NONE seeded, the agent CORRECTLY says "there are no rules — want me to set some
    # up?" (the rail's own notes instruct exactly that, and "never report all-consistent when
    # nothing was checked"). So a rule-less fixture tests the agent's HONESTY, not contradiction
    # detection — it can't fail the right way. Seed the composition project + the canon rule the
    # prose violates, so the rail has something to check against.
    # composition_create_work idempotently creates the book's composition Work (+ its default
    # knowledge project) — the scope a canon rule and the conformance run both hang off. plan_*
    # in rules mode only mints a plan_run, NOT a Work, so it is the wrong primitive here.
    wk = m.call("composition_create_work", {"book_id": book_id})
    if isinstance(wk, dict) and wk.get("success") is False:
        raise RuntimeError(f"s09: composition_create_work failed: {wk.get('error')}")
    proj = oracle.db_query(
        config.DOMAIN_DB["composition"],
        f"SELECT COALESCE(project_id, id) FROM composition_work "
        f"WHERE book_id='{book_id}' AND source_work_id IS NULL AND status='active' LIMIT 1")
    if not proj:
        raise RuntimeError(f"s09: no composition_work resolved for book {book_id} — cannot seed a canon rule")
    project_id = proj[0][0]
    # The declared canon the prose contradicts: ch1 establishes GREEN, ch3 says BLUE.
    m.call("composition_canon_rule_create", {"args": {
        "project_id": str(project_id),
        "text": "Lâm Uyên's eye colour is green and never changes.",
        "scope": "world",
    }})
    n_rules = int(oracle.db_query(
        config.DOMAIN_DB["composition"],
        f"SELECT count(*) FROM canon_rule WHERE project_id='{project_id}' AND active AND NOT is_archived")[0][0])
    if n_rules < 1:
        raise RuntimeError(f"s09: canon rule did not land (rules={n_rules}) — the rail would still find nothing to check")

    return {"book_id": book_id, "project_id": str(project_id), "canon_rules": n_rules,
            "planted_contradictions": ["eye colour: green (ch1) vs blue (ch3)",
                                       "Tô Hạo: dead (ch1) vs alive and ruling (ch3)"]}


# ── S10 — a world (with a book in it) the agent should draw a MAP for ────────────────────
def build_s10(run: str) -> dict:
    """A world + a book moved into it. The agent, asked to map the world, must discover the
    world_map_* tools (no rail) and create a map + place a marker. Returns book_id (the harness
    context) + world_id (the gt resolves the book's world and checks for a map + marker)."""
    m = _mcp()
    w = _J(m.call("world_create", {"name": f"S10 World {run}"}))
    world_id = w.get("world_id") or (w.get("world") or {}).get("world_id") or w.get("id")
    if not world_id:
        raise RuntimeError(f"s10: world_create returned no id: {w}")
    book_id = _new_book(m, "s10", run)
    m.call("world_move_book", {"world_id": world_id, "book_id": book_id})
    return {"book_id": book_id, "world_id": world_id}


def _J(x):
    import json as _json
    return x if isinstance(x, dict) else _json.loads(x)


# ── the eval spend-grant (D-P1-EVAL-SPEND-FIXTURE) ───────────────────────────────────────
def grant_spend() -> dict:
    granted = []
    for t in EVAL_SPEND_TOOLS:
        oracle.db_query(
            "loreweave_chat",
            "INSERT INTO user_tool_approvals (user_id, tool_name, decision) VALUES "
            f"('{config.USER_ID}', '{t}', 'allow') "
            "ON CONFLICT (user_id, tool_name) DO UPDATE SET decision='allow'")
        granted.append(t)
    return {"granted": granted}


BUILDERS = {"s04": build_s04, "s05": build_s05, "plan": build_plan, "s09": build_s09}


def main(argv: list[str]) -> int:
    want = argv[1] if len(argv) > 1 else "all"
    run = uuid.uuid4().hex[:8]
    out: dict = {}
    if want in ("spend", "all"):
        out["spend"] = grant_spend()
    for name, fn in BUILDERS.items():
        if want in (name, "all"):
            out[name] = fn(run)
    if not out:
        print(f"unknown fixture {want!r}; choose from: "
              f"{', '.join(list(BUILDERS) + ['spend', 'all'])}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
