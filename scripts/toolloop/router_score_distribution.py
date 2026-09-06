"""The intent router's OWN score distribution, per prompt — DQ-T67's ruled instrument.

OWNER RULING 2026-08-31, DQ-T67: "(a) BUILD THE SCORE-DISTRIBUTION INSTRUMENT BEFORE ANY LEVER
MOVES. For a representative prompt corpus, compute the router's own per-prompt score distribution
(pure embedding + cosine, no LLM call) and report how often the correct domain clears the floor
but misses the cap, and how often an unrelated skill makes the cap. No lever — cap, floor or
embedding text — is touched until that exists."

WHY THOSE TWO NUMBERS AND NOT A HIT RATE. `router_k_sweep.py` beside this already answers "does
raising K help" (it does, smoothly, at 2 -> 3 = +6.1 points for 250 more unused injections). What
it cannot say is WHICH FAILURE a prompt suffers, and the two are fixed by different levers:

    correct domain CLEARS the floor but MISSES the cap   -> the CAP is what excludes it
    correct domain does not even clear the floor          -> the FLOOR or the EMBEDDING is
    an UNRELATED skill makes the cap                      -> the RANKING is

A single hit rate mixes all three, which is why the row could argue about the cap for three days
without knowing how much of the problem the cap even owns.

RUN IT INSIDE chat-service, against the DEPLOYED router — real embeddings, real skill vectors:

    docker exec -i infra-chat-service-1 python /tmp/router_score_distribution.py < corpus.jsonl

Each stdin line is {"p": "<the user's prompt>", "called": ["tool_name", ...]}. It WRITES NOTHING
and makes no LLM call: embedding + cosine only, exactly as the router does.

GROUND TRUTH IS THE TOOLS THE TURN ACTUALLY CALLED, mapped to a skill by tool-name prefix. A
prompt whose tools map to no skill is EXCLUDED rather than guessed — the same rule the K-sweep
used (73 of 352 excluded there), because inventing a label would measure the labeller.
"""
import asyncio
import collections
import json
import statistics
import sys

sys.path.insert(0, "/app")

from app.client.embedding_client import get_embedding_client  # noqa: E402
from app.services.skill_router import (  # noqa: E402
    ROUTER_CONFIDENCE_THRESHOLD,
    _get_skill_vectors,
)
from app.services.tool_discovery import _resolve_embedding_model  # noqa: E402
from loreweave_vecmath import cosine_similarity  # noqa: E402

USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"

#: tool-name prefix -> the skill that owns that domain. Only unambiguous prefixes.
PREFIX = {"book": "book", "jobs": "jobs", "glossary": "glossary", "composition": "composition",
          "plan": "plan_forge", "kg": "knowledge", "translation": "translation",
          "settings": "settings"}

CAP = 2  # ROUTER_MAX_ADDITIONS as shipped; reported, never changed here


async def main() -> int:
    model = await _resolve_embedding_model(USER)
    vecs = await _get_skill_vectors(user_id=USER)
    rows = [json.loads(l) for l in sys.stdin.read().splitlines() if l.strip()]
    texts = [r["p"] for r in rows]

    embs = []
    for i in range(0, len(texts), 32):
        r = await get_embedding_client().embed(
            user_id=USER, model_source=model[0], model_ref=model[1], texts=texts[i:i + 32])
        embs.extend(r.embeddings)

    n = 0
    verdicts = collections.Counter()
    cleared_counts, spreads, truth_ranks, truth_scores, margins = [], [], [], [], []
    unrelated_in_cap = collections.Counter()
    examples = []

    for row, v in zip(rows, embs):
        truth = {PREFIX[t.split("_")[0]] for t in (row.get("called") or [])
                 if t.split("_")[0] in PREFIX}
        if not truth:
            continue
        n += 1
        scored = sorted(((c, cosine_similarity(v, vv)) for c, vv in vecs.items()),
                        key=lambda x: -x[1])
        by_skill = dict(scored)
        cleared = {c for c, s in scored if s >= ROUTER_CONFIDENCE_THRESHOLD}
        capped = [c for c, _ in scored[:CAP] if c in cleared]

        cleared_counts.append(len(cleared))
        spreads.append(scored[0][1] - scored[-1][1])
        best = max(truth, key=lambda t: by_skill.get(t, -1))
        rank = [c for c, _ in scored].index(best) + 1 if best in by_skill else None
        if rank:
            truth_ranks.append(rank)
            truth_scores.append(by_skill[best])

        for c in capped:
            if c not in truth:
                unrelated_in_cap[c] += 1

        # THE THREE FAILURES, kept apart because different levers fix them.
        if truth & set(capped):
            verdicts["correct domain IS injected"] += 1
        elif truth & cleared:
            verdicts["cleared the floor, MISSED THE CAP  (the cap owns this)"] += 1
            if len(examples) < 6:
                boundary = scored[CAP - 1][1]
                margins.append(boundary - by_skill[best])
                examples.append({"prompt": row["p"][:70], "needed": sorted(truth),
                                 "rank": rank, "score": round(by_skill[best], 4),
                                 "cap_boundary": round(boundary, 4),
                                 "beaten_by": [c for c, _ in scored[:CAP]]})
        else:
            verdicts["did not even CLEAR the floor  (floor/embedding owns this)"] += 1

    print(json.dumps({
        "evaluated_prompts": n,
        "floor": ROUTER_CONFIDENCE_THRESHOLD,
        "cap": CAP,
        "skills_total": len(vecs),
        "THE_TWO_RULED_FIGURES": {
            "correct_domain_cleared_floor_but_missed_cap":
                verdicts["cleared the floor, MISSED THE CAP  (the cap owns this)"],
            "correct_domain_cleared_floor_but_missed_cap_rate":
                round(verdicts["cleared the floor, MISSED THE CAP  (the cap owns this)"] / n, 3)
                if n else None,
            "turns_with_an_UNRELATED_skill_in_the_cap": sum(unrelated_in_cap.values()),
            "unrelated_cap_slots_per_turn": round(sum(unrelated_in_cap.values()) / n, 2)
                if n else None,
            "which_skills_take_slots_they_should_not": unrelated_in_cap.most_common(8),
        },
        "verdicts": dict(verdicts),
        "floor_is_not_filtering": {
            "skills_clearing_the_floor_median": statistics.median(cleared_counts)
                if cleared_counts else None,
            "prompts_where_EVERY_skill_clears":
                sum(1 for c in cleared_counts if c == len(vecs)),
            "of_prompts": n,
        },
        "ranking_quality": {
            "correct_domain_rank_median": statistics.median(truth_ranks) if truth_ranks else None,
            "correct_domain_score_median": round(statistics.median(truth_scores), 4)
                if truth_scores else None,
            "score_spread_median_top_minus_bottom": round(statistics.median(spreads), 4)
                if spreads else None,
            "median_margin_to_the_cap_when_missed": round(statistics.median(margins), 4)
                if margins else None,
        },
        "examples_of_the_cap_excluding_the_right_skill": examples,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
