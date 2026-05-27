# Adversary DESIGN review — geo-phase-1 — round 2

**Task:** geo-phase-1 (`docs/plans/2026-05-17-geo-phase-1.md`)
**Phase:** REVIEW (design) — cold-start AMAW Adversary, round 2
**Verdict:** REJECTED (2 BLOCK, 1 WARN)

---

## Round-1 resolution confirmations

- **R1 Finding 1 (degree 3..=12 unguaranteed)** — PARTIALLY RESOLVED. The perimeter
  ring is a genuine construction change that fixes interior cells (strictly-inside ->
  closed fan -> degree >=3). But the ring-*corner* sub-case is not actually proven — see
  Finding A below. The upper bound 12 is now correctly downgraded to a sanity assertion
  rather than a load-bearing claim, which is acceptable.
- **R1 Finding 2 (contradictory cell-count formula)** — RESOLVED. A single formula
  `(g-2)^2 + 4*(g-1)` is stated once, with `g = round(sqrt(target))`, and the per-scale
  table arithmetic checks out exactly: 32->1024, 45->2025, 91->8281, 111->12321,
  128->16384. Criterion #3 asserts exact equality with no tolerance — correctly
  machine-verifiable.
- **R1 Finding 3 (land coherence unenforced)** — RESOLVED. Criterion #5 now specifies a
  connected-components flood-fill over land cells with a >=85% largest-component bound,
  machine-checked in `structure.rs`, profile-conditional with Archipelago exempted. The
  land-fraction proxy is no longer the criterion. (A residual weakness in the Archipelago
  branch is raised as Finding C, not as an unresolved R1 item.)

---

## Finding A — BLOCK — The perimeter-ring degree proof does not cover ring corners

**Acceptance criterion at risk:** #4 (`neighbour degree in [3,12]` for every cell —
"degree >=3 guaranteed by the ring construction").

§4's proof states every ring point has "exactly 2 ring-neighbours (consecutive hull
edges) + >=1 interior point it faces -> degree >= 3." The "+>=1 interior point" step is
asserted, not proven, and it fails precisely at the **four ring corners**:

- The ring is the convex hull of the point set. A convex-hull vertex is incident to
  *at least one* triangle, but a hull vertex incident to exactly **one** triangle has
  degree exactly **2** (the two other vertices of that single triangle).
- A corner's two adjacent ring points lie along the two perpendicular hull edges. The
  nearest interior grid point sits diagonally inward. Whether the corner shares a
  Delaunay edge with that interior point — versus the corner's single triangle being
  formed by the two adjacent ring points alone — depends on the cocircular geometry of
  that local 4-point configuration. With un-jittered ring points and a `+1`-offset
  interior grid, the corner can be left as a degree-2 cell.
- Because the invariant is regeneration-determinism, a degree-2 corner is not a flake:
  it is a permanent, reproducible criterion-#4 failure baked into that `(seed, scale)`.

The interior-cell half of the proof IS sound (strictly-inside hull -> closed fan >=3).
Only the corner case is unproven, and corners are exactly the cells the ring was added
to protect.

**Concrete fix:** Make the corner degree deterministic by construction, not by hope.
Either (a) place the four ring corners *plus their immediately adjacent interior grid
cells* such that a corner is guaranteed two interior Delaunay neighbours — e.g. add one
extra fixed point just inside each corner — or (b) after triangulation, run a
post-process that detects any cell with degree <3 and repairs it (merge or add the
nearest non-neighbour), then assert. Whichever is chosen, §4 must state the corner case
explicitly with a guarantee, and the structure test must assert min-degree >=3 on the
*four corner cell ids specifically* in addition to the global sweep.

## Finding B — BLOCK — The heightmap blob-seed placement is not a specified deterministic algorithm

**Acceptance criterion at risk:** #2 (byte-identical `WorldMap` across two runs) and
the GEO_GENERATOR_PLAN regeneration-determinism invariant.

§5 step 1 says blob seed-cell placement is, for non-Archipelago profiles, "sampled from
a distribution pulled toward `(0.5,0.5)`" and for Archipelago "spread uniformly". This
is a description of intent, not an algorithm. An unattended BUILD agent cannot implement
a deterministic function from "a distribution pulled toward the centre":

- No distribution is named (truncated Gaussian? rejection sampling? radius-biased
  uniform?), no parameters given (variance / pull strength), and no statement of how a
  continuous sample is mapped to a discrete cell id.
- Different reasonable implementations produce different `content_hash` values, so the
  determinism test passes within one build but the design does not pin the output —
  meaning two BUILD agents (or a re-implementation) silently diverge. The invariant is
  "same inputs -> byte-identical `WorldMap`", and that only holds if the algorithm itself
  is fixed by the spec, not just by whatever code happened to be written.
- The same gap applies, more mildly, to "BFS outward... multiplying amplitude by falloff
  `0.82..0.90` (jittered) per ring": the jitter draw order across rings/cells must be
  pinned (it is determined by the sorted `neighbors` BFS order — state that explicitly).

**Concrete fix:** §5 must state the exact placement algorithm. E.g.: "draw `cx,cy` from
`rng_for(seed,b\"terrain\")` as `0.5 + (u-0.5)*SPREAD` where `u` is two uniform draws and
`SPREAD = 0.35` (non-Archipelago) / `1.0` (Archipelago), clamp to `[0,1]`, then pick the
cell whose center is nearest `(cx,cy)`." Pin the per-ring falloff jitter to one named
uniform draw per BFS-visited cell, and state that BFS visits `neighbors[i]` in its
already-sorted order so visitation is deterministic.

## Finding C — WARN — The Archipelago ">=2 land components" branch of criterion #5 is too weak to catch a real failure

**Acceptance criterion at risk:** #5 (land coherence) — Archipelago branch.

For non-Archipelago profiles criterion #5 is a strong, well-formed check (largest
component >=85%). For Archipelago it degrades to "assert only >=2 land components exist".
That is nearly unfalsifiable: any heightmap that produces even one stray single-cell
island alongside one dominant mass passes — including the failure mode where Archipelago
*collapses into one continent* with a single noise cell detached, or the opposite mode
where it shatters into 200 one-cell specks. Neither is a real archipelago. The check
also says nothing about the largest component *not* dominating.

**Concrete fix:** Strengthen the Archipelago branch to bracket both ends: e.g. require
`3 <= component_count <= ~30` AND the largest land component is `< 60%` of all land (so
it is genuinely fragmented, not a continent-plus-speck). Tune the bounds after the
Phase-1 spike, but the criterion as written is not a meaningful machine guarantee.

---

Lessons consulted: 10; Guardrails relevant: none
