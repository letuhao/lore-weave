"""F-48 · the `advertised_tools` / `withheld_tools` merge, against REAL Postgres.

**Why this cannot be a unit test.** The defect is entirely inside a jsonb expression evaluated by
the server: `||` on two arrays, `jsonb_array_elements` with ordinality, `IS DISTINCT FROM` against a
key that may be absent. A mock replays whatever we feed it and proves none of that. The previous
gates for this column were substring assertions over `stream_service.py` — they passed while the
column was storing `[1,2,1,2,1,2,3]`, because a string containing `||` says nothing about what the
array ends up holding. That is the exact NV-1 shape the verification protocol exists to reject.

**What the merge has to do, and why the two requirements fight.** One SQL expression serves two
callers that need opposite things from it:

* a **resume** builds a FRESH recorder for the same `message_id`. It must not erase the earlier
  recorder's passes — a declined confirm card took a row from 2 passes to 1 and destroyed the
  founding-defect artefact. That argues for concatenation.
* a **mid-turn checkpoint** shares the recorder with the terminal write, and both re-send the
  recorder's FULL cumulative list. Concatenating those stores each pass once per write.

Measured here, both ways, in the same run: unconditional concatenation stores **7** entries for a
3-pass turn with 2 checkpoints, numbered `[1,1,2,1,2,3,1]`. The segment-scoped merge stores **4**.

Marked xdist_group("pg") (shared dev DB, serialized). Skips cleanly when the dev DB is unreachable.
It never touches real rows: every statement runs against a `TEMP TABLE chat_messages` inside one
transaction, and the resolution of that name is ASSERTED to be a temp schema before any write.
"""
import json
import os

import asyncpg
import pytest

from app.services import instrument
from app.services.instrument import AdvertisedToolsRecorder

pytestmark = pytest.mark.xdist_group("pg")

DSN = os.environ.get("CHAT_DB_DSN", "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_chat")

# The shipped merge, taken from the module rather than retyped. If the two upsert sites and this
# test could drift apart, the test would certify a string nothing executes — which is how the
# class-4 predicate and the expired-suspend sweep came to contradict each other (F-45).
_MERGE_ADV = instrument.segment_merge_sql("advertised_tools")
_MERGE_WITH = instrument.segment_merge_sql("withheld_tools")

_UPSERT = f"""
INSERT INTO chat_messages (message_id, advertised_tools, withheld_tools)
VALUES ($1, $2::jsonb, $3::jsonb)
ON CONFLICT (message_id) DO UPDATE SET
  {_MERGE_ADV},
  {_MERGE_WITH}
"""

_OLD_UPSERT = """
INSERT INTO chat_messages (message_id, advertised_tools, withheld_tools)
VALUES ($1, $2::jsonb, $3::jsonb)
ON CONFLICT (message_id) DO UPDATE SET
  advertised_tools = CASE
    WHEN EXCLUDED.advertised_tools IS NULL THEN chat_messages.advertised_tools
    WHEN chat_messages.advertised_tools IS NULL THEN EXCLUDED.advertised_tools
    ELSE chat_messages.advertised_tools || EXCLUDED.advertised_tools END,
  withheld_tools = CASE
    WHEN EXCLUDED.withheld_tools IS NULL THEN chat_messages.withheld_tools
    WHEN chat_messages.withheld_tools IS NULL THEN EXCLUDED.withheld_tools
    ELSE chat_messages.withheld_tools || EXCLUDED.withheld_tools END
"""


@pytest.fixture
async def conn():
    """One connection, one transaction, a TEMP `chat_messages` that shadows the real table.

    The rollback is belt-and-braces on top of `ON COMMIT DROP`: nothing here may reach a real row.
    """
    try:
        c = await asyncpg.connect(DSN)
    except Exception:
        pytest.skip("dev postgres unreachable")
    tx = c.transaction()
    await tx.start()
    try:
        await c.execute(
            "CREATE TEMP TABLE chat_messages ("
            "  message_id text PRIMARY KEY,"
            "  advertised_tools jsonb,"
            "  withheld_tools jsonb"
            ") ON COMMIT DROP"
        )
        # 🔴 The one thing that would make this test dangerous instead of useful: if the TEMP table
        # were NOT created, every statement below would hit the real `chat_messages`. Assert the
        # name resolves into a temp schema before anything writes.
        ns = await c.fetchval(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.oid = 'chat_messages'::regclass"
        )
        assert ns.startswith("pg_temp"), (
            f"refusing to run: 'chat_messages' resolves to {ns!r}, not a temp schema"
        )
        yield c
    finally:
        await tx.rollback()
        await c.close()


