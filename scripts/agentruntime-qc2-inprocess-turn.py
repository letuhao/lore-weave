"""CP-2 QC2 · ONE IN-PROCESS TURN inside infra-chat-service-1, against the real Postgres.

Run with:  docker exec -i infra-chat-service-1 python - < qc2_inprocess_turn.py

WHAT THIS IS, AND WHAT IT IS NOT.
It runs the DEPLOYED image's own modules, with `agentruntime_arm` patched for THIS process only,
through the real advertise chokepoint and the real terminal-path writer, into the real database.
It is NOT a POST /messages against a real model -- that half stays CANNOT DETERMINE and is said so.

It creates a throwaway session and deletes it afterwards. The dogfood corpus is the baseline every
cross-arm comparison in this run is measured against; synthetic rows left in `chat_messages` would
move that baseline silently, which is the exact failure class CP-0.5 recorded.
"""
import asyncio
import json
import os
import uuid

RESULT = {}


async def main() -> None:
    from app.config import settings
    from app.db.pool import create_pool
    from app.services import instrument, stream_service
    from app.agentruntime import (
        FAILED, UNCLASSIFIABLE, NotObservable, observe_breaker, observe_dispatch,
    )
    from app.agentruntime import serve as ar_serve
    from app.agentruntime import manifest as ar_manifest

    # ── 0 · the arm, for this process only ───────────────────────────────────────────────────
    control_variant = instrument.current_runtime_variant()
    settings.agentruntime_arm = True
    armed_variant = instrument.current_runtime_variant()
    RESULT["0_arm"] = {"control": control_variant, "armed": armed_variant}

    # ── 1 · the REAL advertise chokepoint, with a POPULATED legacy catalogue ─────────────────
    # A populated catalogue is the whole point: an empty one would produce [] on both arms and
    # the measurement would be vacuous.
    catalog = {
        "book_list": {"name": "book_list", "description": "d", "input_schema": {"type": "object"}},
        "read_file": {"name": "read_file", "description": "d", "input_schema": {"type": "object"}},
    }
    armed_payload = stream_service._advertise_discovery_tools(catalog, {"book_list"}, [])
    settings.agentruntime_arm = False
    control_payload = stream_service._advertise_discovery_tools(catalog, {"book_list"}, [])
    settings.agentruntime_arm = True
    RESULT["1_advertise"] = {
        "armed_names": [t.get("name") for t in armed_payload],
        "control_names": [t.get("name") or sorted(t) for t in control_payload],
        "control_n": len(control_payload),
    }

    # ── 2 · item A -- the arm SAYS it has no declarations ────────────────────────────────────
    doc = ar_manifest.load()
    payload, surface = ar_serve.advertise(doc, pass_number=1)
    statement = ar_serve.statement_for(surface)
    RESULT["2_item_A"] = {
        "declarations_in_manifest": len(doc.get("declarations", [])),
        "payload_names": [t.get("name") for t in payload],
        "statement": statement,
        "is_NO_DECLARATIONS": statement == ar_serve.NO_DECLARATIONS,
    }

    # ── 3 · items C/D + 2.5 -- the record is DERIVED FROM THE SAME SURFACE ───────────────────
    record = observe_dispatch([surface], outcome="empty")
    RESULT["3_observation"] = {
        "advertised": [dict(e, names=list(e["names"])) for e in record.advertised],
        "withheld": [dict(w) for w in record.withheld],
        "source": record.source,
        "outcome": record.outcome,
        "error_class": record.error_class,
        "guardrail_fired": record.guardrail.fired,
        "guardrail_acted": record.guardrail.acted,
    }

    # ── 4 · CP-2.6 -- source is structural, and the enum refines only `failed` ───────────────
    six = {}
    six["dispatch_source"] = observe_dispatch([surface], outcome="done").source
    six["breaker_source"] = observe_breaker([surface], outcome="done").source
    six["failed_needs_a_class"] = None
    try:
        observe_breaker([surface], outcome=FAILED)
    except NotObservable as exc:
        six["failed_needs_a_class"] = type(exc).__name__
    six["failed_with_a_class"] = observe_breaker(
        [surface], outcome=FAILED, error_class=UNCLASSIFIABLE).error_class
    six["class_on_a_non_failure"] = None
    try:
        observe_dispatch([surface], outcome="done", error_class=UNCLASSIFIABLE)
    except NotObservable as exc:
        six["class_on_a_non_failure"] = type(exc).__name__
    six["no_source_parameter"] = None
    try:
        observe_dispatch([surface], outcome="done", source="breaker")
    except TypeError as exc:
        six["no_source_parameter"] = str(exc)[:80]
    RESULT["4_cp26"] = six

    # ── 5 · the REAL terminal-path write, into the REAL database ─────────────────────────────
    dsn = os.environ.get("DATABASE_URL") or settings.database_url
    pool = await create_pool(dsn)
    sid, mid, uid = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    try:
        async with pool.acquire() as con:
            await con.execute(
                "INSERT INTO chat_sessions (session_id, owner_user_id, title, model_source, "
                "                           model_ref) VALUES ($1,$2,$3,'local',$4)",
                uuid.UUID(sid), uuid.UUID(uid), "CP-2 QC2 throwaway - deleted below",
                uuid.UUID(uid),
            )
        # 5a - the EMPTY terminal turn. This is the shape an arm with zero declarations
        # produces, and it takes the CP-0.4 orphan-stamp branch. Captured, not asserted away.
        import io, logging as _lg
        buf = io.StringIO()
        h = _lg.StreamHandler(buf)
        _lg.getLogger("app.services.stream_service").addHandler(h)
        empty_mid = str(uuid.uuid4())
        empty_wrote = await stream_service._persist_terminal_assistant(
            pool,
            msg_id=empty_mid, session_id=sid, user_id=uid,
            parent_message_id=None, model_ref=None,
            content="", reasoning="", tool_calls_history=None,
            finish_reason="error", is_error=True, error_detail="CP-2 QC2 empty terminal turn",
            outcome=None,  # the TURN's outcome is derived; C-14's is call-level
            advertised_tools=[dict(e, names=list(e["names"])) for e in record.advertised],
            withheld_tools=None,
            runtime_variant=instrument.current_runtime_variant(),
        )
        _lg.getLogger("app.services.stream_service").removeHandler(h)
        log = buf.getvalue()
        RESULT["5a_empty_terminal_turn"] = {
            "write_returned": empty_wrote,
            "orphan_stamp_failed": "orphan-stamp failed" in log,
            "raised": next((l for l in log.splitlines() if "Error" in l), None),
        }

        # 5b - a terminal turn WITH content, which is the real INSERT path.
        buf2 = io.StringIO()
        h2 = _lg.StreamHandler(buf2)
        _lg.getLogger("app.services.stream_service").addHandler(h2)
        wrote = await stream_service._persist_terminal_assistant(
            pool,
            msg_id=mid, session_id=sid, user_id=uid,
            parent_message_id=None, model_ref=None,
            content="partial reply before the error", reasoning="",
            tool_calls_history=None,
            finish_reason="error", is_error=True, error_detail="CP-2 QC2 in-process turn",
            outcome=None,  # the TURN's outcome is derived; C-14's is call-level
            advertised_tools=[dict(e, names=list(e["names"])) for e in record.advertised],
            withheld_tools=[dict(w) for w in record.withheld] or None,
            runtime_variant=instrument.current_runtime_variant(),
        )
        _lg.getLogger("app.services.stream_service").removeHandler(h2)
        RESULT["5b_log"] = buf2.getvalue()[-1500:]
        async with pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT outcome, advertised_tools, withheld_tools, runtime_variant, "
                "       advertised_tools IS NULL AS advertised_is_null "
                "FROM chat_messages WHERE message_id = $1", uuid.UUID(mid))
        RESULT["5b_the_row"] = {
            "write_returned": wrote,
            "row_found": row is not None,
            "outcome": row and row["outcome"],
            "advertised_tools": row and row["advertised_tools"],
            "call_level_outcome_on_the_observation": record.outcome,
            "advertised_is_null": row and row["advertised_is_null"],
            "withheld_tools": row and row["withheld_tools"],
            "runtime_variant": row and row["runtime_variant"],
        }
    finally:
        async with pool.acquire() as con:
            await con.execute("DELETE FROM chat_sessions WHERE session_id = $1", uuid.UUID(sid))
            left = await con.fetchval(
                "SELECT count(*) FROM chat_messages WHERE message_id = $1", uuid.UUID(mid))
        RESULT["6_cleanup"] = {"rows_left_behind": left, "session_id": sid, "message_id": mid}
        await pool.close()


asyncio.run(main())
print("=== CP-2 QC2 IN-PROCESS TURN ===")
print(json.dumps(RESULT, indent=2, default=str))
