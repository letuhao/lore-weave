import json, subprocess, sys, collections

SESS = sys.argv[1]
SEQ = sys.argv[2]
LABEL = sys.argv[3]

def q(sql):
    r = subprocess.run(['docker','exec','infra-postgres-1','psql','-U','loreweave','-d','loreweave_chat','-tAc',sql],
                       capture_output=True, text=True)
    if r.returncode: raise SystemExit(r.stderr)
    return r.stdout

adv = json.loads(q(f"SELECT coalesce(advertised_tools,'[]'::jsonb)::text FROM chat_messages WHERE session_id='{SESS}' AND sequence_num={SEQ};").strip())
wh  = json.loads(q(f"SELECT coalesce(withheld_tools,'[]'::jsonb)::text FROM chat_messages WHERE session_id='{SESS}' AND sequence_num={SEQ};").strip())

snap = json.load(open('contracts/agent-runtime-baseline/tools-list.snapshot.json'))
universe = set(t['name'] for t in snap['tools'])
deprecated = set(snap['summary']['deprecated'])

adv_union = set()
per_pass_adv = {}
for rec in adv:
    per_pass_adv[rec['pass']] = set(rec['names'])
    adv_union |= set(rec['names'])

wh_names = set(r['tool'] for r in wh)
stages = collections.Counter(r['stage'] for r in wh)
per_pass_wh = collections.Counter(r['pass'] for r in wh)
malformed = [r for r in wh if not all(k in r for k in ('tool','stage','reason','pass'))]

neither = universe - adv_union - wh_names
neither_live = neither  # universe == live catalogue, verified separately
neither_dep = neither & deprecated

# what stage did the "neither" tools get? none by definition.
# domain_not_selected accounting
dns = set(r['tool'] for r in wh if r['stage']=='domain_not_selected')

print(f"=== {LABEL} (session {SESS} seq {SEQ}) ===")
print(f"passes={len(adv)} advertised_union={len(adv_union)} withheld_records={len(wh)} withheld_tools={len(wh_names)}")
print(f"advertised per pass: {{{', '.join(f'{p}: {len(n)}' for p,n in sorted(per_pass_adv.items()))}}}")
print(f"withheld records per pass: {dict(sorted(per_pass_wh.items()))}  total {len(wh)}")
print(f"stages: {dict(stages.most_common())}")
print(f"malformed records (missing tool/stage/reason/pass): {len(malformed)}")
print(f"withheld JSON bytes: {len(json.dumps(wh))}")
print()
print(f"  TURN-LEVEL NEITHER = {len(neither)}  (deprecated={len(neither_dep)}, non-deprecated={len(neither-deprecated)})")
print(f"  {sorted(neither)}")
print(f"  of those, recorded as domain_not_selected: {len(neither & dns)}")
print()
# arithmetic close
adv_in_universe = adv_union & universe
print(f"advertised names NOT in the 315 universe: {sorted(adv_union - universe)}")
print(f"arithmetic: 315 - {len(dns)} domain_not_selected = {315-len(dns)} surviving")
other_stages = {s:0 for s in stages if s!='domain_not_selected'}
for r in wh:
    if r['stage']!='domain_not_selected': other_stages[r['stage']] = other_stages.get(r['stage'],0)+1
print(f"            adv-in-universe {len(adv_in_universe)} + other-stage withheld tools {len(wh_names-dns)} = {len(adv_in_universe)+len(wh_names-dns)}")
print(f"            {315-len(dns)} - {len(adv_in_universe)+len(wh_names-dns)} = {315-len(dns)-len(adv_in_universe)-len(wh_names-dns)}")
print()
# the four from round 7
FOUR = ['glossary_book_sync_apply','glossary_plan','glossary_propose_batch','glossary_propose_kinds']
print("ROUND-7 RESIDUAL FOUR — status now:")
for t in FOUR:
    a = [p for p,n in sorted(per_pass_adv.items()) if t in n]
    w = [(r['pass'], r['stage'], r['reason'][:70]) for r in wh if r['tool']==t]
    print(f"  {t:34s} advertised_at_passes={a}  withheld={w if w else 'NO RECORD'}")
print()
# per-pass one-bucket check
print("per-pass NEITHER (cumulative-withheld reading):")
for p in sorted(per_pass_adv):
    cum_wh = set(r['tool'] for r in wh if r['pass']<=p)
    print(f"  pass {p}: strict-neither={len(universe - per_pass_adv[p] - set(r['tool'] for r in wh if r['pass']==p))}  cumulative-neither={len(universe - per_pass_adv[p] - cum_wh)}")
print()
print("inter-pass deltas:")
ps = sorted(per_pass_adv)
for i in range(len(ps)-1):
    a,b = per_pass_adv[ps[i]], per_pass_adv[ps[i+1]]
    rem, add = sorted(a-b), sorted(b-a)
    print(f"  pass{ps[i]}->{ps[i+1]}: -{rem} +{add}" if (rem or add) else f"  pass{ps[i]}->{ps[i+1]}: unchanged ({len(a)})")
