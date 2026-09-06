"""SHIP audit for translation_job_control — a tool that has NEVER completed a call.

Its ledger note prescribes exactly this: "SHIP cases remain unexercised ... exercisable by direct
probe now that it is federated, and that is the next step for it rather than another consumer
run."

THE JOB MUST BE ON A BOOK THAT STILL EXISTS. A first version of this probe used ids read from
translation_jobs by status and every call came back "not found or not accessible" — the tool's
auth is BOOK-scoped and every one of the 60 translation jobs visible to this account is an
ORPHAN whose book was torn down by an earlier run. An id in a table is not an id the caller can
address. So this seeds its own job the way the scenarios do: throwaway book, throwaway chapter,
one INSERT, all removed after.

ORDERING IS LOAD-BEARING: every REFUSAL runs first against untouched state, the real cancel LAST.
Cycle 16 paid for that lesson when a control action taken first changed what a later call did.
"""
import json, subprocess, sys, uuid
sys.path.insert(0, ".")
from scripts.eval.tool_liveness.mcp_direct import MCPDirect, MCPToolError
from scripts.toolloop.provision import Throwaway

m = MCPDirect()


def sql(q, db="loreweave_translation"):
    r = subprocess.run(["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
                        "-d", db, "-tAF|", "-c", q], capture_output=True, text=True)
    return (r.stdout or "").strip(), (r.stderr or "").strip()


def seed_job(fx, status="pending"):
    sql(f"""INSERT INTO translation_jobs (book_id, owner_user_id, status, target_language,
            model_source, model_ref, system_prompt, user_prompt_tpl, chapter_ids, total_chapters)
            VALUES ('{fx.book_id}', '019d5e3c-7cc5-7e6a-8b27-1344e148bf7c', '{status}', 'vi',
            'user_model', '019ebb72-27a2-72f3-a42d-d2d0e0ded179', 'sys', 'tpl',
            ARRAY['{fx.chapter_id}']::uuid[], 1)""")
    got, _ = sql(f"select job_id::text from translation_jobs where book_id='{fx.book_id}' "
                 f"and status='{status}' order by created_at desc limit 1")
    return got.strip() or None


def call(**args):
    try:
        return {"verdict": "SUCCEEDED",
                "detail": json.dumps(m.call("translation_job_control", args), ensure_ascii=False)[:220]}
    except MCPToolError as e:
        return {"verdict": "refused", "detail": str(e)[:250]}


def db_status(job_id):
    got, _ = sql(f"select status from translation_jobs where job_id='{job_id}'")
    return got.strip() or "(gone)"


a = b = None
out = {}
try:
    a = Throwaway("jc-ship-a", mcp=m).build()
    b = Throwaway("jc-ship-b", mcp=m).build()
    live = seed_job(a)
    done = seed_job(a, status="completed")
    foreign = seed_job(b)
    out["_fixture"] = {"book_a": a.book_id, "pending_job": live, "completed_job": done,
                       "book_b": b.book_id, "job_on_book_b": foreign}

    out["absent"] = call(job_id=str(uuid.uuid4()), action="cancel")
    out["absent"]["asked"] = "a job_id that does not exist"

    out["malformed"] = call(job_id="the-last-one", action="cancel")
    out["malformed"]["asked"] = "a job NAME where a UUID is required"

    out["bad_action"] = call(job_id=live, action="obliterate")
    out["bad_action"]["asked"] = "an action outside the enum — refused, not defaulted"

    out["terminal_state"] = call(job_id=done, action="cancel")
    out["terminal_state"]["asked"] = "cancel a COMPLETED job — terminal jobs are not cancellable"

    out["gate_resume_respends"] = call(job_id=done, action="resume")
    out["gate_resume_respends"]["asked"] = (
        "resume RE-SPENDS money, so it must card or refuse — never silently re-run")

    # the single real state change, last
    out["_status_before"] = db_status(live)
    first = call(job_id=live, action="cancel")
    first["asked"] = "cancel a genuinely pending job — the first call this tool has ever completed"
    out["gate_cancel_immediate"] = first
    out["_status_after_first"] = db_status(live)

    second = call(job_id=live, action="cancel")
    second["asked"] = "cancel the SAME job again"
    out["idempotency"] = second
    out["_status_after_second"] = db_status(live)

    out["tenancy_job_on_another_book"] = {"note": "book B is a DIFFERENT book of the same account; "
                                                  "its job must not be controllable via book A's scope"}
    out["tenancy_job_on_another_book"].update(call(job_id=foreign, action="cancel"))
finally:
    for fx in (a, b):
        if fx:
            sql(f"delete from translation_jobs where book_id='{fx.book_id}'")
            try:
                fx.teardown()
            except Exception as e:  # noqa: BLE001
                out.setdefault("_teardown_errors", []).append(str(e)[:120])
print(json.dumps(out, indent=2, ensure_ascii=False))