def _turn(segment: str, passes: int) -> str:
    """The recorder's cumulative list after `passes` passes — what every write site sends."""
    return json.dumps([
        {"segment": segment, "pass": i + 1, "names": ["a", "b", "c"][: 3 - i] or ["a"]}
        for i in range(passes)
    ])


def _withheld(segment: str, n: int) -> str:
    return json.dumps([
        {"segment": segment, "tool": f"t{i}", "stage": "token_budget", "reason": "r", "pass": i + 1}
        for i in range(n)
    ])


async def _write(conn, sql: str, segment: str, passes: int) -> None:
    await conn.execute(sql, "m1", _turn(segment, passes), _withheld(segment, passes))


async def _entries(conn, col: str = "advertised_tools") -> list[dict]:
    raw = await conn.fetchval(f"SELECT {col} FROM chat_messages WHERE message_id = 'm1'")
    return json.loads(raw)


class TestTheCheckpointDoesNotMultiplyTheRecord:
    """F-48 — the half unconditional concatenation got wrong."""

    async def test_three_writes_from_one_recorder_store_each_pass_once(self, conn):
        """REJECTS the shipped behaviour. A 3-pass turn with 2 checkpoints, exactly as the code
        writes it: checkpoint(1 pass), checkpoint(2 passes), terminal(3 passes)."""
        for n in (1, 2, 3):
            await _write(conn, _UPSERT, "segA", n)
        entries = await _entries(conn)
        assert [e["pass"] for e in entries] == [1, 2, 3], (
            f"expected one entry per pass, got {[e['pass'] for e in entries]}"
        )

    async def test_the_old_merge_really_did_store_seven(self, conn):
        """The control. Without this the test above proves only that the NEW code is
        self-consistent — it would pass just as happily if the defect had never existed, which is
        the shape of gate that let eight frames of P1 through."""
        for n in (1, 2, 3):
            await _write(conn, _OLD_UPSERT, "segA", n)
        entries = await _entries(conn)
        assert [e["pass"] for e in entries] == [1, 1, 2, 1, 2, 3], (
            "the defect this test exists for did not reproduce; the control is not controlling"
        )

    async def test_withheld_is_multiplied_the_same_way_and_is_fixed_the_same_way(self, conn):
        """`withheld_tools` rides the same merge. In production this multiplied ~215
        `domain_not_selected` entries per extra copy, which reads as a narrowing that happened
        several times rather than one recorded several times."""
        for n in (1, 2, 3):
            await _write(conn, _UPSERT, "segA", n)
        entries = await _entries(conn, "withheld_tools")
        assert [(e["tool"], e["pass"]) for e in entries] == [("t0", 1), ("t1", 2), ("t2", 3)]

    async def test_rewriting_the_same_state_is_idempotent(self, conn):
        """A turn that happens to checkpoint more often must not produce a longer record. The
        number of checkpoints is an implementation detail of the loop; it is not a fact about the
        surface the model saw."""
        await _write(conn, _UPSERT, "segA", 3)
        first = await _entries(conn)
        for _ in range(4):
            await _write(conn, _UPSERT, "segA", 3)
        assert await _entries(conn) == first


