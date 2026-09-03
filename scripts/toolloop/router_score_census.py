import asyncio, sys, json, collections
sys.path.insert(0, '/app')
from app.services.skill_router import (_get_skill_vectors, ROUTER_CONFIDENCE_THRESHOLD,
                                       ROUTER_MAX_ADDITIONS)
from app.services.tool_discovery import _resolve_embedding_model
from app.client.embedding_client import get_embedding_client
from loreweave_vecmath import cosine_similarity

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
# tool prefix -> skill code. Only unambiguous mappings; anything else is left out of
# ground truth rather than guessed, because a wrong label here invents a failure.
PREFIX = {"book": "book", "jobs": "jobs", "glossary": "glossary", "composition": "composition",
          "plan": "plan_forge", "kg": "knowledge", "translation": "translation",
          "settings": "settings"}

async def main():
    model = await _resolve_embedding_model(USER)
    vecs = await _get_skill_vectors(user_id=USER)
    rows = [json.loads(l) for l in sys.stdin.read().splitlines() if l.strip()]
    texts = [r["p"] for r in rows]
    embs = []
    B = 32
    for i in range(0, len(texts), B):
        r = await get_embedding_client().embed(user_id=USER, model_source=model[0],
                                               model_ref=model[1], texts=texts[i:i+B])
        embs.extend(r.embeddings)
    n_clear = collections.Counter()
    stats = collections.Counter()
    for row, v in zip(rows, embs):
        truth = {PREFIX[t.split("_")[0]] for t in (row.get("called") or [])
                 if t.split("_")[0] in PREFIX}
        if not truth:
            stats["no_ground_truth"] += 1
            continue
        scored = sorted(((c, cosine_similarity(v, vv)) for c, vv in vecs.items()), key=lambda x: -x[1])
        cleared = [c for c, s in scored if s >= ROUTER_CONFIDENCE_THRESHOLD]
        capped = [c for c, _ in scored[:ROUTER_MAX_ADDITIONS]]
        n_clear[len(cleared)] += 1
        stats["evaluated"] += 1
        hit_cap = bool(truth & set(capped))
        in_floor = bool(truth & set(cleared))
        if hit_cap: stats["correct_domain_MADE_the_cap"] += 1
        elif in_floor: stats["cleared_the_floor_but_MISSED_the_cap"] += 1
        else: stats["did_not_even_clear_the_floor"] += 1
        if not hit_cap and capped: stats["an_UNRELATED_skill_took_a_cap_slot"] += 1
    print(json.dumps({"stats": dict(stats),
                      "skills_clearing_the_floor_per_prompt": dict(sorted(n_clear.items())),
                      "floor": ROUTER_CONFIDENCE_THRESHOLD, "cap": ROUTER_MAX_ADDITIONS,
                      "skills_total": len(vecs)}, indent=1))
asyncio.run(main())
