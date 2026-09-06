"""Replay decide_absent over the RECORDED corpus: what would the fetch branch have done?

For each (tool, missing_id_param) failure since 2026-08-10 whose supplier is declared in
`argument_emitters`, take a REAL recorded successful result of that supplier and run the
pure decision over it. No provider calls: every input is a payload the platform already
produced and stored.

Reports the three outcomes separately, because they are three different products:
  resolved  — the call would have gone through
  ambiguous — the model is handed the ROWS instead of the name of a tool to go call
  no_match  — the supplier returned nothing usable; this branch cannot help
"""
import json, subprocess, sys, collections, pathlib

sys.path.insert(0, str(pathlib.Path("services/chat-service").resolve()))
from app.agentruntime.refresolve import decide_absent, bare_id_field  # noqa: E402

SINCE = "2026-08-10"
SEP = "\x1f"


def psql(db: str, sql: str) -> list[str]:
    out = subprocess.run(["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave",
                          "-d", db, "-t", "-A", "-F", SEP, "-c", sql],
                         capture_output=True, text=True, encoding="utf-8",
                         env={"MSYS_NO_PATHCONV": "1"})
    if out.returncode != 0:
        sys.exit(f"psql failed: {out.stderr[:400]}")
    return [l for l in out.stdout.splitlines() if l.strip()]


emitters = json.load(open("contracts/agent-runtime-tool-contracts.json",
                          encoding="utf-8"))["argument_emitters"]
declared = {(t, p): s for t, m in emitters.items() if not t.startswith("_")
            for p, s in m.items()}

fails = [r.split(SEP) for r in psql("loreweave_chat", rf"""
WITH raw AS (
  SELECT tc->>'tool' AS tool,
         (regexp_matches(tc->>'error','missing required argument\(s\): \[([^\]]*)\]'))[1] AS args
  FROM chat_messages m, jsonb_array_elements(COALESCE(m.tool_calls,'[]'::jsonb)) tc
  WHERE tc->>'error' LIKE '%missing required argument%' AND m.created_at >= '{SINCE}'),
split AS (SELECT tool, trim(both ' ''"' from a) AS arg FROM raw, unnest(string_to_array(args, ',')) AS a)
SELECT tool, arg, count(*) FROM split WHERE arg ~ '_id$|_ref$' GROUP BY 1,2""")]

# One real recorded result per supplier tool - the largest, so the harvest is exercised
# against the shape the supplier actually produces rather than an empty page.
results: dict[str, object] = {}
for row in psql("loreweave_chat", r"""
SELECT DISTINCT ON (tc->>'tool') tc->>'tool', (tc->'result')::text
FROM chat_messages m, jsonb_array_elements(COALESCE(m.tool_calls,'[]'::jsonb)) tc
WHERE (tc->>'ok')='true' AND tc ? 'result'
ORDER BY tc->>'tool', length((tc->'result')::text) DESC"""):
    tool, blob = row.split(SEP, 1)
    try:
        results[tool] = json.loads(blob)
    except json.JSONDecodeError:
        pass

tally = collections.Counter()
detail = collections.defaultdict(list)
for tool, arg, n in fails:
    n = int(n)
    sup = declared.get((tool, arg))
    if sup is None:
        tally["undeclared (no emitter)"] += n
        continue
    if sup not in results:
        tally["supplier never observed succeeding"] += n
        detail["unobserved"].append((n, tool, arg, sup))
        continue
    r = decide_absent(arg, sup, results[sup])
    tally[r.outcome] += n
    detail[r.outcome].append((n, tool, arg, sup))

total = sum(tally.values())
if total == 0:
    sys.exit("ABORT: nothing scored - a verdict over zero rows is vacuous.")

print(f"missing-id failures since {SINCE}: {total}\n")
for k, v in tally.most_common():
    print(f"  {k:<34} {v:>4}  {v/total:.0%}")
for kind in ("resolved", "ambiguous"):
    if detail[kind]:
        print(f"\ntop '{kind}':")
        for n, t, a, s in sorted(detail[kind], reverse=True)[:8]:
            print(f"  {n:>4}  {t}.{a} <- {s}")
