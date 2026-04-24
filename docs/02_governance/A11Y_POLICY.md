# Accessibility (A11y) Policy

> **Status:** Policy — enforced at code review + automated CI gate
> **Applies to:** All user-facing frontends in LoreWeave (novel platform UI + LLM MMO RPG roleplay UI + admin tools user-visible surfaces)
> **Source:** Derived from CC-6 resolution ([LLM_MMO_RPG FEATURE_CATALOG CC-6](../03_planning/LLM_MMO_RPG/FEATURE_CATALOG.md) + CC-6-D1..D7 in [decisions/locked_decisions.md](../03_planning/LLM_MMO_RPG/decisions/locked_decisions.md))
> **Created:** 2026-04-23
> **Owner:** Tech Lead + Design Lead

---

## 1. Policy

All user-facing frontends MUST ship at **WCAG 2.2 AA** compliance. PRs introducing user-visible UI MUST pass automated axe-core checks and tick a "reviewed for a11y" box in the PR description. Major UI changes (new surfaces, redesigns) MUST pass manual screen-reader walkthrough before merge to `main`.

This is not optional. A11y is not a later pass.

## 2. Why

LoreWeave ships to a general audience — readers, writers, and (via the Living Worlds extension) players across the accessibility spectrum. Approximately 15 % of the global population has some form of disability; a meaningful subset will attempt to use the product. Beyond the ethical baseline:

- **Legal:** ADA (US), EAA (EU, 2025), AODA (Ontario) — increasingly mandatory for public products
- **Quality correlation:** products that pass WCAG typically have cleaner markup, better keyboard UX, and more robust i18n — benefits flow to all users
- **Retrofit cost:** a11y added after the fact almost always requires UI rewrites; this is exactly the anti-pattern flagged in V-2 (service split from V1, not refactor later)

The LLM MMO RPG extension amplifies a11y risk specifically:

- Real-time streaming LLM output (breaks naïve screen-reader consumption)
- Multi-stream UI (NPC narration / player say / system / whisper) increases cognitive load
- Color-coded signals (canonicality badges, status indicators) fail for color-blind users
- Multiverse + canon concept complexity requires cognitive scaffolding

This policy addresses those risks upstream.

## 3. WCAG 2.2 AA target (CC-6-D1)

We target **WCAG 2.2 Level AA** as the V1 shipping bar.

| Level | Interpretation | Our stance |
|---|---|---|
| A | Minimum legal baseline | Insufficient — not a target |
| **AA** | **Broadly accepted industry standard** | **V1 target** |
| AAA | Maximum conformance; some criteria mutually exclusive with design choices | Not a target; adopt criterion-by-criterion where cheap |

