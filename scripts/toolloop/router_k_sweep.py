import asyncio, sys, json, collections
sys.path.insert(0, '/app')
from app.services.skill_router import _get_skill_vectors, ROUTER_CONFIDENCE_THRESHOLD
from app.services.tool_discovery import _resolve_embedding_model
from app.client.embedding_client import get_embedding_client
from loreweave_vecmath import cosine_similarity

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
PREFIX = {"book": "book", "jobs": "jobs", "glossary": "glossary", "composition": "composition",
          "plan": "plan_forge", "kg": "knowledge", "translation": "translation",
          "settings": "settings"}

async def main():
    model = await _resolve_embedding_model(USER)
    vecs = await _get_skill_vectors(user_id=USER)
    rows = [json.loads(l) for l in sys.stdin.read().splitlines() if l.strip()]
    texts = [r["p"] for r in rows]
    embs = []
    for i in range(0, len(texts), 32):
        r = await get_embedding_client().embed(user_id=USER, model_source=model[0],
                                               model_ref=model[1], texts=texts[i:i+32])
        embs.extend(r.embeddings)
    out = {}
    evaluated = 0
    per_k = {k: collections.Counter() for k in (1, 2, 3, 4, 5)}
    for row, v in zip(rows, embs):
        truth = {PREFIX[t.split("_")[0]] for t in (row.get("called") or [])
                 if t.split("_")[0] in PREFIX}
        if not truth:
            continue
        evaluated += 1
        scored = sorted(((c, cosine_similarity(v, vv)) for c, vv in vecs.items()), key=lambda x: -x[1])
        cleared = [c for c, s in scored if s >= ROUTER_CONFIDENCE_THRESHOLD]
        for k in per_k:
            capped = [c for c, _ in scored[:k] if c in cleared]
            per_k[k]["hit"] += bool(truth & set(capped))
            # FLOOD = injected skills the turn did not call a tool from
            per_k[k]["injected"] += len(capped)
            per_k[k]["wasted"] += len([c for c in capped if c not in truth])
    for k, c in per_k.items():
        out[f"K={k}"] = {"correct_domain_injected": c["hit"],
                         "hit_rate": round(c["hit"] / evaluated, 3) if evaluated else None,
                         "skills_injected_total": c["injected"],
                         "injected_but_unused": c["wasted"],
                         "waste_rate": round(c["wasted"] / c["injected"], 3) if c["injected"] else None}
    print(json.dumps({"evaluated_prompts": evaluated, "floor": ROUTER_CONFIDENCE_THRESHOLD,
                      "skills_total": len(vecs), "by_K": out}, indent=1))
asyncio.run(main())
