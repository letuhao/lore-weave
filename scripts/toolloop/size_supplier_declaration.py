"""Size the supplier-declaration fix against the failures it claims to prevent.

For every recorded `missing required argument: ['<something>_id']` failure since the
refresolve fix (2026-08-10), ask ONE question: is there a tool that DEMONSTRABLY returns
that id field in a successful result? If yes, the id had a supplier all along and the only
thing missing was a declaration connecting the two. If no, the fix cannot help that pair
and a different remedy is needed.

The supplier map is MINED, never assumed: a tool counts as a supplier only if its own
recorded `ok:true` results contain the field. That keeps the estimate honest -- a supplier
this script invents is one the model could not have called either.
"""
import json, re, subprocess, sys, collections

#: Role prefixes that name the id's ROLE in the call, not its TYPE.
ROLE_PREFIX = re.compile(r'^(from|to|source|target|parent|child|left|right)_')

SINCE = "2026-08-10"


def psql(sql: str) -> list[str]:
    out = subprocess.run(
        ["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave",
         "-d", "loreweave_chat", "-t", "-A", "-F", "\x1f", "-c", sql],
        capture_output=True, text=True, encoding="utf-8", env={"MSYS_NO_PATHCONV": "1"})
    if out.returncode != 0:
        sys.exit(f"psql failed: {out.stderr[:400]}")
    return [l for l in out.stdout.splitlines() if l.strip()]


# ── 1. the failures the fix must answer for ──────────────────────────────────
fail_rows = psql(rf"""
WITH raw AS (
  SELECT tc->>'tool' AS tool,
         (regexp_matches(tc->>'error','missing required argument\(s\): \[([^\]]*)\]'))[1] AS args
  FROM chat_messages m, jsonb_array_elements(COALESCE(m.tool_calls,'[]'::jsonb)) tc
  WHERE tc->>'error' LIKE '%missing required argument%' AND m.created_at >= '{SINCE}'),
split AS (SELECT tool, trim(both ' ''"' from a) AS arg FROM raw, unnest(string_to_array(args, ',')) AS a)
SELECT tool, arg, count(*) FROM split WHERE arg ~ '_id$|_ref$' GROUP BY 1,2""")
failures = [(r.split("\x1f")[0], r.split("\x1f")[1], int(r.split("\x1f")[2])) for r in fail_rows]

# ── 2. the suppliers that DEMONSTRABLY exist ─────────────────────────────────
# A tool supplies field F if a successful result of that tool contains key F anywhere.
# 🔴 THE VALUE MUST BE A UUID, NOT JUST THE KEY. A first pass keyed on the field NAME
# alone credited `tool_load` as a supplier of world_id/map_id/job_id -- it returns tool
# SCHEMAS, so every id parameter appears as a property KEY there. A schema is a
# description of the argument, not a value the model can pass. Requiring the value to be
# a UUID removes that whole class of false positive.
sup_rows = psql(r"""
SELECT DISTINCT s.tool, kv.key
FROM (
  SELECT tc->>'tool' AS tool, x
  FROM chat_messages m,
       jsonb_array_elements(COALESCE(m.tool_calls,'[]'::jsonb)) tc,
       LATERAL jsonb_path_query(tc->'result', '$.**') x
  WHERE (tc->>'ok')='true' AND jsonb_typeof(x) = 'object'
) s, LATERAL jsonb_each_text(s.x) kv
WHERE kv.key ~ '_id$|_ref$'
  AND kv.value ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'""")
supplies = collections.defaultdict(set)
for r in sup_rows:
    tool, field = r.split("\x1f")
    supplies[field].add(tool)

# ── 2b. a supplier must be a READ ────────────────────────────────────────────
# 🔴 SUGGESTING A WRITE TOOL AS A SUPPLIER IS WORSE THAN SUGGESTING NOTHING. Mined by
# value alone, `composition_find_references.entity_id` came back sourced from
# `glossary_entity_rename` -- a tool that returns an entity_id because it just RENAMED
# something. Telling a model to call that to obtain an id invites an unrequested write.
# refresolve already refuses a non-read resolver at registration (check_resolver); the
# same rule has to hold for a declaration a model is told to act on.
# 🔴 AND THE LANE SOURCE MUST BE THE ONE THE RUNTIME USES. A first pass read lanes from
# `agent-runtime-manifest.json`, which declares TWELVE tools of 183 -- so every supplier
# absent from it was scored as non-read and coverage "collapsed" from 95% to 10%. That was
# an artifact of the instrument, not a property of the platform. The catalogue cache is the
# full surface (316 tools, tier A/R/W) and is what the turn's index is built from.
CATALOG = json.load(open("contracts/tool-catalog-cache.json", encoding="utf-8"))
TIER = {name: (spec.get("meta") or {}).get("tier") for name, spec in CATALOG.items()}
unknown = {t for tools in supplies.values() for t in tools if t not in TIER}
for field, tools in list(supplies.items()):
    # tier R is the read lane. A tool absent from the catalogue cannot be shown to be a
    # read, and "cannot be shown to be safe" fails closed -- the same rule check_resolver
    # applies at registration.
    supplies[field] = {t for t in tools if TIER.get(t) == "R"}

# ── 3. score ─────────────────────────────────────────────────────────────────
covered = uncovered = 0
cov_pairs, unc_pairs = [], []
for tool, arg, n in failures:
    # 🔴 A ROLE PREFIX IS NOT A DIFFERENT ID TYPE. `composition_motif_link_edit` requires
    # from_motif_id + to_motif_id; `composition_motif_search` returns `motif_id`. Scored on
    # the literal name those 168 failures looked unsupplied, when the supplier was the
    # single most reliable tool in the corpus (620/626 ok). The prefix states the ROLE the
    # id plays in the call, not the kind of thing it identifies.
    bare = ROLE_PREFIX.sub("", arg)
    # a tool may not supply its OWN required id - that would be circular
    sources = sorted((supplies.get(arg, set()) | supplies.get(bare, set())) - {tool})
    if sources:
        covered += n
        cov_pairs.append((n, tool, arg, sources[:3]))
    else:
        uncovered += n
        unc_pairs.append((n, tool, arg))

total = covered + uncovered
if total == 0:
    sys.exit("ABORT: zero failures scored - the query matched nothing, so any verdict "
             "below would be vacuous.")

print(f"  (suppliers not in the catalogue, refused as unproveable: {len(unknown)})")
print(f"missing-id failures since {SINCE}: {total} across {len(failures)} (tool, param) pairs\n")
print(f"  A SUPPLIER EXISTS (declaration would connect them): {covered:>4}  {covered/total:.0%}")
print(f"  NO SUPPLIER FOUND (needs a different remedy):       {uncovered:>4}  {uncovered/total:.0%}\n")

print("top pairs a declaration would answer:")
for n, tool, arg, src in sorted(cov_pairs, reverse=True)[:12]:
    print(f"  {n:>4}  {tool}.{arg:<18} <- {', '.join(src)}")
print("\ntop pairs it would NOT:")
for n, tool, arg in sorted(unc_pairs, reverse=True)[:10]:
    print(f"  {n:>4}  {tool}.{arg}")