Reference: [WCAG 2.2 QuickRef](https://www.w3.org/WAI/WCAG22/quickref/)

Key WCAG 2.2 additions we care about: **2.4.11 Focus Not Obscured (Minimum)** · **2.5.7 Dragging Movements** · **2.5.8 Target Size (Minimum)** — 24×24 CSS pixel minimum per WCAG AA, but we apply 44×44 per §7 below.

## 4. Streaming text rendering (CC-6-D2)

Problem: LLM output streams char-by-char. Wired directly to an ARIA live region, screen readers announce every token — producing unusable noise.

Solution: **batch output to sentence boundaries** before announcing.

Rules:

- Streaming text renders into an `aria-live="polite"` region
- Batch granularity: **whichever comes first** — sentence boundary (`.`, `!`, `?`, `。`), every 500 ms, or end-of-stream
- Never `aria-live="assertive"` for narration (reserved for critical system alerts)
- Visual rendering can still be per-char (smooth streaming) while the a11y announcement batches

Implementation pattern (conceptual):

```tsx
<div aria-live="polite" aria-atomic="false">
  {batchedSentences.map(s => <span key={s.id}>{s.text}</span>)}
</div>
<div aria-hidden="true" className="visual-stream">
  {tokenStream}  {/* per-char visual only, not read */}
</div>
```

## 5. Multi-stream UI semantic markup (CC-6-D3)

Problem: NPC narration, player say, system action results, and world events all converge in session UI. A single scroll log of mixed streams is hostile to keyboard and screen-reader users — they can't tell who said what and can't skip irrelevant channels.

Solution: **Semantic channels + per-stream mute/subscribe.**

Rules:

- Each channel = distinct region with `role="log"` + unique `aria-label`
  - `aria-label="Narration"` for NPC + narrator output
  - `aria-label="Dialogue"` for player + NPC say
  - `aria-label="System"` for action results + errors
  - `aria-label="Whisper"` for private channels
- Channels rendered in distinct visual columns OR tabs (per user preference)
- User control: per-channel **mute** (hide + skip in screen reader announcement) and **subscribe** (announce; default for narration + dialogue)
- Keyboard shortcut: `Tab` cycles between channels; `Shift+Tab` reverses; `Space` on channel mutes it
- This is a UX win for all users, not just a11y — muting "System" during immersive narration is a common request

## 6. Color-independent signaling rule (CC-6-D4)

**Rule: any information conveyed by color MUST also be conveyed through a non-color channel.** No exceptions.

Applies to:

| Signal | Color alone ❌ | Color + non-color ✅ |
|---|---|---|
| `canon_attempt` badge | Green pill | 📖 Green pill + "Follows book" label |
| `divergent` badge | Yellow pill | 🌿 Yellow pill + "Alternate take" label |
| `pure_what_if` badge | Red pill | ❓ Red pill + "What-if scenario" label |
| "Hibernated" status | Gray-out only | 💤 Icon + "Hibernated" label + gray |
| "Near-cap" indicator | Red bar | 🔴 Icon + "Near full" text + red bar |
| Friend presence | Outlined avatar | Outlined avatar + `aria-label="{name} is in this timeline"` |
| Error state | Red border | ⚠ Icon + red border + error message text |

Screen-reader announcements for badges should state the meaning: *"Canonicality: follows book"* not *"canon attempt badge"*. Integrate with [`UI_COPY_STYLEGUIDE.md`](UI_COPY_STYLEGUIDE.md) terminology map.

## 7. Tap target minimum (CC-6-D5)

**All interactive elements: minimum 44 × 44 CSS pixels.**

- Source: existing LoreWeave mobile convention (carries into RPG UI)
- Exceeds WCAG 2.5.8 minimum (24 × 24) intentionally — LoreWeave is mobile-first
- Includes: buttons, icon-only controls, close buttons, avatar affordances, badge taps, per-turn action controls

Exceptions (require explicit design-lead signoff):
- Inline text links (follow text line-height)
- Dense tabular data where density is a UX requirement (but row itself remains 44 × 44)

Close buttons on overlays / modals / panels explicitly require square 44 × 44 targets (both `min-width` and `min-height`) — user memory notes this from prior mobile bug fix.

## 8. A11y mode toggle (CC-6-D6)

A **tier-independent** user preference — NOT gated by platform tier (M7-D2). A11y is a baseline, not a premium feature.

Settings panel exposes an "Accessibility" section with:

| Toggle | Effect when ON |
|---|---|
| **Reduced motion** | Disable streaming text animations, scene transitions, avatar motion; honor `prefers-reduced-motion` by default |
| **High contrast** | Dark-mode palette with higher contrast ratio; honor `prefers-contrast: more` by default |
| **Verbose screen-reader output** | Announce decorative elements (badges, avatars) in addition to primary content; useful for some SR users |
| **Simplified UI** | Hide decorative elements (friend avatars on browse cards, canonicality badges until actively queried, recent-activity timestamps); reduce cognitive load |
| **Default to terse voice mode** | Override C1-D1 "mixed" default with "terse" (less prose per turn — lower SR processing load) |
| **Keyboard-only mode** | Show keyboard shortcut overlay; `?` key opens shortcut reference |

- Toggles sticky per user account (stored in auth-service preferences, per M7-D4 pattern)
- System defaults from OS preferences where possible (`prefers-reduced-motion`, `prefers-contrast`)
- Individual toggles, not a single "a11y on/off" — different users need different subsets

## 9. Testing gate (CC-6-D7)

### 9.1 Automated — axe-core in CI

- Every PR touching frontend runs axe-core against affected components
- Violations at `serious` or `critical` level **block merge**
- `moderate` level surfaces in PR comment but does not block (author decides)
- Coverage goal: 100 % of user-facing pages + key component combinations

### 9.2 Manual — screen-reader walkthrough

- Required for: new top-level pages, redesigned session UI, new user-facing flows (onboarding, discovery, canonization UI, admin surfaces exposed to authors)
- Test matrix minimum: NVDA on Windows + VoiceOver on macOS + VoiceOver on iOS + TalkBack on Android
- Walkthrough captured as video or signed-off checklist; stored in QA archive
- Cadence: per major release, not per PR

### 9.3 Periodic external audit

- Annual third-party WCAG audit (once platform-mode launches)
- Findings feed fix backlog; critical findings block next release

## 10. Integration with other policies

| Policy | How A11y interacts |
|---|---|
| [`UI_COPY_STYLEGUIDE.md`](UI_COPY_STYLEGUIDE.md) | Screen reader reads user-facing terms (M7-D1 map). Power-user labels hidden from SR unless explicitly enabled (verbose mode). Copy clarity = cognitive a11y. |
| [`ADMIN_ACTION_POLICY.md`](ADMIN_ACTION_POLICY.md) | Admin tools are user-facing for authors/ops; WCAG AA applies. Destructive-action confirmation dialogs must be keyboard-accessible. |
| [`CROSS_INSTANCE_DATA_ACCESS_POLICY.md`](CROSS_INSTANCE_DATA_ACCESS_POLICY.md) | No direct a11y interaction. |
| [`05_LLM_SAFETY_LAYER.md`](../03_planning/LLM_MMO_RPG/05_LLM_SAFETY_LAYER.md) | Output filter (A6-D4) must not strip aria attributes. 3-intent classifier (A5-D1) preserves keyboard-native command path. |
| [`LLM_MMO_TESTING_STRATEGY.md`](../05_qa/LLM_MMO_TESTING_STRATEGY.md) | G1 unit test scenarios include a11y assertions where applicable; G3 user reports include "accessibility issue" category. |

## 11. Update process

Changes to this policy require:

1. PR with justification (new WCAG version, user feedback data, legal requirement change)
2. Design Lead + Tech Lead signoff
3. Migration plan for any frontend affected (e.g., if we raise tap target from 44 × 44 to 48 × 48)
4. Update CC-6 row in [FEATURE_CATALOG.md](../03_planning/LLM_MMO_RPG/FEATURE_CATALOG.md) and CC-6-D* rows in OPEN_DECISIONS if decisions change

Never lower the bar without explicit sign-off + documented rationale.

## 12. Residual OPEN (V1 playtest / external measurement)

- **Per-locale screen-reader pronunciation** for proper nouns (character names, place names) — cannot design upfront; collect during V1 QA per locale
- **Cognitive accessibility for multiverse concept** — M7 progressive disclosure helps; refine based on real user feedback
- **Voice-only / TTS narrator mode** (read narration aloud in-app) — V2+ nice-to-have, beyond WCAG 2.2 AA baseline

These do not block V1; they are continuous-improvement items.

## 13. References

- [WCAG 2.2 QuickRef](https://www.w3.org/WAI/WCAG22/quickref/)
- [WAI-ARIA Authoring Practices 1.2](https://www.w3.org/WAI/ARIA/apg/)
- [axe-core documentation](https://github.com/dequelabs/axe-core)
- [Mozilla MDN ARIA reference](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA)
- Internal: [`UI_COPY_STYLEGUIDE.md`](UI_COPY_STYLEGUIDE.md) (terminology consistency)
- Internal: CC-6 row in [`FEATURE_CATALOG.md`](../03_planning/LLM_MMO_RPG/FEATURE_CATALOG.md)
- Internal: CC-6-D1..D7 in [`decisions/locked_decisions.md`](../03_planning/LLM_MMO_RPG/decisions/locked_decisions.md)
