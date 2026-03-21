# LoreWeave Module 01 GUI Visual Improvement Plan

## Document Metadata

- Document ID: LW-M01-23
- Version: 1.2.0
- Status: Active
- Owner: Product Manager + Execution Authority
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Module 01 identity UI visual improvement plan. **Approved stack:** Tailwind CSS, shadcn/ui (Radix UI), lucide-react, react-hook-form, and zod—aligned with wireframes (20) and FE design (19); no API contract changes.

## Change History


| Version | Date       | Change                                            | Author    |
| ------- | ---------- | ------------------------------------------------- | --------- |
| 1.2.0   | 2026-03-21 | §4 split: historical vs current snapshot; §12 notes smoke vs formal acceptance; pointer to `MODULE01_DEFERRED_FOLLOWUPS.md` | Assistant |
| 1.1.0   | 2026-03-21 | Decision Authority approved stack: Tailwind + shadcn/ui + Radix + lucide-react + react-hook-form + zod; status Active | Assistant |
| 1.0.0   | 2026-03-21 | Initial GUI improvement and library strategy plan | Assistant |


## 1) Purpose and scope

Improve **visual quality, consistency, and usability** of the Module 01 identity UI (`frontend/`: register, login, verify, forgot/reset, profile, security, navigation) without changing **API behavior** or **contract paths** under `contracts/api/identity/v1/`.

Implementation work **may proceed** under this baseline; track concrete tasks in the execution backlog / PRs.

## 2) Monorepo alignment (authority)

- Implementation lives under `frontend/` per `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`.
- All screens remain traceable to `12_MODULE01_API_CONTRACT_DRAFT.md` and the governed OpenAPI artifact.
- Gateway and auth-service are **unchanged** by this plan except for any future need to serve static assets (out of scope here).

## 3) Traceability matrix


| Screen / area   | Wireframe blocks & states (`20`) | FE architecture (`19`) | User journeys (`13`) |
| --------------- | -------------------------------- | ---------------------- | -------------------- |
| Register        | 2.1                              | identity/screens       | Registration flow    |
| Login           | 2.2                              | identity/screens       | Login flow           |
| Verify email    | 2.3                              | identity/screens       | Verification flow    |
| Forgot / Reset  | 2.4                              | identity/screens       | Reset flow           |
| Profile         | 2.5                              | identity/screens       | Authenticated area   |
| Security prefs  | 2.5                              | identity/screens       | Authenticated area   |
| Global nav/home | 4 (navigation)                   | layout / shell         | Cross-cutting        |


## 4) Current state

### 4.1) Historical baseline (pre–GUI refresh)

Before the approved stack rollout, the Module 01 UI used:

- **Global styling** in `frontend/src/styles.css`: minimal tokens, system font, single `.layout` card pattern.
- **Per-page** React components under `frontend/src/pages/`: duplicated structure, inline nav, limited loading/empty/error differentiation.
- **No shared shell** (header, consistent spacing scale, or component primitives).

### 4.2) Implementation snapshot (2026-03-21)

- **Stack in repo:** Tailwind CSS, shadcn/ui (Radix), lucide-react, react-hook-form, zod — per §5.3; global CSS via `frontend/src/index.css`; shared **AppLayout** / **AppNav**; screens under `frontend/src/pages/` migrated to the new primitives.
- **Automated checks:** `npm test` and `npm run build` (and Docker frontend image build) remain required quality gates.
- **Manual verification:** **Smoke test** (register, login, profile/navigation) completed on dev/local after the refresh. **Formal acceptance** scenarios and evidence per `14_MODULE01_ACCEPTANCE_TEST_PLAN.md` are **deferred**; backlog in `docs/implementation/MODULE01_DEFERRED_FOLLOWUPS.md` (LW-IMPL-M01-01).

## 5) Strategy: use existing themes / component libraries

**Do not** rebuild low-level primitives (buttons, inputs, dialogs, toasts, focus rings) from scratch in plain CSS for Module 01.

Adopt **one** primary React + TypeScript + Vite–compatible **component system** (or Tailwind + headless + copied components) so that:

- accessibility behaviors (focus, keyboard, ARIA) come from maintained primitives where possible;
- visual consistency is enforced via the library’s **theme / token** layer;
- future modules can reuse the same shell and tokens.

### 5.1 Market reference (2024–2026)