class TestAWriteNeverShrinksItsOwnSegment:
    """D-THE-PERSISTED-PER-PASS-RECORDER-DROPS-A-PASS-ON-THE-SECOND-TURN.

        THE INVARIANT. An entry recorded at (segment, pass) is never REMOVED by a later write
        for the same segment. A write may add passes; it may never take one away.

    🔴 THIS FILE HAD THIRTEEN CASES AND WAS EMPTY OF THIS ONE. It asserted that a rewrite of the
    SAME state is idempotent (above) and that a DIFFERENT segment appends beside — but never that
    a SHORTER write for the SAME segment leaves the longer record intact. The merge is a
    segment-scoped WHOLESALE REPLACE: it drops every stored entry of the incoming segment and
    appends the incoming array. So a shorter write silently truncates, and nothing said so.

    THE SHAPE IS THE ROW'S FOUNDING INSTANCE, not an invented one. Session
    01a03f44-1507-76d3-9012-7853c2befd40, still in the live store today:

        seq 2  assistant  completed  9 entries  seg=fdf2bb6bec25  p=1..9
        seq 3  user       abandoned_by_user
        seq 5  assistant  completed  4 entries  seg=a1b98ae38254  p=1..4   <- the wire log said 5

    Measured against real Postgres BEFORE the fix: writing p1..p5 then p1..p4 for one segment left
    the column holding **four** entries, p1..p4 — the stored row, reproduced exactly.

    🔴 WHAT THIS DOES NOT ESTABLISH, and the row says so too: that the live instance was CAUSED
    this way. The container log that would decide has a 30-minute window and is long gone, so
    "a shorter write landed after a longer one" and "the terminal write never carried the fifth"
    remain indistinguishable for THAT session. What is settled is that the merge CAN destroy a
    recorded pass, which is half the search space the row had left, and that it no longer does.
    """

    async def test_a_shorter_write_does_not_truncate_the_segment(self, conn):
        """The founding instance's exact numbers: 5 recorded, then a 4-pass write."""
        await _write(conn, _UPSERT, "a1b98ae38254", 5)
        assert [e["pass"] for e in await _entries(conn)] == [1, 2, 3, 4, 5]
        await _write(conn, _UPSERT, "a1b98ae38254", 4)
        assert [e["pass"] for e in await _entries(conn)] == [1, 2, 3, 4, 5], (
            "a 4-pass write erased pass 5 — the merge is replacing its segment wholesale again")

    async def test_it_holds_for_withheld_too(self, conn):
        """Both columns share one expression; a fix to one that missed the other would be the
        pair-fixed-at-one-end failure this file already records elsewhere."""
        await _write(conn, _UPSERT, "segW", 4)
        await _write(conn, _UPSERT, "segW", 2)
        assert len(await _entries(conn, "withheld_tools")) == 4

    async def test_the_LATER_write_still_WINS_on_a_pass_it_carries(self, conn):
        """Not-shrinking must not become not-updating. The incoming version of a pass replaces the
        stored one — otherwise a corrected pass could never be corrected."""
        await conn.execute(
            _UPSERT, "m1",
            json.dumps([{"segment": "segU", "pass": 1, "names": ["old"]}]),
            json.dumps([]),
        )
        await conn.execute(
            _UPSERT, "m1",
            json.dumps([{"segment": "segU", "pass": 1, "names": ["new"]}]),
            json.dumps([]),
        )
        got = await _entries(conn)
        assert len(got) == 1 and got[0]["names"] == ["new"], got

    async def test_the_surviving_pass_keeps_the_segment_in_pass_ORDER(self, conn):
        """A pass rescued from truncation must land in its place, not at the end. `pass` is
        asserted monotone within a segment elsewhere in this file, and a naive union would append
        the survivor after the incoming array and break it."""
        await _write(conn, _UPSERT, "segO", 5)
        await _write(conn, _UPSERT, "segO", 2)
        passes = [e["pass"] for e in await _entries(conn) if e["segment"] == "segO"]
        assert passes == sorted(passes), passes

    async def test_a_shorter_write_STILL_cannot_reach_another_segment(self, conn):
        """ANTI-OVERREACH. The repair must not turn the segment-scoped merge back into a global
        append — the erasure it replaced, and the duplication before that, are both one careless
        edit away."""
        await _write(conn, _UPSERT, "segX", 3)
        await _write(conn, _UPSERT, "segY", 3)
        await _write(conn, _UPSERT, "segY", 1)
        got = await _entries(conn)
        assert [e["pass"] for e in got if e["segment"] == "segX"] == [1, 2, 3]
        assert [e["pass"] for e in got if e["segment"] == "segY"] == [1, 2, 3]


