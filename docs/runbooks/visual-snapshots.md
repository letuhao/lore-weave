# Runbook — Cross-platform visual snapshot bake

**Scope:** Playwright visual regression goldens for the `frontend-game`
viewer (chunk-Q5 zone-role overlay, chunk-Q6 chunk-C/D decoration-family
breakdown, future visual specs).

**Audience:** developer about to land a UI change that affects rendered
output (new UI section, font choice, color tweak, dependency update
touching Chromium).

---

## Why this runbook exists

Playwright snapshot files are platform-suffixed by the test runner:
`<test-id>-chromium-win32.png`, `<test-id>-chromium-linux.png`,
`<test-id>-chromium-darwin.png`. The repo's existing PNGs were baked on
Windows-x86_64 during chunk-Q6 chunk-C/D dev because the developer
machine was Windows. The Ubuntu CI runner used by
`.github/workflows/game-subtree-ci.yml` job `frontend-game-e2e-with-backend`
can't verify against WIN32 baselines (anti-aliasing + font rendering
differs by more than the 2% `maxDiffPixelRatio` tolerance).

The Linux baselines need to be **baked once on Linux**, then committed
to the repo so CI can verify against them. This runbook documents that
bake flow.

---

## When to run the bake

Trigger `Bake Linux visual snapshots` (GitHub UI → Actions → workflow
name → Run workflow) when:

- You added a new `*.spec.ts` file that uses `toHaveScreenshot(...)`
- You changed UI rendering (new section in `MetadataPanel`, font
  weight tweak, color swatch addition)
- A Chromium version bump landed in `pnpm-lock.yaml` (Playwright
  bundles the browser per-version)
- The existing chromium-linux PNGs failed verification in
  `frontend-game-e2e-with-backend` AND you've confirmed the diff is
  intentional (e.g. you wanted the rendering to change)

**Do NOT run** the bake when:

- A backend regression made decorations stop placing (the goldens
  would silently capture the broken state — fix backend FIRST, then
  re-bake). This is the chunk-D `feedback_verify_environment_before_diagnosis`
  lesson — verify your environment before treating a snapshot mismatch
  as a "needs re-bake" signal.

---

## How to bake

1. Push your branch with the UI change.
2. GitHub UI → **Actions** tab → left sidebar → **Bake Linux visual snapshots**.
3. Top-right → **Run workflow** dropdown → select your branch → **Run workflow**.
4. The workflow takes ~5-8 minutes:
   - Checkout (fetch-depth: 0 — needed for the auto-commit)
   - Cargo build tilemap-service (release) + Rust cache
   - pnpm install (cached)
   - Playwright browser install (`chromium` only by default —
     change via the `browsers` input if you need firefox/webkit too)
   - Start tilemap-service in background, wait for `/livez`
   - `playwright test --update-snapshots all --project=chromium`
   - `stefanzweifel/git-auto-commit-action` commits new/changed
     `frontend-game/e2e/**/*.png` files back to your branch
5. Pull the auto-commit locally: `git pull`.
6. **Review the auto-committed PNGs** before merging. Treat the
   commit like any other reviewable change — visual diffs caught by
   the bake are the same as code diffs caught by `cargo test`.

The auto-commit's message is:

```
ci(visual-snapshots): bake Linux PNG goldens via GitHub Actions
```

so it's easy to spot in `git log`.

---

## Coexistence with Windows baselines

Playwright's per-platform suffixing means win32 and linux PNGs live
side-by-side in the same snapshot directory:

```
frontend-game/e2e/decoration-family-visual-regression.spec.ts-snapshots/
├── decoration-family-breakdown-collapsed-chromium-linux.png   # CI verifier
├── decoration-family-breakdown-collapsed-chromium-win32.png   # local Windows dev
├── decoration-family-breakdown-expanded-chromium-linux.png
└── decoration-family-breakdown-expanded-chromium-win32.png
```

No conflict — each platform reads its own file. Windows developers see
their local goldens verify locally; CI verifies the Linux goldens. The
two sets can drift slightly (they will, given font/AA differences),
but both serve the same regression-catching purpose for their platform.

---

## Reviewing snapshot diffs

The auto-commit lands in your PR. Look at the PNG diff (GitHub renders
PNG side-by-side or use `git diff --stat` to scope which files
changed). Questions to ask:

1. **Is the visible change consistent with the code I shipped?** A
   `<DecorationFamilyBreakdown>` section addition should produce a
   bigger expanded-state PNG; a font-weight change should affect the
   text rows uniformly; an unrelated change is a red flag.
2. **Did unrelated goldens change?** If you only edited MetadataPanel
   but the zone-role goldens also changed, something else shifted —
   investigate (Chromium update? CSS cascade? viewport size drift?).
3. **Do the linux PNGs differ wildly from the win32 PNGs of the
   same test?** Some drift is expected (Cantarell vs Segoe UI); >40%
   pixel change suggests a font-stack issue worth chasing.

---

## Troubleshooting

### "auto-commit-action permission denied"

Branch protection rules can block the `GITHUB_TOKEN` from pushing.
Either:

- Disable branch protection temporarily (NOT recommended — defeats the
  reviewability guarantee).
- Replace the action with `peter-evans/create-pull-request@v6` so the
  bake opens a PR instead of pushing directly. The reviewer of the
  bake-PR is then the gatekeeper.

### "/livez never came up"

The cargo build succeeded but the binary failed to start. Common
causes:
- `TILEMAP_HTTP_BIND=0.0.0.0:8220` conflicts with another step's port
  binding — check the workflow log.
- `LOREWEAVE_INTERNAL_TOKEN` env not set — but the workflow hard-codes
  `dev_internal_token` so this should never happen.

Re-run the workflow; if it persistently fails, run `cargo run --release
--bin tilemap-service -- serve` in a docker-ubuntu locally to reproduce.

### "snapshots updated for win32 too"

The workflow uses `actions/checkout@v4` which preserves whatever's in
the branch. If you previously had a win32 baseline that's now stale
(e.g. you removed the spec), the bake won't delete it — it only
WRITES the linux baseline. Clean up stale win32 PNGs manually in a
separate commit.

---

## Pairs with

- [`feedback_verify_environment_before_diagnosis`](../../memory/...)
  — verify backend isn't stale BEFORE concluding a snapshot mismatch
  means re-bake.
- [`feedback_visual_goldens_must_gate_on_content`](../../memory/...)
  — every `toHaveScreenshot(...)` must be preceded by a content
  assertion so the bake can't silently capture a wrong-fixture state.
