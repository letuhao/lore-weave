# M-recall — CJK/VI dictionary-anchor recall fix

**Date:** 2026-07-07 · **Branch:** `feat/context-budget-law` · **Corpus:** 万古神帝 (wangu,
`019f37f0`, 158 ent) · **Model:** none needed (recall is a graph-fact metric, not answer-quality).
Follow-on from the M3 measurement, which found the real lever is **retrieval recall**, not budget.

## Root cause (confirmed against code + graph)

The M3 passage top-K sweep found 3–4/12 wangu goldens miss at *every* K — the answer isn't retrieved.
Tracing each through the stack showed the answers **exist in the graph as clean 1-hop relations**
(`张若尘 —cultivates→ 《九天明帝经》`, `林泞姗 —owns→ 星辉宝剑`, `九王子 —practices→ 龙象般若掌`),
yet `select_l2_facts` returned **0 facts**. The cause is in the intent classifier's `entities`:

| Query | classifier "entities" |
|---|---|
| 九王子修炼什么武功？ | `['九王子修炼什么武功']` — the whole question |
| 林泞姗属于哪个家族，拥有什么武器？ | `['林泞姗属于哪个家族', '拥有什么武器']` |

`extract_candidates` splits on whitespace/punctuation; Chinese is scriptio-continua (no spaces), so it
emits whole **clauses** as "entities". `select_l2_facts` then looks up an entity literally named
"九王子修炼什么武功", finds nothing → 0 facts. This silently degrades L2 recall for **every Chinese and
Vietnamese book** (the query-side sibling of the passage-prose extractor bug). The M1a passage→graph
bridge partly masks it by anchoring on passage-surfaced entities instead.

## Fix — Aho-Corasick dictionary matching (not segmentation)

We already KNOW every entity name, so this is **dictionary matching**, not word segmentation. Build a
per-project **Aho-Corasick** automaton (`pyahocorasick`) over entity names + aliases and match the
message against it; UNION the hits into `intent.entities` before the L2 / widened-retry / M1a-bridge
path. Language-agnostic (zh/ja/ko/vi in one path — jieba is zh-only), exact (no segmentation errors),
sub-millisecond. Gated to non-Latin messages (Latin already segments on whitespace; running it there
risks matching short names like "Will" inside "I will"). Per-project TTL cache; degrade-safe at every
step (no pyahocorasick / load timeout / empty project → classifier-only). Kill-switch
`context_dict_anchor_enabled`.

- `app/context/anchors.py` — automaton cache + `resolve_anchors` (longest-match tiling, dedup, cap).
- `app/db/neo4j_repos/entities.py::list_project_entity_names` — owner+project-scoped name+alias load.
- `app/context/modes/full.py` — gated, timeout-bounded merge into `intent.entities`.

## Result — L2 answer-recall A/B (wangu, n=12)

| | classifier-only | +dict-anchor |
|---|---|---|
| **L2 answer-recall** | **2/12** | **7/12** |
| flipped miss→hit | — | **5** (云武郡王's sons · 清玄阁 owner · 林泞姗 family+weapon · 九王子 武功 · 张若尘's swords) |
| **regressions** | — | **0** |

The 5 recovered queries all **name the entity in the message** (directly or inside a clause the
classifier glued up) — exactly what dictionary matching resolves. The 5 still-missing are **role-only
coreference** ("主角"/"被重生的少年" → 张若尘, never named) — a different problem for the M1a bridge /
a future role-resolution step, out of scope here.

## Verification

- **Unit:** 3663 knowledge-service unit tests green, incl. 19 new `test_anchors` (gate · tiling ·
  dedup · cap · min-len · alias→canonical · cache/TTL/degrade) + 2 `build_full_mode` wiring guards.
  A unit test caught a real surface-vs-canonical length bug in the tiling (aliases) before ship.
- **Live A/B:** the table above — real `anchors.py` + real `select_l2_facts` against the live wangu
  Neo4j graph; English message stays gated-off (0 facts, unchanged).
- **OSS build:** `pyahocorasick` ships a prebuilt `cp312-manylinux2014` wheel; a real
  `docker build --target deps` on `python:3.12-slim` installed it (as root, build-time) with **no
  compiler and no permission issue** — the Dockerfile needs no change (adding to requirements.txt
  suffices; the runtime `USER app` only affects run-time, not the build install).

## Note

Dictionary matching can over-fire on a very common short entity name (e.g. a generic 2-char term);
mitigated by `min_len≥2` + longest-match tiling (drops nested) + `cap` + downstream 1-hop bounding +
budget-trim. At 10k+ entities the per-project name load + automaton build is the cost to watch
(cached, timeout-bounded).

---

## Follow-on — role→entity coreference (protagonist resolution)

The 5 queries the dictionary matcher couldn't recover all reference the lead by ROLE, not name
("被重生的主角的母亲", "主角达到什么境界"). Diagnosis: (a) resolving the role to the project's
**most-central entity** recovers **5/5**; (b) the M1a passage→graph bridge only recovers **2/5** even
though the protagonist IS in the retrieved passages — its 1-hop expansion over 张若尘's **150**
relations crowds out the specific answer. And the protagonist is unambiguous by degree: **张若尘 = 150,
next = 46** (3× gap).

**Fix:** on a message containing a strict protagonist role-term
(`主角`/`主人公`/`男主`/`protagonist`/`main character`/`nhân vật chính`/… — deliberately NOT generic
`少年`/`the boy`), anchor the project's most-connected entity (`get_most_connected_entity`, degree-ranked
— a place can have high salience but not high character-degree). Additive, cached (own TTL), timeout-
bounded, degrade-safe, kill-switch `context_role_anchor_enabled`.

**Combined result (dict-anchor + role-resolution), L2 answer-recall A/B (wangu, n=12):**

| | classifier-only | +dict-anchor +role |
|---|---|---|
| **L2 answer-recall** | **2/12** | **11/12** |
| flipped miss→hit | — | **9** |
| **regressions** | — | **0** |

The single remaining miss ("那位重生的少年…") uses the generic noun 少年 — genuine NLP coreference
(a minor youth vs the reborn protagonist) that a role-term list correctly refuses to guess. That's the
honest floor here; real coref is a separate, larger track.

Verify: +14 unit tests (role-gate detection · protagonist cache/degrade · 2 build_full_mode wiring
guards), 3677 knowledge unit tests green; live A/B above against the real wangu graph.