class TestTheResumeStillCannotEraseTheTurnItResumes:
    """The half the concatenation got RIGHT, and which the fix must not give back.

    This is the regression that matters most: the previous fix for the erasure introduced F-48, so
    the obvious repair — go back to replacing — would reinstate the worse defect. Both directions
    are asserted here so neither can be traded for the other silently.
    """

    async def test_a_fresh_recorder_appends_beside_the_earlier_segment(self, conn):
        await _write(conn, _UPSERT, "segA", 3)
        await _write(conn, _UPSERT, "segB", 1)          # the resume
        entries = await _entries(conn)
        assert [(e["segment"], e["pass"]) for e in entries] == [
            ("segA", 1), ("segA", 2), ("segA", 3), ("segB", 1),
        ], "the resume erased the turn it resumed — the founding-defect artefact is gone again"

    async def test_pass_numbers_collide_across_segments_and_that_is_why_segment_exists(self, conn):
        """Both segments have a `pass 1` and they are DIFFERENT sets. Before the segment stamp the
        stored array said `1` twice with no way to tell which recorder issued which — so
        "what disappeared between pass 1 and pass 2" had two contradictory answers."""
        await _write(conn, _UPSERT, "segA", 2)
        await _write(conn, _UPSERT, "segB", 2)
        entries = await _entries(conn)
        ones = [e for e in entries if e["pass"] == 1]
        assert len(ones) == 2 and {e["segment"] for e in ones} == {"segA", "segB"}

    async def test_segment_and_pass_together_are_unique(self, conn):
        """The invariant round 11 found nothing asserting. Stated over the STORED value, not over
        the recorder's in-memory list — the recorder was never the thing that was wrong."""
        for n in (1, 2, 3):
            await _write(conn, _UPSERT, "segA", n)
        await _write(conn, _UPSERT, "segB", 1)
        await _write(conn, _UPSERT, "segA", 3)          # a late re-write of the first segment
        dupes = await conn.fetch(
            "SELECT e->>'segment' AS seg, e->>'pass' AS p, count(*) AS n "
            "FROM chat_messages, jsonb_array_elements(advertised_tools) AS e "
            "WHERE message_id = 'm1' GROUP BY 1, 2 HAVING count(*) > 1"
        )
        assert not dupes, f"duplicate (segment, pass): {[dict(r) for r in dupes]}"

    async def test_pass_is_monotone_within_each_segment(self, conn):
        """Monotonicity is what makes the column a delta encoding rather than a bag. Without it
        `advertised_tools` cannot answer the one question it was added for."""
        for n in (1, 2, 3):
            await _write(conn, _UPSERT, "segA", n)
        await _write(conn, _UPSERT, "segB", 2)
        bad = await conn.fetch(
            "SELECT * FROM ("
            "  SELECT e->>'segment' AS seg, (e->>'pass')::int AS p,"
            "         lag((e->>'pass')::int) OVER (PARTITION BY e->>'segment' ORDER BY ord) AS prev"
            "  FROM chat_messages, jsonb_array_elements(advertised_tools) WITH ORDINALITY AS t(e, ord)"
            "  WHERE message_id = 'm1') s "
            "WHERE prev IS NOT NULL AND p <= prev"
        )
        assert not bad, f"non-monotone pass sequence: {[dict(r) for r in bad]}"


class TestTheMergeNeverDestroysWhatItDoesNotUnderstand:
    """Every row written before the segment stamp existed has no `segment` key."""

    async def test_a_historical_unstamped_entry_survives_a_stamped_write(self, conn):
        await conn.execute(
            "INSERT INTO chat_messages (message_id, advertised_tools) "
            "VALUES ('m1', '[{\"pass\":1,\"names\":[\"legacy\"]}]'::jsonb)"
        )
        await _write(conn, _UPSERT, "segC", 1)
        entries = await _entries(conn)
        assert entries[0].get("names") == ["legacy"], (
            "a pre-segment row was deleted by a writer that could not have produced it"
        )
        assert len(entries) == 2

    async def test_an_unstamped_writer_still_appends(self, conn):
        """If some path is ever added that does not stamp, it keeps the old append-only behaviour
        rather than silently replacing. Fail toward KEEPING the record."""
        await _write(conn, _UPSERT, "segA", 2)
        await conn.execute(
            _UPSERT, "m1", json.dumps([{"pass": 1, "names": ["unstamped"]}]), None,
        )
        entries = await _entries(conn)
        assert len(entries) == 3 and entries[-1]["names"] == ["unstamped"]

    async def test_a_null_payload_preserves_what_is_stored(self, conn):
        """A checkpoint that carries no recorder must not blank the column. This is the property
        the original COALESCE got right, and it has to survive both later rewrites."""
        await _write(conn, _UPSERT, "segA", 2)
        before = await _entries(conn)
        await conn.execute(_UPSERT, "m1", None, None)
        assert await _entries(conn) == before


