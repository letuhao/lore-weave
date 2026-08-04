"""Run reconcile_crashed_turns from a SECOND process against the live DB while a turn
is in flight. Simulates a second replica / rolling restart. Reports which rows it stamped."""
import asyncio, os, sys, json
import asyncpg
from app.services.instrument import reconcile_crashed_turns

SESS = "019fcc55-683c-7c0f-8450-3b51e2b7c193"
MINUTES = int(sys.argv[1]) if len(sys.argv) > 1 else 5


async def snap(pool, tag):
    rows = await pool.fetch(
        "SELECT sequence_num, role, outcome, finish_reason, "
        " (now()-created_at) AS age FROM chat_messages WHERE session_id=$1 "
        " AND sequence_num>11 ORDER BY sequence_num", SESS)
    print(f"--- {tag} ---")
    for r in rows:
        print(f"  seq={r['sequence_num']} {r['role']:9s} outcome={r['outcome'] or 'NULL':18s} "
              f"fr={r['finish_reason'] or 'NULL':14s} age={r['age']}")
    if not rows:
        print("  (no rows > 11)")


async def main():
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=3)
    await snap(pool, f"BEFORE reconcile(older_than_minutes={MINUTES})")
    res = await reconcile_crashed_turns(pool, older_than_minutes=MINUTES)
    print(f">>> reconciler returned: {json.dumps(res)}")
    await snap(pool, "AFTER")
    await pool.close()

asyncio.run(main())
