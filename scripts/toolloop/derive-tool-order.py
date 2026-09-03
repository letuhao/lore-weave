"""Re-derive the tool cohort with the CORRECTED group-A ordering.

🔴 THE CORRECTION. The first ordering ranked group A by total recorded failures, and that treats
the whole corpus as a statement about the CURRENT code. It is not. `glossary_propose_curation`
ranked first with 29 failures — and all 26 of its dominant failure are dated 2026-08-10
06:28-07:03Z, while the commit that fixed them (cc41f8c2f, "the dispatch was dropping the field
it then demanded") landed 2026-08-10 15:41Z. The ordering was pointing at a tool whose failures
could no longer happen, and it would have gone on pointing there forever.

A recorded failure is evidence about the deployed code only if it POSTDATES the last change to
the tool's owning service. So group A now ranks on LIVE failures (failures newer than that
commit), with total failures as the tiebreak so a tool with only historical failures still sits
in A rather than vanishing into B.

Ownership is read from each provider's OWN tools/list (see derive_owners.py), never from the
tool-name prefix — a consumer-local tool's name can lie about its owner.
"""
import json, io, os, collections, datetime as dt

SP = os.environ.get("TOOLLOOP_WORKDIR") or os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
owners = json.load(io.open(os.path.join(SP, "owners.json"), encoding="utf-8"))["owner"]
cat = [x["name"] for x in json.load(io.open(os.path.join(SP, "tools.json"), encoding="utf-8"))["result"]["tools"]]

def _utc_naive(value):
    """Both sides of the live/historical cutoff must be naive UTC.

    Call timestamps come out of psql as `at time zone 'UTC'`, i.e. naive UTC. A commit time
    dumped as %cI carries an offset and comparing the two raises. Worse than the raise: a commit
    time dumped in LOCAL wall-clock with no offset compares SILENTLY and skews the cutoff by the
    local offset (+07:00 here) - enough to reclassify a whole afternoon of failures as
    historical. So normalise here rather than trusting the dump.
    """
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)


last = {}
for line in io.open(os.path.join(SP, "svc_last_commit.tsv"), encoding="utf-8"):
    if "\t" not in line:
        continue
    s, iso = line.rstrip("\n").split("\t", 1)
    if iso.strip():
        last[s] = _utc_naive(iso.strip())

total_f = collections.Counter()
live_f = collections.Counter()
calls = collections.Counter()
for line in io.open(os.path.join(SP, "calls_ts.tsv"), encoding="utf-8"):
    parts = line.rstrip("\n").split("\t")
    if len(parts) != 3:
        continue
    tool, ts, outcome = parts
    if not tool:
        continue
    calls[tool] += 1
    if outcome != "failed":
        continue
    total_f[tool] += 1
    svc = (owners.get(tool) or {}).get("service")
    cut = last.get(svc)
    if cut is None:
        live_f[tool] += 1        # unknown owner ⇒ cannot prove it is historical ⇒ treat as live
        continue
    try:
        when = _utc_naive(ts)
    except ValueError:
        live_f[tool] += 1
        continue
    if when > cut:
        live_f[tool] += 1

# A tool already CONCLUDED in the ledger leaves the cohort - otherwise the loop re-derives it
# forever. Not hypothetical: glossary_propose_curation's live defect was fixed in CHAT-SERVICE
# (an argument repair) while this ordering's cutoff keys on its OWNING service, glossary-service,
# whose last commit did not move. The ledger is the progress authority; the ordering only decides
# what comes next AMONG THE UNCONCLUDED.
_ledger = json.load(io.open(os.path.join(REPO, 'contracts', 'tool-deep-dive-ledger.json'),
                            encoding='utf-8'))
concluded = {k for k, v in (_ledger.get('tools') or {}).items()
             if v.get('state') in ('proven', 'blocked')}
names = sorted(n for n in cat if n not in concluded)
if concluded:
    print('excluded', len(concluded), 'concluded:', sorted(concluded))
prov = collections.Counter((owners.get(n) or {}).get("provider", "gateway-local") for n in names)
A = sorted([n for n in names if total_f[n] > 0],
           key=lambda n: (-live_f[n], -total_f[n], n))
B = sorted([n for n in names if total_f[n] == 0 and calls[n] > 0], key=lambda n: (-calls[n], n))
C = sorted([n for n in names if total_f[n] == 0 and calls[n] == 0],
           key=lambda n: (-prov[(owners.get(n) or {}).get("provider", "gateway-local")], n))

out = {
    "A": [{"tool": n, "live_fails": live_f[n], "total_fails": total_f[n], "calls": calls[n],
           "service": (owners.get(n) or {}).get("service", "gateway-local")} for n in A],
    "B": [{"tool": n, "calls": calls[n]} for n in B],
    "C": C,
    "counts": {"federated": len(names), "A": len(A), "B": len(B), "C": len(C)},
}
io.open(os.path.join(SP, "order2.json"), "w", encoding="utf-8").write(json.dumps(out, indent=1))
print(f"federated={len(names)} A={len(A)} B={len(B)} C={len(C)}")
print("\nGROUP A, corrected order (live_fails, total_fails, calls, service):")
for r in out["A"]:
    print(f"  {r['live_fails']:>3} {r['total_fails']:>4} {r['calls']:>5}  {r['tool']:<34} {r['service']}")