class TestTheRecorderStampsEveryEntryItProduces:
    """The merge is only sound if the payload actually carries `segment`. A single unstamped write
    site would fall to the append-only branch and re-introduce the duplication for that path."""

    async def test_a_real_recorder_stamps_advertised_and_withheld_alike(self, conn):
        rec = AdvertisedToolsRecorder()
        rec.record_pass(["book_list"])
        rec.record_withheld("glossary_search", stage="token_budget", reason="over budget")
        rec.record_pass(["book_list", "book_get"])
        adv, wit = rec.advertised_json(), rec.withheld_json()
        assert {e["segment"] for e in adv} == {rec.segment}
        assert {e["segment"] for e in wit} == {rec.segment}

    async def test_two_recorders_never_share_a_segment(self, conn):
        """If they collided, a resume would replace the turn it resumed — the original defect, via
        the new mechanism."""
        segs = {AdvertisedToolsRecorder().segment for _ in range(200)}
        assert len(segs) == 200


# ── F-50 · the ORPHAN UPDATE form, executed ───────────────────────────────────────────────────

#: The parameterised form, taken from the module for the same reason `_MERGE_WITH` is: a retyped
#: copy would certify a string nothing executes.
_MERGE_WITH_BOUND = instrument.segment_merge_sql("withheld_tools", incoming="$3::jsonb")

#: The CP-0.4 orphan stamp, in the shape `_persist_terminal_assistant` issues it. A plain UPDATE --
#: no `ON CONFLICT`, therefore **no `EXCLUDED` relation**, which is precisely what the shipped
#: statement assumed for two days.
_ORPHAN_UPDATE = f"""
UPDATE chat_messages SET outcome = $2,
  {_MERGE_WITH_BOUND}
WHERE message_id = $1
RETURNING message_id
"""


class TestTheOrphanStampExecutesAgainstRealPostgres:
    """REJECTS: F-50's second layer — a merge expression that only a server can refuse.

    **This is the guard that had to exist and did not.** The first layer (`UnboundLocalError`) meant
    the statement never reached Postgres, so the second layer (`EXCLUDED` in a plain UPDATE) could
    not be observed even in production. Fixing the first exposed the second immediately, in a live
    run, with `UndefinedTableError: missing FROM-clause entry for table "excluded"`.

    No static check and no mock can hold this property. A fake connection accepts any string; an AST
    gate proves the statement is *written*. Only a server decides whether SQL is executable.
    """

    async def test_THE_ORPHAN_UPDATE_IS_ACCEPTED_BY_THE_SERVER(self, conn):
        await conn.execute("ALTER TABLE chat_messages ADD COLUMN outcome text")
        await conn.execute(
            "INSERT INTO chat_messages (message_id, withheld_tools) VALUES ('m1', $1::jsonb)",
            _withheld("seg-a", 2))
        got = await conn.fetchval(_ORPHAN_UPDATE, "m1", "failed", _withheld("seg-b", 1))
        assert got == "m1", "the orphan UPDATE matched no row"
        row = await conn.fetchrow(
            "SELECT outcome, withheld_tools FROM chat_messages WHERE message_id = 'm1'")
        assert row["outcome"] == "failed"
        merged = json.loads(row["withheld_tools"])
        assert [w["segment"] for w in merged] == ["seg-a", "seg-a", "seg-b"], (
            f"the stamp did not merge segment-scoped: {merged}. F-48's properties must hold in the "
            f"UPDATE shape exactly as they do in the upsert -- one expression, two statements."
        )

    async def test_THE_DEFAULT_FORM_IS_REJECTED_IN_A_PLAIN_UPDATE(self, conn):
        """The control, and it is the whole finding: prove the server refuses what shipped.

        Without this the fix above is a claim. With it, the defect is reproduced on the same
        connection that accepts the repair, so 'EXCLUDED does not exist here' is a measurement.
        """
        await conn.execute("ALTER TABLE chat_messages ADD COLUMN outcome text")
        await conn.execute("INSERT INTO chat_messages (message_id) VALUES ('m1')")
        shipped = f"UPDATE chat_messages SET outcome = $2, {_MERGE_WITH} WHERE message_id = $1"
        with pytest.raises(asyncpg.exceptions.UndefinedTableError, match="excluded"):
            await conn.execute(shipped, "m1", "failed")
