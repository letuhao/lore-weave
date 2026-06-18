# Cycle 18 — live-smoke evidence

**Token:** `live smoke: query built project subgraph → capped nodes+edges`

Cross-service: FE/gateway (:3123) → knowledge-service (:8216) → Neo4j.
knowledge-service image rebuilt + `up -d` before the smoke (no stale image).
Built project `019eb683-8de9-7cc4-8aec-e120166cfffd` (万古神帝), test account
`claude-test@loreweave.dev`.

| Check | Request | Result |
|---|---|---|
Re-run AFTER the adversary fixes (bounded-frontier ego BFS replacing the
`*1..3` path enumeration; project_id bound on both edge endpoints):

| Capped subgraph | `GET /v1/knowledge/projects/019eb683…/subgraph?limit=50` | 200 — **50 nodes, 145 edges, node_cap_hit=true** (real entities e.g. 张若尘, edge `lives_in` conf 0.95) |
| Cap not hit on full graph | `…/subgraph?limit=200` | 200 — 55 nodes, 146 edges, node_cap_hit=false (whole partition < cap) |
| Cross-project isolation | `GET …/projects/00000000-…-ff/subgraph?limit=50` (unowned) | 200 — **0 nodes, 0 edges** (no foreign nodes; both user_id + project_id bound) |
| Ego-expansion (bounded BFS) | `…/subgraph?center=<top>&hops=2&limit=50` | 200 — 38 nodes, 145 edges, center in set |

Artifacts: `subgraph-project-built-limit50.json`,
`subgraph-project-built-full.json`, `subgraph-foreign-project-empty.json`,
`subgraph-ego-center.json` (raw endpoint responses).

`scripts/raid/verify-cycle-18.sh` exits 0 — **97 pytest green** incl. 23 new
C18 unit tests + **4 live-Neo4j integration tests** (partition isolation,
cap+determinism, ego hop-bounding, inactive-edge exclusion — real Cypher
execution, addressing adversary F4). `ai-provider-gate.py` green.
