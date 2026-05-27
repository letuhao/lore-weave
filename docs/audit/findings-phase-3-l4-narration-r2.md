# Adversary findings — Phase 3 L4 regional-narration spec, round 2

**Verdict:** APPROVED_WITH_WARNINGS — round-1 BLOCK-1 + WARN-2 + WARN-3 all
genuinely resolved by the revised spec text. 3 new WARNs, all spec
under-specifications (no captured-lesson hole re-opened at BLOCK severity).
**All 3 resolved in the spec** after this round (D1/D3/D6/D7 + AC-6/AC-11).

## WARN-1 — out-of-subset guard pinned only on the error side, not the accept side

D1 pinned `errors.retain(... subset_ids ...)` but not the accept-side
`subset_ids.contains` check; D3's R-list had no unknown-zone rule, so an
out-of-subset narration in a later attempt could be silently *accepted*,
overwriting saved work. **Fixed:** D1 Hole-3 bullet now pins both sides
(accept iff `zone_id ∈ subset` AND no error); D3 R1 now flags `UnknownZoneId`.

## WARN-2 — all-digit token eligibility undefined in key-phrase extraction

D6 dropped short tokens + stopwords but left bare numbers (`2026`) eligible —
two implementers would diverge. **Fixed:** D6 now drops all-digit tokens (a
kept token must contain ≥1 `[a-z]`); AC-6 asserts it.

## WARN-3 — `ZoneNarrationInput` shape + the L3→L4 join unspecified

D7 said "build `ZoneNarrationInput`s" without a field list or the
`L3Classification.obj_id → L3Placeholder.zone_id` join needed to recover each
zone's objects; `terrain` population (D4's template slot) was unpinned →
risk of a `"...across  terrain"` double-space stub invisible to every AC.
**Fixed:** D7 now pins `ZoneNarrationInput { zone_id, terrain, l3_objects }`,
the join, terrain always-populated from `ZoneRuntime`, and the all-fallback
zone case; AC-11 added.

Captured rules: read pre-loaded (4 lessons incl. the L3 retry-loop holes); Guardrails relevant: none
