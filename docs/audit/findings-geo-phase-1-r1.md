# Adversary DESIGN review — geo-phase-1 — round 1

**Task:** geo-phase-1 (`docs/plans/2026-05-17-geo-phase-1.md`)
**Phase:** REVIEW (design) — cold-start AMAW Adversary
**Verdict:** REJECTED (2 BLOCK, 1 WARN)

---

## Finding 1 — BLOCK — Neighbour degree 3..=12 is not guaranteed by a jittered-grid Delaunay mesh

**Acceptance criterion at risk:** #4 (`neighbour degree in [3,12]` for every cell).

§4 step 4 builds adjacency from `delaunator::triangulate` edges, and §4's closing
paragraph claims "interior ~6, edges 4-5, corners 3 ... `JITTER <= 0.55` keeps the grid
topology intact so no cell drops below degree 3." This reasoning is unsound:

- Delaunay triangulation does NOT preserve grid topology. A jittered point gets
  exactly the neighbours its incident Delaunay triangles give it, which depends on the
  relative positions of jittered points, not on grid slots.
- A convex-hull corner cell has only the two hull edges plus whatever interior
  triangulation gives it. With `JITTER = 0.55` (half a cell width) a corner's expected
  inward neighbour can be pulled away or "shadowed" by a diagonal point, leaving the
  corner with degree 2. There is no proof — only an assertion — that this cannot
  happen for any of the >=3 fixture seeds x >=2 scales the determinism test will run.
- The upper bound 12 is equally unproven. A point jittered far into a sparse pocket
  can be a Delaunay neighbour of an arbitrary number of surrounding cells; for a
  jittered grid the empirical max degree is typically 8-10 but is NOT bounded at 12 by
  construction.

Because the invariant is regeneration-determinism, a single bad seed is not a flake —
it is a permanent, reproducible criterion-4 failure baked into that seed.

**Suggested fix:** Do not assert the bound — enforce or measure it.
Either (a) post-process the adjacency: drop the lowest-degree pathological hull cells
or merge degree-<3 cells, and document the actual observed max instead of hard-coding
12; or (b) change criterion 4 to test the realised [min,max] degree across all
fixtures and pick the band empirically after a spike, rather than pre-committing to
[3,12]; or (c) clamp jitter much lower for hull rows/cols, or add a border ring of
fixed (un-jittered) points so hull cells have deterministic minimum degree. Pick one
and write it into §4 with a stated guarantee, not a hope.

## Finding 2 — BLOCK — Cell-count formula is internally contradictory; the design gives two different answers

**Acceptance criterion at risk:** #3 (cell count within [1024,16384] and close to
`scale.target_cells()`).

The design specifies the mesh dimensions twice, inconsistently:

- §3 / §4 step 1: `cols = rows = round(sqrt(n))`, "all five scales land in
  [1024,16384]: 1024, 2025, 8190->90*91, 12321->111*111, 16384" — note `8190` and
  `8192` are conflated, and `90*91` is not `cols=rows`.
- §4 closing paragraph: a different formula — `cols = round(sqrt(n))`,
  `rows = round(n / cols)` — yielding Region 45->2025 and Continent 91->8281.

These are two different algorithms producing two different counts (e.g. Continent:
8190 vs 8281). An unattended BUILD agent cannot implement a spec that disagrees with
itself; whichever it picks, the other half of the document is now wrong, and the
"close to target" half of criterion 3 has no defined tolerance to check against.

**Suggested fix:** Delete one formula. State a single rule, e.g.
`cols = round(sqrt(n)); rows = round(n / cols); count = cols*rows`, then list the
resolved count for all five scales (Pocket/Region/Continent/SuperContinent/Megaplanet)
in one table, and add an explicit tolerance to criterion 3 (e.g. "within 5% of
`target_cells()`") so it is mechanically verifiable.

## Finding 3 — WARN — "One coherent continent" is unenforced; the land-fraction proxy cannot detect fragmentation

**Acceptance criterion at risk:** #5 (CLI emits a PNG showing "one coherent continent";
machine proxy: "land-fraction within 0.15 of target").

The only machine-checkable part of criterion 5 is land-fraction, which is orthogonal
to connectedness. The §5 blob heightmap places `k = clamp(count/380, 6, 40)` blobs
with a soft center-biased seed distribution — a probabilistic nudge, not a guarantee.
6-40 blobs can settle into multiple disconnected land masses while still hitting the
land-fraction target exactly, so the proxy passes while the visual criterion fails.
`Archipelago` is defined as disconnected, so "one coherent continent" cannot even be
a universal criterion. The determinism invariant makes any fragmented seed permanently
fragmented.

**Suggested fix:** Add a real coherence check to VERIFY: connected-components flood-fill
over land cells (the `neighbors` graph already exists), and assert the largest land
component holds >= X% of all land (e.g. >=85% for Island/Coastal/Inland; relax or skip
for Archipelago). Reword criterion 5 so the proxy is "largest land component >= X% of
land" rather than land-fraction, and make the "one continent" wording profile-conditional.

---

Lessons consulted: 10; Guardrails relevant: none
