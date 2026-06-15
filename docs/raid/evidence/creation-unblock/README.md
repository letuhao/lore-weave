# Creation-unblock RAID — scenario test evidence

The creation-unblock RAID existed because the World workspace dead-end (no way to
add a book or branch a what-if) slipped past unit tests. So the completion work is
covered by real **browser scenario tests** — both committed Playwright specs and a
live Playwright-MCP walkthrough.

## Committed e2e specs (`frontend/tests/e2e/specs/creation-unblock-*.spec.ts`)

Run: `cd frontend && npx playwright test creation-unblock` (against the `:5174`
image — rebuild it after FE changes; it is a baked prod nginx, not vite-dev).

| Spec | Flow | Asserts |
|---|---|---|
| `creation-unblock-world` | G1 populate + G4 rollups | workspace renders the populate CTAs + graph/timeline rollups; attach an existing book (BookPicker) + create one inline; what-if routes to the canon studio; a pre-seeded member book with a Work shows in the living tree |
| `creation-unblock-crosslink` | G3 cross-links | book Settings WorldPicker attaches + "Open in world" backlinks; knowledge project Overview backlinks to its book + world |
| `creation-unblock-onboarding` | G5 funnel | "Build a world" intent → /worlds → create → a USABLE workspace (populate CTAs present) |
| `creation-unblock-pickers` | G2 pickers | chat session settings shows the ProjectPicker combobox (W4 swap from the raw `<select>`); model-gated |
| `creation-unblock-divergence` | D-079 | a seeded discovered entity offers the inline "Anchor & override" button; clicking it runs the real C9 promote so the override input appears |

**Result:** `6 passed (9.0s)`.

## Live Playwright-MCP walkthrough (the screenshots here)

A logged-in browser walk of the core funnel, proving the dead-end is gone:

1. `01-onboarding-intent.png` — the onboarding intent fork ("Build a world" present).
2. `02-world-workspace.png` — the world workspace: **Add a book** + **Create a
   what-if** CTAs, the living-world tree (1 canon · 4 what-if), the **World graph**
   rollup (G4), and the **World timeline** rollup (D-WORLD-TIMELINE-ROLLUP) — all
   the affordances that were previously absent.
3. `03-add-book-modal.png` — the Add-a-book modal (Attach existing / Create new
   tabs + the BookPicker).