Typical stacks for React/TS apps that are **form-heavy** (auth, settings):


| Direction                   | Typical stack                                                         | Strengths                                                                                                    | Constraints                                                                                        |
| --------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| **A — “New stack”**         | **Tailwind CSS** + **shadcn/ui** (on **Radix UI**) + **lucide-react** | Very common for new Vite apps; components live in repo; Radix handles a11y patterns; theme via CSS variables | Requires Tailwind pipeline; document `tailwind.config` / `components.json` in implementation tasks |
| **B — All-in-one**          | **Mantine** (core, hooks, forms, notifications)                       | Fast path to polished UI; strong forms                                                                       | Larger baseline bundle unless tree-shaken carefully; default “Mantine look” unless themed          |
| **C — Enterprise Material** | **MUI (Material UI)**                                                 | Large ecosystem; mature theming                                                                              | Heavier bundle; strong Material visual language                                                    |
| **D — Ant Design**          | **antd**                                                              | Familiar in many enterprise teams (especially Asia)                                                          | Opinionated; heavier customization cost for distinct branding                                      |


### 5.2 Recommended decision order (for Execution / Decision Authority)

1. **Preferred (default recommendation):** **Tailwind CSS + shadcn/ui + Radix + lucide-react**, with **react-hook-form** + **zod** for forms (common industry pairing).
2. **Alternative (fastest ship, less Tailwind setup):** **Mantine** (use current stable major at implementation time).
3. **Alternative (Material-aligned orgs):** **MUI**.

### 5.3 Approved UI stack (2026-03-21)

**Decision Authority** selected the **preferred (A)** option. Implementation SHALL use:

| Layer | Technology |
| ----- | ---------- |
| Styling | **Tailwind CSS** |
| Components | **shadcn/ui** (patterns; components copied into the repo) |
| Primitives / a11y | **Radix UI** (via shadcn/ui) |
| Icons | **lucide-react** |
| Forms | **react-hook-form** |
| Schema / validation | **zod** (with `@hookform/resolvers` for integration, when added) |

**Not in scope for this refresh:** Mantine, MUI, or antd as primary dependencies (unless a future ADR revisits the decision).

Implementation steps (for engineers): initialize Tailwind for Vite; run shadcn/ui CLI (`npx shadcn@latest init`) with defaults compatible with the repo; add only needed components (Button, Input, Label, Card, Alert, etc.); migrate screens incrementally per section 11.

### 5.4 Selection criteria (must be recorded in implementation PR / ADR)

- **Bundle size** after `vite build` (compare before/after; set a team budget if needed).
- **Accessibility**: keyboard, focus visibility, semantic structure; prefer primitives with proven patterns (e.g. Radix).
- **License**: MIT or equivalent compatible with project policy.
- **TypeScript** and **Vite** first-class support.
- **Maintenance**: active releases, security posture.
- **DX**: form validation story, documentation quality.

## 6) Design principles (to-be)

- Clear **visual hierarchy** (page title, helper text, primary vs secondary actions).
- **Single-column** forms on small/medium viewports; predictable error placement (inline + summary where wireframes require).
- **Unified feedback**: success and error patterns match the chosen library (toast, banner, or inline—pick one primary pattern per flow).
- **Brand**: LoreWeave primary color, typography, and radius applied via **theme tokens**, not fighting the library defaults without a deliberate design choice.

## 7) Design system (planning level)

Avoid redefining every token manually: **map** LoreWeave branding onto the **Tailwind + shadcn** theme layer:

- **Tailwind:** `tailwind.config` theme extension and/or CSS variables.
- **shadcn/ui:** `:root` / `.dark` CSS variables as generated by the CLI (`globals.css`), customized for LoreWeave primary, radius, and fonts.

Token groups to plan (values TBD at implementation):

- Primary / neutral / semantic (**success**, **destructive**, **muted**).
- Typography scale (display, title, body, caption).
- Spacing and **border radius**.
- Elevation / shadow (subtle; avoid heavy drop shadows for auth cards unless intentional).

## 8) Component architecture (planning level)

Introduce a small **app shell** and reusable building blocks (names illustrative):

- **AppShell** or **PageLayout**: max width, padding, background, optional header strip.
- **AppNav** / **UserMenu**: consistent navigation and auth state.
- **Form primitives**: labeled inputs, password field, submit row, link to secondary routes.
- **Feedback**: `Alert`, inline field errors, loading state on submit (spinner or disabled button).
- **Optional:** `Skeleton` for profile load.

