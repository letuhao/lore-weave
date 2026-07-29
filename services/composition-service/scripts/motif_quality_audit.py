#!/usr/bin/env python
"""Motif library QUALITY audit — the embedding-space bars, measured against a live DB.

The pure-text bars (precond↔effect linkage, tension shape, vi mirroring) are unit tests in
`tests/unit/test_motif_pack_quality.py` and run in CI. The bars below need a seeded database
and a working platform embed model, so they live here and are run deliberately — before and
after authoring a pack.

The runtime image COPYs `app/` only — NOT `scripts/` (the same R-NODE-P1 trap that made the
seed packs FileNotFound at container boot until they moved inside the package). So this is
copied in for the run rather than invoked in place:

    docker cp services/composition-service/scripts/motif_quality_audit.py \
        infra-composition-service-1:/app/motif_quality_audit.py
    docker exec infra-composition-service-1 sh -c 'cd /app && python motif_quality_audit.py'

It needs `COMPOSITION_DB_URL` (set in the container) and a reachable platform embed model.

WHAT IT MEASURES

  1. SELF-RETRIEVAL RECALL — for every motif, embed its author-written `examples[0].text` as a
     query and rank the whole library against it. `examples` are NOT part of
     `motif_summary_text` (only name + summary + beat labels + intents are embedded), so this
     is a genuine query→document test: it asks whether a CONCRETE premise finds the ABSTRACT
     motif that describes it.

     Production returns top-15 for an LLM to choose from, so **recall@15 is the reachability
     gate**; rank-1 is a sharpness measure and is partly zero-sum between adjacent motifs —
     do not chase it. Reference points from the 2026-07-29 audit: cultivation / intrigue /
     revenge score 100% @1 (they are written concretely); `hook` scores 0% @1 and 31% @15
     because single-beat hooks have almost no text to embed.

     The failure mode it catches is real: it found `rebirth.butterfly_divergence` at rank 59
     because its example illustrated `rebirth.save_what_was_lost` — a mis-authored example
     that reads fine to a human.

  2. CONFUSABLE PAIRS — the nearest neighbours across the whole library. Above ~0.72 is worth
     a look: it caught `wuxia.righteous_debt` at 0.733 against `cultivation.master_disciple_debt`,
     which were genuinely the same motif written twice with inverted roles.

  3. PACK SEPARATION (intra-pack minus inter-pack mean cosine) — read this one carefully. It is
     LOW for `cultivation` (+0.03) and `wuxia` (+0.04) not because those packs are bad but
     because they are SETTINGS rather than situation-types; `mystery` (all investigation) and
     `emotion_arc` (all emotional shape) score high because their members share a semantic core.
     A low number here is a prompt to ask which kind of pack it is, not a defect to fix.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.repositories.motif_retrieve import _cosine  # noqa: E402
from app.engine.motif_embed import (  # noqa: E402
    embed_motif_summary, embed_query, motif_summary_text,
)

LANG = os.environ.get("AUDIT_LANG", "en")
CONFUSABLE_AT = 0.72


class _M:
    def __init__(self, row):
        self.code, self.name, self.summary = row["code"], row["name"], row["summary"]
        self.beats = json.loads(row["beats"]) if isinstance(row["beats"], str) else row["beats"]
        ex = json.loads(row["examples"]) if isinstance(row["examples"], str) else row["examples"]
        self.example = ex[0].get("text", "") if ex else ""

    @property
    def pack(self) -> str:
        return self.code.split(".", 1)[0]


async def main() -> int:
    dsn = os.environ.get("COMPOSITION_DB_URL")
    if not dsn:
        print("COMPOSITION_DB_URL unset — run this inside the composition container.")
        return 2
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT code, name, summary, beats, examples FROM motif "
            "WHERE owner_user_id IS NULL AND language = $1 AND status = 'active' ORDER BY code",
            LANG)
    ms = [_M(r) for r in rows]
    if not ms:
        print(f"no system motifs in language {LANG!r} — is the library seeded?")
        return 2
    print(f"{len(ms)} system motifs ({LANG})\n")

    vecs = {m.code: (await embed_motif_summary(motif_summary_text(m))).embeddings[0] for m in ms}

    # ── 1 · self-retrieval
    ranks, misses = [], []
    for m in ms:
        if not m.example:
            continue
        q = await embed_query(m.example)
        ranked = sorted(((_cosine(q, vecs[o.code]), o.code) for o in ms), reverse=True)
        pos = next(i for i, (_s, code) in enumerate(ranked, 1) if code == m.code)
        ranks.append((pos, m.code))
        if pos > 1:
            misses.append((pos, m.code, ranked[0][1], ranked[0][0]))

    n = len(ranks)
    print(f"== 1 · SELF-RETRIEVAL | rank-1={sum(1 for p, _ in ranks if p == 1)/n:.0%} "
          f"recall@5={sum(1 for p, _ in ranks if p <= 5)/n:.0%} "
          f"recall@15={sum(1 for p, _ in ranks if p <= 15)/n:.0%} "
          f"MRR={sum(1/p for p, _ in ranks)/n:.3f}")
    by = defaultdict(list)
    for pos, code in ranks:
        by[code.split(".")[0]].append(pos)
    for pack in sorted(by):
        ps = by[pack]
        flag = "   <-- weak reachability" if sum(1 for p in ps if p <= 15) / len(ps) < 0.75 else ""
        print(f"   {pack:14} n={len(ps):2}  @1={sum(1 for p in ps if p <= 1)/len(ps):4.0%}"
              f"  @5={sum(1 for p in ps if p <= 5)/len(ps):4.0%}"
              f"  @15={sum(1 for p in ps if p <= 15)/len(ps):4.0%}  worst=rank {max(ps)}{flag}")
    print("\n   worst misses (its own example retrieves something else):")
    for pos, code, thief, score in sorted(misses, reverse=True)[:6]:
        print(f"      rank {pos:2}  {code:38} lost to {thief} ({score:.3f})")
    if misses:
        print("\n   most frequent attractors (broad motifs that steal top slots):")
        for thief, cnt in Counter(m[2] for m in misses).most_common(5):
            print(f"      {cnt}x  {thief}")

    # ── 2 · confusable pairs
    pairs = sorted(((_cosine(vecs[a.code], vecs[b.code]), a.code, b.code)
                    for i, a in enumerate(ms) for b in ms[i + 1:]), reverse=True)
    print(f"\n== 2 · CONFUSABLE PAIRS (>= {CONFUSABLE_AT}) ==")
    hot = [p for p in pairs if p[0] >= CONFUSABLE_AT]
    for s, a, b in hot[:10]:
        same = "  (same pack)" if a.split(".")[0] == b.split(".")[0] else ""
        print(f"   {s:.3f}  {a:38} ~ {b}{same}")
    if not hot:
        print("   none — no two motifs are near-duplicates")

    # ── 3 · pack separation
    intra, inter = defaultdict(list), defaultdict(list)
    for s, a, b in pairs:
        pa, pb = a.split(".")[0], b.split(".")[0]
        if pa == pb:
            intra[pa].append(s)
        else:
            inter[pa].append(s)
            inter[pb].append(s)
    print("\n== 3 · PACK SEPARATION (intra - inter; a SETTING pack scores low by nature) ==")
    for pack in sorted(intra):
        ia = sum(intra[pack]) / len(intra[pack])
        ie = sum(inter[pack]) / len(inter[pack])
        print(f"   {pack:14} intra={ia:.3f} inter={ie:.3f} sep={ia - ie:+.3f}")

    await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
