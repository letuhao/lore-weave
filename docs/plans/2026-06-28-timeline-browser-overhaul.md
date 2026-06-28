# Plan — #12 Timeline GUI quality + browser consistency (L, multi-part)

Date: 2026-06-28 · branch `fix/critical-ux-bugs`

## Finding (verified in code)
The timeline is NOT low-quality in capability — `TimelineTab` already has: project filter,
narrative/chronological sort + direction, entity filter, chronological + ISO-date ranges,
pagination, expandable rows, loading/error/empty states; `TimelineEventRow` already shows
order, importance, title (localized + source-marker), chapter, participant chips, and on
expand the summary + all participants + source_types. The user's "low quality / scattered"
(all 4 aspects selected) is mostly **consistency + a few missing affordances**, not a broken UI.

The genuine gaps, by the 4 aspects the user picked:
1. **Inconsistent look across browsers** — Timeline, Entities (`EntityListBrowser`), Evidence
   (`RawDrawersTab`) each implement their own chrome. No shared shell.
2. **Rows lack info** — partly already rich; the in-story **time_cue** was only in the expanded
   detail (DONE this commit — surfaced on the collapsed row).
3. **Missing text search** — the BE timeline endpoint (`timeline.py`) has NO `q`/search param;
   it's a Neo4j Cypher query. Needs a BE change (Cypher `toLower(...) CONTAINS toLower($q)` over
   title/summary, interacting with the reader-language localization) + FE search box.
4. **Visual polish / density** — page-size control, spacing, mobile.

## Parts (each its own commit)
- **Part 1 (DONE, this commit):** surface `time_cue` on the collapsed `TimelineEventRow`
  (localized + source-marker) — the cheapest, highest-signal row-richness win (#2).
- **Part 2 (BE+FE):** timeline **text search** (#3) — add a `q` Query param to `timeline.py`,
  extend the Cypher to filter on title/summary (case-insensitive CONTAINS); FE search box in
  `TimelineTab` (debounced, resets offset). Mind the localization: search the SOURCE text
  (title/summary) so it's deterministic regardless of reader language. ~M cross-layer.
- **Part 3 (FE):** extract a shared **BrowserShell** primitive (header + search slot + filter
  slot + content + footer/pagination) as CONTROLLED, adopt in `TimelineTab` first (then Entities
  / Evidence in follow-ups) for consistency (#1) + polish (#4). ~M FE refactor; keep existing
  leaves unchanged (memory: extract-as-controlled).

## Out of scope / deferred
- Porting EVERY browser onto the shell at once = XL → adopt incrementally (timeline first).
- Scene/block-level event provenance = the separate #15 (L/XL).

## Verify
- FE knowledge suite green per part; tsc clean; 4-locale parity.
- Part 2 needs a knowledge-service live smoke (Neo4j search) or a deferred row.