Refactor pages to **compose** these instead of duplicating raw `<label>` + `<input>` blocks everywhere. Align folder layout with `19_MODULE01_FRONTEND_DETAILED_DESIGN.md` when refactoring (e.g. `identity/components`, `identity/screens`)—exact move is an implementation detail.

## 9) Per-screen checklist

For each screen, verify against `20_MODULE01_UI_UX_WIREFRAME_SPEC.md` blocks and states:


| Screen         | Layout                         | Components to standardize                            | States to cover                                  |
| -------------- | ------------------------------ | ---------------------------------------------------- | ------------------------------------------------ |
| Register       | Header + form + link to login  | Text inputs, password, primary button, error summary | default, submitting, validation error, API error |
| Login          | Header + form + forgot link    | Same                                                 | + rate-limit messaging area if surfaced by API   |
| Verify         | Request + token form           | Button, token input, success/error alerts            | success path, invalid token                      |
| Forgot         | Email + submit                 | Email input, generic confirmation copy               | loading, error                                   |
| Reset          | Token + new password           | Inputs, security notice block                        | validation, API errors                           |
| Profile        | Editable fields                | Inputs, save/cancel                                  | loading profile, patch errors                    |
| Security prefs | Toggles / selects per contract | Form controls per `19`                               | save feedback                                    |
| Home / nav     | Global chrome                  | Nav links, logout                                    | authenticated vs guest                           |


## 10) States and accessibility

Required states (from `20`): empty/default, loading/submitting, validation error, API error, success, disabled where applicable.

Accessibility goals (implementation must verify):

- Visible **focus** styles (library defaults or theme override).
- **Labels** associated with every input; errors linked via `aria-describedby` where supported.
- **Live regions** or polite announcements for critical errors if toast-only feedback is used.

## 11) Phased rollout (suggested)

1. **Phase 1 — Tooling & shell:** Add chosen stack; global theme tokens; App shell + navigation; replace `styles.css` gradually.
2. **Phase 2 — Auth screens:** Register, Login, Forgot, Reset, Verify.
3. **Phase 3 — Authenticated screens:** Profile, Security; responsive pass.
4. **Phase 4 — Hardening:** Bundle analysis (`vite build`); prune unused imports; ensure Docker `frontend` image still builds with updated `package-lock.json`.

## 12) Completion criteria

- Visual pass matches **wireframe intent** in `20` (not pixel-perfect, but blocks and states present).
- Flows remain demonstrable per `14_MODULE01_ACCEPTANCE_TEST_PLAN.md` (screenshots or recordings as evidence).
- **CI:** `npm ci`, `npm test`, `npm run build` succeed for `frontend/`.
- **Stack decision** recorded in this document (section 5.3); a short ADR is optional if the team wants a separate decision log.

**Interim note (2026-03-21):** Implementation and **smoke** verification are sufficient to **proceed with Module 02 planning** from an execution standpoint. **Full** completion against the bullets above (especially formal `14` execution with evidence) remains **open** — tracked in `docs/implementation/MODULE01_DEFERRED_FOLLOWUPS.md`.

## 13) Out of scope (for this plan)

- Full **i18n** rollout (message catalogs for all locales).
- **Dark mode** unless explicitly added as a themed variant later.
- Marketing / landing site outside the identity module.
- Changing REST paths or payload shapes (contract work is separate).

## 14) Risks and dependencies

- **Bundle size** growth; mitigate with lazy routes (if introduced) and careful imports.
- **Major version upgrades** of UI libraries—pin versions and plan upgrade windows.
- **Docker:** frontend production build must stay reproducible (`npm ci` + lockfile).
- **Structural refactor** may require updating `19` or adding a short implementation note for folder layout—keep planning docs in sync.

## References

- `docs/03_planning/17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`
- `docs/03_planning/19_MODULE01_FRONTEND_DETAILED_DESIGN.md`
- `docs/03_planning/20_MODULE01_UI_UX_WIREFRAME_SPEC.md`
- `docs/03_planning/13_MODULE01_FRONTEND_FLOW_SPEC.md`
- `docs/03_planning/14_MODULE01_ACCEPTANCE_TEST_PLAN.md`
- `contracts/api/identity/v1/openapi.yaml`

