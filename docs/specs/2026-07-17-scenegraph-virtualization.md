# Scene-Graph Virtualization (S5-B4 §2-bar #9 scale) — spec

> Origin: S5 `/review-impl` (D-S5-SCENEGRAPH-VIRTUALIZE). `SceneGraphCanvas` (the what-if
> canvas producer) renders EVERY scene node + edge as SVG with no windowing, so at a
> book-scale outline (~10k scenes) it emits thousands of DOM nodes and pan/zoom janks.
> This is the one §2-bar-#9 gap S5 could not close inline — it needs a real design, below.

## 1 · Problem

`SceneGraphCanvas` → `GraphCanvas<GraphEdge>` renders `nodeIds.map(renderNode)` and
`edges.map(renderEdge)` into one `<svg>`, all nodes/edges always in the DOM. Auto-layout
(`autoLayout(scenes)`) lays every scene on a 2-D plane; the SVG viewBox pans/zooms over
it. At 10k scenes: ~10k `<SceneNode>` groups + N edges mounted at once → slow first paint,
janky drag, high memory. The what-if branch overlay (dashed alt nodes/edges) is small and
not the problem; the CANON node/edge set is.

## 2 · Design — viewport culling (render only what's visible)

Keep the layout (cheap: it's math over positions, not DOM). Cull the RENDER: mount only
the nodes whose laid-out box intersects the current viewport rect (+ a margin), and only
the edges with ≥1 rendered endpoint.

1. **Expose the viewport rect from GraphCanvas.** GraphCanvas owns pan/zoom (the SVG
   viewBox / transform). Lift the current `{x, y, w, h}` world-rect into state (throttled
   on pan/zoom via `requestAnimationFrame`, not every wheel tick).
2. **Cull nodes.** `visibleNodeIds = allNodeIds.filter(id => intersects(positions[id],
   viewportRect.expandedBy(MARGIN)))`. MARGIN ≈ one viewport (so a node just off-screen is
   pre-mounted before it pans in — no pop-in). ALWAYS include: the dragged node, the
   selected node(s), and every what-if alt node (the branch overlay is always small).
3. **Cull edges.** Render an edge iff BOTH endpoints are in `visibleNodeIds` (an edge to an
   off-screen node draws to nowhere; acceptable — the existing code already filters edges to
   in-graph endpoints). Keep every what-if branch edge (small set).
4. **Stable keys.** Node/edge keys stay `id`-based so React reuses DOM across cull changes
   (no remount storm on pan).
5. **The extent / scrollbars.** The canvas scroll extent still comes from the FULL layout
   (so the scrollbar reflects the whole graph), NOT the culled set — cull affects only which
   children mount, never the scroll area.

## 3 · Interaction correctness (the traps)

- **Drag:** the dragged node MUST stay mounted even if the pointer leaves the viewport
  mid-drag → always include the active-drag id in `visibleNodeIds` until pointer-up.
- **Link-create selection:** a selected scene (pending a link) must stay mounted so the
  ring + the two-click flow survive a pan → include `selected[]`.
- **What-if branch:** alt nodes/edges + the anchor scene always render (they are the point of
  the canvas and are few) — never culled.
- **Auto-scroll-to on open (↗):** `openScene` navigates away (no canvas concern); a future
  "focus a node on the canvas" (plan-rail `planFocusNode`) must first pan the viewport so the
  target is in the culled set, THEN it mounts — order matters.

## 4 · Where it lives

`GraphCanvas` (features/composition/components/GraphCanvas.tsx) grows the viewport-rect state
+ the cull filter (it already owns pan/zoom + the node/edge render loop, so the cull belongs
there, not in every consumer). `SceneGraphCanvas` passes the always-include set (dragged /
selected / what-if ids). No API change for other GraphCanvas consumers (place-graph, plan-hub)
— they benefit for free; the cull is a pure perf transparency (same nodes, fewer mounted).

## 5 · Acceptance

- A 10k-node fixture mounts only ~viewport-worth of `<SceneNode>` (assert the rendered count
  is O(viewport), not O(total)) — a jsdom test counting mounted nodes at a given viewport rect.
- Pan/zoom stays smooth (manual + a perf trace); dragging a node off-screen and back keeps it.
- The what-if branch overlay always renders; link-create + selection survive a pan.
- Existing SceneGraphCanvas tests stay green.

## 6 · Effort / sequencing

M (a focused GraphCanvas refactor + a cull test). Not blocked — buildable now; deferred from
S5 only because it's a graph-rendering refactor of its own, not part of the divergence panel.
Owner: whoever next touches the what-if canvas / plan-hub graph (S5 or S2/S3 graph work).
