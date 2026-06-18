# Cycle 22 — Intent-branching onboarding — Playwright live smoke

**Account:** claude-test@loreweave.dev · FE :5174 + gateway :3123 (both /health 200).

`playwright smoke: each of 4 intents (Write/Build-a-world/Translate/Explore) lands in the correct surface`

## First-run gating (server-side seen-flag via /v1/me/preferences)
1. Logged in → reset `hasSeenOnboarding=false` via `PATCH /v1/me/preferences` (status 200 — server-side, NOT localStorage).
2. Navigated to `/` → **redirected to `/onboarding`** and rendered the 4-intent fork
   ("What do you want to do?"). Proves first-run gating fires off the server flag.
   Screenshot: `intent-fork-first-run.png`

## Each of the 4 intents lands on the correct surface + container
| Intent | Action | Landed URL (correct surface) | Screenshot |
|---|---|---|---|
| Write | click Write card | `/books` (book workspace container) | `intent-write-books.png` |
| Build a world | click Build-a-world card | `/worlds` (C20/C21 world container) | `intent-world-worlds.png` |
| Translate | click Translate card | `/books?intent=translate` — tailored: renders the "Pick a book to translate…" hint (route-only, no new translator flow) | `intent-translate-books.png` |
| Explore | click Explore card | `/knowledge/projects` (read-only knowledge/graph browse) | `intent-explore-knowledge.png` |

Intents 2–4 were driven via the **re-entry route `/onboarding/new`** ("Start something
new" — sidebar affordance + forceShow), which renders the fork even after the seen-flag
is set — proving re-entry without forcing the fork every session.

## Seen-flag persisted server-side → not re-onboarded every session
After picking Write (which marked seen=true), navigated to `/onboarding` (the gate,
forceShow=false) → **redirected straight to `/books`** (fork NOT re-shown). The flag was
written through to the server, so a returning user / another device skips the fork.

0 console errors across all navigations.
