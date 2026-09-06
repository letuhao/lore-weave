"""Is the router's problem the EMBEDDING MODEL or the SKILL DESCRIPTION TEXTS?

D-THE-INTENT-ROUTERS-TOP-K-CAP-CROWDS-OUT-THE-RIGHT-DOMAIN states the alternative and never
resolves it: "either the embedding model in use discriminates poorly, or the skill-description
texts being embedded are too similar to each other".

skill_router.py's own 2026-07-25 comment measures skill-to-INTENT similarity ("EVERY novel-
authoring skill description scores 0.35-0.66 cosine to ANY authoring intent"). Nobody has
measured skill-to-SKILL. That is the quantity that separates the two causes:

  * skill vectors mutually FAR APART but all close to any intent  -> the intent embedding is
    what fails to discriminate; the descriptions are fine.
  * skill vectors mutually CLOSE                                  -> the descriptions occupy one
    tight cluster, and NO threshold and NO cap over these vectors can separate them. The lever
    is the text, not the numbers.

Runs against the DEPLOYED router inside infra-chat-service-1. Reads only; moves no lever.
"""
import asyncio
import itertools
import statistics


async def main():
    from app.services.skill_router import (
        ROUTER_CONFIDENCE_THRESHOLD, _get_skill_vectors, _skill_embedding_text)

    import os
    uid = os.environ.get("LW_UID") or None
    vecs = await _get_skill_vectors(user_id=uid)
    print(f"user_id used: {uid!r}")
    if not vecs:
        print("REFUSED TO REPORT: the router returned no vectors (its documented degrade path). "
              "Nothing here would be about the skills.")
        return

    codes = sorted(vecs)
    print(f"skills embedded: {len(codes)}   dim={len(vecs[codes[0]])}")

    def cos(a, b):
        num = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return num / (na * nb) if na and nb else 0.0

    pairs = [(a, b, cos(vecs[a], vecs[b])) for a, b in itertools.combinations(codes, 2)]
    sims = [p[2] for p in pairs]
    print(f"\nSKILL-TO-SKILL cosine over {len(pairs)} pairs:")
    print(f"    min    {min(sims):.4f}")
    print(f"    median {statistics.median(sims):.4f}")
    print(f"    max    {max(sims):.4f}")
    print(f"    spread {max(sims) - min(sims):.4f}")
    print(f"\n  the ROUTER'S FLOOR sits at {ROUTER_CONFIDENCE_THRESHOLD}")
    above = sum(1 for s in sims if s >= ROUTER_CONFIDENCE_THRESHOLD)
    print(f"  pairs of DISTINCT skills that are more similar to each other than the floor "
          f"a skill must clear to be injected: {above} of {len(pairs)}")

    print("\n  closest pairs (the ones a ranker must tell apart):")
    for a, b, s in sorted(pairs, key=lambda p: -p[2])[:6]:
        print(f"      {s:.4f}  {a} / {b}")
    print("\n  furthest pairs:")
    for a, b, s in sorted(pairs, key=lambda p: p[2])[:3]:
        print(f"      {s:.4f}  {a} / {b}")

    print("\n  the text actually embedded, first 90 chars each:")
    for c in codes:
        print(f"      {c:14} {_skill_embedding_text(c)[:90]}")


asyncio.run(main())
