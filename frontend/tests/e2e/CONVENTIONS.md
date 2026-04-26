# E2E Test Conventions

Project-wide conventions for E2E-friendly frontend code + Playwright test code.

## 1. `data-testid` selector convention

### Why test IDs (not text / role / class)

LoreWeave is a **multilingual** application (English + Vietnamese + more) where the demo pipeline shows the same flow across multiple languages — Dracula in English, Tây Du Ký in Vietnamese, etc. Selectors that depend on visible text (`getByText`, `getByRole({ name: ... })`) break when i18n strings change. Class-based selectors break when Tailwind utility classes shift.

`data-testid` is **language-agnostic** and **style-agnostic** — the only stable contract between UI code and test code.

### Naming format

```
data-testid="<feature>-<element>[-<variant>]"
```

- **kebab-case**, lowercase
- `<feature>`: the feature/page namespace (`auth`, `book`, `chapter`, `glossary`, `wiki`, `knowledge`, `settings`, …)
- `<element>`: what the element does (`email-input`, `submit-button`, `entity-card`, `extract-trigger`)
- `<variant>` (optional): for desktop/mobile or item-level identifiers (`mobile`, `desktop`, `{id}`, `{slug}`)

### Examples

| feature | testid | role |
|---|---|---|
| auth | `auth-email-input` | login email field |
| auth | `auth-password-input` | login password field |
| auth | `auth-submit-button` | login submit |
| auth | `auth-error-message` | login error toast |
| book | `book-create-button` | open create-book dialog |
| book | `book-title-input` | book title field |
| chapter | `chapter-add-button` | add new chapter |
| chapter | `chapter-content-editor` | TipTap editor area |
| glossary | `glossary-extract-trigger` | start glossary extraction |
| glossary | `glossary-entity-card-{name}` | per-entity card |
| wiki | `wiki-page-link-{slug}` | per-wiki-page link |
| knowledge | `entities-table` | knowledge graph entities table |
| knowledge | `entities-row` | per-row in entities table |

### When to add a `data-testid`

**Add it** if:
- The element is a target of a Playwright test (click / fill / assert visible)
- The element has dynamic text or i18n content where text-based selection is fragile
- The element is one-of-many similar elements (form inputs, list items)

**Don't add it** if:
- The element is decorative (icons-only, dividers, layout wrappers)
- A semantic role + label is more natural and unique on the page (`<form aria-label="Search">`)
- It's an internal child that the test doesn't directly interact with

Rule of thumb: a Page Object's locator list = the test surface = the test ID list. No more, no less.

### Where to add it

**Source code** (`frontend/src/...`) — alongside the existing `className` attribute. Example:

```tsx
<input
  type="email"
  data-testid="auth-email-input"
  className="..."
/>
```

Place `data-testid` adjacent to other props (close to `type` / `className`), not in the middle of conditional logic.

### Shared components (cross-feature)

Components in `src/components/` (e.g., `PageHeader`, `FormDialog`, `DataTable`) are used by multiple features. Their stable elements get a **component-scoped** testid using the kebab-cased component name:

| Component | testid | Where used |
|---|---|---|
| `PageHeader` | `page-header-title` | The H1 — every page that uses PageHeader gets a stable title hook for free |

When a shared-component testid would collide with a feature testid (e.g., a generic button class), prefer the more specific feature-level testid in the feature component itself.

## 2. Page Object Model (PoM)

### Pattern

Every page or major UI region gets a class in `tests/e2e/pages/`:

```ts
import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

export class LoginPage {
  readonly page: Page;
  readonly emailInput: Locator;
  // ...
  constructor(page: Page) {
    this.page = page;
    this.emailInput = page.getByTestId('auth-email-input');
  }

  async goto(): Promise<void> { /* ... */ }
  async login(email: string, password: string): Promise<void> { /* ... */ }
  async expectError(): Promise<void> { /* ... */ }
}
```

### Rules

- **Locators in constructor** — defined once, reused across methods
- **Async methods only** — Playwright operations are all promises
- **Methods return `Promise<void>`** unless they extract data
- **No raw selectors in spec files** — all UI access via PoM
- **One PoM per page/route** — `LoginPage`, `BooksPage`, `ChapterEditorPage`, `KnowledgeGraphPage`

## 3. Wait/timing discipline

### Forbidden

```ts
await page.waitForTimeout(2000);  // ❌ never
await page.waitForSelector('...', { timeout: 5000 });  // ❌ legacy API
```

### Use

```ts
await expect(locator).toBeVisible();        // ✅ auto-retries until visible
await page.waitForURL('**/books');          // ✅ semantic wait
await expect(locator).toHaveText('foo');    // ✅ retries until text matches
```

Playwright's web-first assertions retry automatically until timeout. They are the only correct way to wait.

## 4. Test data discipline

- **Test account**: `claude-test@loreweave.dev` / `Claude@Test2026` (per CLAUDE.md, env-overridable)
- **Demo book** (Phase 3): Dracula Ch.1 — fixture content checked into `tests/e2e/fixtures/`
- **Determinism**: same input → same expected output. No random or wall-clock dependencies in assertions.
- **Cleanup**: tests should not depend on prior state. Each test creates + deletes its own data when feasible. (V1 acceptable to share state if test order is enforced and idempotent.)

## 5. Test file naming

```
specs/<scope>-<intent>.spec.ts
```

- `smoke-login.spec.ts` — basic auth pipeline check
- `demo-pipeline.spec.ts` — full Dracula → glossary → wiki → knowledge flow (Phase 3)
- `regression-glossary-extract.spec.ts` — bug-specific regression (future)
