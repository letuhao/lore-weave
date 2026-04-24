# UI Copy Style Guide

> **Status:** Policy — enforced at code review on user-facing UI changes
> **Applies to:** All user-facing strings in the frontend (Reader, Player, Author tiers) — component labels, tooltips, modals, error messages, emails
> **Source:** Derived from [§9.6 in 03_multiverse/06_M_C_resolutions.md](../03_planning/LLM_MMO_RPG/03_multiverse/06_M_C_resolutions.md)
> **Created:** 2026-04-23
> **Owner:** Tech Lead + Design Lead

---

## 1. Policy

User-facing copy MUST follow the terminology map and phrasing patterns below. Internal design-doc terms (e.g., "reality", "aggregate", "projection", "fork point") do NOT appear in default UI copy. Power-user labels are only surfaced in author tooling, admin surfaces, and developer documentation.

PRs that add or modify user-facing strings MUST tick a **"copy reviewed against styleguide"** checkbox; reviewers block merges that leak internal terminology into default UI paths.

## 2. Why

The LoreWeave multiverse model is sophisticated: peer realities, 4-layer canon, snapshot fork, event sourcing. Exposing these concepts unfiltered to casual readers causes immediate cognitive overload and churn — this was identified as risk **M7 (Concept complexity for users)** in [§M7 in 01_problems/M_multiverse_specific.md](../03_planning/LLM_MMO_RPG/01_problems/M_multiverse_specific.md).

The mitigation is **progressive disclosure** — keep the complexity available to power users (authors, admins) while rendering it invisible to readers. This style guide is the copy-layer enforcement of that principle.

## 3. Terminology map

Default UI uses user-facing terms. Power-user labels appear only in author tooling, admin ops, and developer docs.

| Internal (design doc / code) | User-facing (default UI) | Power-user label (optional hover/toggle) |
|---|---|---|
| reality | **timeline** *(default)* / **server** *(gaming context)* | reality |
| book | **world** *(immersive)* / **book** *(literary)* | book |
| fork | "explore another version" / "branch" | snapshot fork |
| canonicality_hint | "follows the book" / "alternate take" / "what-if" | canon_attempt / divergent / pure_what_if |
| L1 axiomatic canon | "world law" *(unchangeable)* | L1 axiomatic canon |
| L2 seeded canon | "starting facts" | L2 seeded canon |
| L3 reality-local canon | "story event" / "what happened" | L3 reality-local canon |
| L4 flexible state | *(not user-visible)* | L4 runtime state |
| NPC | **character** | NPC |
| PC | **your character** | PC |
| event sourcing | "the world remembers" | event sourcing |
| aggregate / projection | *(never surfaced)* | aggregate / projection |

## 4. Phrasing patterns

### Do

- ✅ "Step inside Alice's world"
- ✅ "Explore another version of this world"
- ✅ "Continue your story"
- ✅ "Your character remembers"
- ✅ "The world remembers what happened here"
- ✅ "This timeline follows the book closely"
- ✅ "Alice is currently playing in this timeline"
- ✅ "Start a fresh version of this world"

### Don't

- ❌ "Join reality R_α"
- ❌ "Fork a reality"
- ❌ "Resume session"
- ❌ "Per-PC memory slot"
- ❌ "Event-sourced world state"
- ❌ "canon_attempt hint"
- ❌ "Aggregate ID"
- ❌ "Projection rebuild"

## 5. Tier-aware defaults

The 3-tier user model (see [§9.6.2 in 03_multiverse/06_M_C_resolutions.md](../03_planning/LLM_MMO_RPG/03_multiverse/06_M_C_resolutions.md)) sets default copy complexity:

| Tier | Copy default |
|---|---|
| 🧍 Reader / Casual | User-facing terms only. No badges, no canonicality, no tier labels visible. Focus on the story. |
| 🧙 Player | User-facing terms remain default; power-user labels appear on hover tooltips when requested. |
| ✍️ Author / Creator | User-facing terms still default in UI, but author-facing tools (canonicality_hint setter, world-rule editor, canonization flow) may use full terminology. |

Admin and developer surfaces are exempt — they use internal terminology freely.

## 6. Review gate

Every PR that touches user-facing strings MUST include in its description:

> **Copy review:** [x] reviewed against `docs/02_governance/UI_COPY_STYLEGUIDE.md`

Reviewers check:

1. No internal terms leaked into default UI (see §3 table)
2. Phrasing patterns followed (see §4)
3. Tier-appropriate defaults (see §5)
4. i18n keys exist in EN + VI minimum (V1 locales)
5. Tooltips <100 chars default

Exceptions (internal terminology permitted without review):
- Developer tooling: `services/admin-cli/`, admin dashboards
- Author tooling: canonicality_hint setter, World Rules editor, canonization UI (DF3)
- Log messages, error codes (unless user-visible)
- Internal API responses

## 7. i18n requirements

- All user-facing strings routed through `i18next` (novel-platform infrastructure, reused)
- V1 ships EN + VI minimum
- Tooltip strings <100 chars default; exceptions require design sign-off
- Pluralization uses i18next plural rules, not string concatenation

## 8. Contextual tooltip library

Seven tooltips locked in [§9.6.5 in 03_multiverse/06_M_C_resolutions.md](../03_planning/LLM_MMO_RPG/03_multiverse/06_M_C_resolutions.md) (M7-D5):

| Element | Tooltip (EN) |
|---|---|
| `canon_attempt` badge | "This timeline follows the book closely" |
| `divergent` badge | "This timeline diverges from the book" |
| `pure_what_if` badge | "What-if scenario — a hypothetical version" |
| "Create new timeline" CTA | "Start a fresh version of this world. You can begin from the book or from a specific moment in an existing timeline." |
| Friend avatar on browse card | "Your friend {name} is currently playing in this timeline" |
| "Hibernated" badge | "No players for 30 days. Read-only; start a new session to wake it up." |
| "Forked from R_α at event 48" | "Branched off from another timeline at a specific story moment. They share history up to that point." |

VI translations tracked in `frontend/src/i18n/locales/vi.json` under the same keys.

## 9. Updating this doc

Changes to the terminology map (§3) or phrasing patterns (§4) require:

1. PR with justification (user research data, UX feedback, locale issue)
2. Design Lead + Tech Lead sign-off
3. Update corresponding §9.6 in [03_multiverse/06_M_C_resolutions.md](../03_planning/LLM_MMO_RPG/03_multiverse/06_M_C_resolutions.md) + [decisions/locked_decisions.md](../03_planning/LLM_MMO_RPG/decisions/locked_decisions.md) M7-D1/D4 rows
4. Migration plan for any affected live strings (i18n key rename, deprecation schedule)

## 10. References

- [03_multiverse/06_M_C_resolutions.md — §9.6 Progressive disclosure](../03_planning/LLM_MMO_RPG/03_multiverse/06_M_C_resolutions.md)
- [01_problems/M_multiverse_specific.md — §M7 Concept complexity](../03_planning/LLM_MMO_RPG/01_problems/M_multiverse_specific.md)
- [decisions/locked_decisions.md — M7-D1 through M7-D5](../03_planning/LLM_MMO_RPG/decisions/locked_decisions.md)
- [ADMIN_ACTION_POLICY.md](ADMIN_ACTION_POLICY.md) — sibling governance doc pattern
