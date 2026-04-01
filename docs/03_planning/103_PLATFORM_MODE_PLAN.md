# Platform Mode Plan — Admin, System Settings, Tiers & Multi-Tenancy

> **Status:** Planning (not started)
> **Priority:** After Phase 3 + Phase 3.5 complete
> **Blocks:** Nothing currently — self-hosted mode works without this
> **Enables:** Hosted community platform, paid tiers, managed AI providers
>
> **Created:** 2026-04-02

---

## 1. Context

LoreWeave currently runs as a **self-hosted Docker Compose deployment**. The person who runs
`docker compose up` is implicitly the admin. All users are equal — anyone who registers can
create books, configure AI providers, and manage glossary kinds.

This plan defines the architecture for **Platform Mode** — the layer needed to run LoreWeave
as a hosted multi-tenant service with admin controls, system defaults, user tiers, and
managed AI providers.

### Current State vs. Platform Mode

| Feature | Self-hosted (now) | Platform Mode (future) |
|---------|-------------------|----------------------|
| Admin role | Not needed — host = admin | Required — explicit admin users |
| User registration | Open | Invite-only or open + approval |
| AI providers | BYOK per user | System-managed + BYOK |
| AI models | User-configured | System default + user override |
| Prompts | Per-user + per-book | System defaults → user override → book override |
| Entity kinds | Global, any user | System kinds (admin) + user kinds (per-book) |
| Storage quota | Hardcoded config | Tier-based, admin-adjustable |
| Usage billing | Simple metering | Tier-based limits, credits, invoicing |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PLATFORM LAYER                               │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │ Admin Panel  │  │ Tier Engine │  │ System AI   │                │
│  │             │  │             │  │ Gateway     │                │
│  │ - Users     │  │ - Tiers     │  │             │                │
│  │ - Roles     │  │ - Quotas    │  │ - Providers │                │
│  │ - Settings  │  │ - Limits    │  │ - Models    │                │
│  │ - Kinds     │  │ - Credits   │  │ - Prompts   │                │
│  │ - Prompts   │  │ - Billing   │  │ - Routing   │                │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                │
│         │                │                │                        │
│  ───────┴────────────────┴────────────────┴──────────              │
│                     auth-service (extended)                         │
│                     + new: platform-service                        │
└─────────────────────────────────────────────────────────────────────┘
          │                │                │
   existing services  (book, glossary, translation, chat, etc.)
```

### Deployment Modes

```
MODE=self-hosted    (default)
  - No admin panel
  - No tier engine
  - All users are equal
  - BYOK only
  - Config via environment variables

MODE=platform
  - Admin panel enabled
  - Tier engine active
  - System AI providers available
  - Registration policies enforced
  - Billing integration (Stripe)
```

The `ModeProvider` in the frontend (already exists, currently unused) will finally be used
to toggle platform features in the UI.

---

## 3. Role & Permission Model

### 3.1 Roles

| Role | Scope | Description |
|------|-------|-------------|
| `super_admin` | Global | Platform owner. Full access to everything. |
| `admin` | Global | Manages users, system settings, tiers. Cannot modify super_admin. |
| `moderator` | Global | Reviews reported content, manages public catalog. |
| `user` | Own data | Default role. Creates books, uses AI, manages own content. |

### 3.2 Permissions

```
Permissions are additive. Each role inherits from the role below it.

user:
  - books.own.*          (CRUD own books)
  - chapters.own.*       (CRUD own chapters)
  - glossary.own.*       (CRUD own book glossary)
  - translation.own.*    (manage own translations)
  - chat.own.*           (own chat sessions)
  - providers.own.*      (BYOK providers + models)
  - profile.own.*        (own profile)

moderator (+ user):
  - content.moderate     (review reports, hide content)
  - catalog.manage       (feature/unfeature books)
  - users.view           (read user list)

admin (+ moderator):
  - users.manage         (create, disable, change role)
  - tiers.manage         (CRUD tiers, assign users)
  - settings.system      (system kinds, prompts, providers)
  - billing.view         (usage reports, revenue)

super_admin (+ admin):
  - admins.manage        (promote/demote admins)
  - system.dangerous     (reset DB, export all data, maintenance mode)
```

### 3.3 Implementation

Add `role` column to `auth_users` table:

```sql
ALTER TABLE auth_users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';
-- Values: 'super_admin', 'admin', 'moderator', 'user'
```

JWT claims extended:
```json
{
  "sub": "user-uuid",
  "sid": "session-uuid",
  "role": "admin",
  "tier": "pro",
  "exp": 1234567890
}
```

Middleware: `requireRole("admin")` — checks JWT claim before handler.

---

## 4. System Settings

### 4.1 Settings Storage

New table in `loreweave_auth` (or a new `loreweave_platform` DB):

```sql
CREATE TABLE system_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by UUID REFERENCES auth_users(user_id)
);
```

### 4.2 Setting Categories

#### Registration & Access
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `registration.mode` | enum | `open` | `open`, `invite_only`, `approval_required`, `closed` |
| `registration.default_tier` | string | `free` | Tier assigned to new users |
| `registration.require_email_verify` | bool | `true` | Require email verification |
| `registration.allowed_domains` | string[] | `[]` | Restrict to specific email domains |

#### AI Defaults
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ai.default_translation_prompt` | string | (built-in) | Default system prompt for translation AI |
| `ai.default_user_prompt_tpl` | string | (built-in) | Default user prompt template for translation |
| `ai.default_chat_system_prompt` | string | (built-in) | Default system prompt for chat AI |
| `ai.default_chat_user_prompt_tpl` | string | (built-in) | Default user prompt template for chat |
| `ai.default_grammar_prompt` | string | (built-in) | Default prompt for grammar check AI |
| `ai.per_kind_prompts` | map | `{}` | System prompt override per entity kind |

#### System AI Providers (platform-managed)
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ai.system_providers` | object[] | `[]` | Platform-managed AI provider credentials |
| `ai.system_models` | object[] | `[]` | Platform-managed models (available to all users) |
| `ai.model_routing` | object | `{}` | Default model routing rules (fallback, cost caps) |
| `ai.allow_byok` | bool | `true` | Allow users to bring their own API keys |

#### Entity Kinds
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `glossary.system_kinds_locked` | bool | `false` | Prevent users from editing system kind attributes |
| `glossary.allow_user_kinds` | bool | `true` | Allow users to create custom kinds |
| `glossary.max_user_kinds` | int | `20` | Max custom kinds per user |

#### Content & Moderation
| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `content.auto_moderation` | bool | `false` | AI-based content moderation |
| `content.require_approval_for_public` | bool | `false` | Admin approval before book goes public |
| `content.max_books_per_user` | int | `100` | Default book limit |
| `content.max_chapters_per_book` | int | `500` | Default chapter limit |

---

## 5. User Tiers & Quotas

### 5.1 Tier Table

```sql
CREATE TABLE user_tiers (
  tier_id UUID PRIMARY KEY DEFAULT uuidv7(),
  code TEXT NOT NULL UNIQUE,          -- 'free', 'pro', 'enterprise'
  name TEXT NOT NULL,                  -- 'Free', 'Pro', 'Enterprise'
  sort_order INT NOT NULL DEFAULT 0,
  is_default BOOLEAN NOT NULL DEFAULT false,
  limits JSONB NOT NULL,               -- structured limits object
  price_monthly_usd NUMERIC(10,2),
  price_yearly_usd NUMERIC(10,2),
  stripe_price_id_monthly TEXT,
  stripe_price_id_yearly TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 5.2 Default Tiers

| Tier | Books | Chapters/book | Storage | AI tokens/month | AI providers | Price |
|------|-------|---------------|---------|-----------------|-------------|-------|
| Free | 5 | 50 | 500 MB | 100K | BYOK only | $0 |
| Pro | 50 | 200 | 10 GB | 2M | BYOK + System | $12/mo |
| Enterprise | Unlimited | Unlimited | 100 GB | 20M | All + priority | $49/mo |

### 5.3 Limits Structure (JSONB)

```json
{
  "max_books": 5,
  "max_chapters_per_book": 50,
  "storage_bytes": 524288000,
  "ai_tokens_monthly": 100000,
  "ai_providers": ["byok"],
  "features": {
    "translation": true,
    "chat": true,
    "glossary": true,
    "wiki": false,
    "export": true,
    "collaboration": false,
    "api_access": false,
    "priority_support": false
  }
}
```

### 5.4 Tier Assignment

```sql
-- Add tier_id to auth_users
ALTER TABLE auth_users ADD COLUMN tier_id UUID REFERENCES user_tiers(tier_id);
-- Default: assigned via registration.default_tier setting
```

### 5.5 Quota Enforcement

Quotas are checked at the **service level** (not gateway) for accuracy:

| Service | What it checks | When |
|---------|---------------|------|
| book-service | `max_books`, `max_chapters_per_book`, `storage_bytes` | Create book/chapter |
| translation-service | `ai_tokens_monthly` | Before AI invocation |
| chat-service | `ai_tokens_monthly` | Before AI invocation |
| usage-billing-service | Token usage tracking + tier limit enforcement | On every AI call |

Each service reads the user's tier limits from the JWT claims or by calling a lightweight
internal endpoint on auth-service.

---

## 6. System AI Providers & Models

### 6.1 Platform-Managed Providers

In self-hosted mode, users BYOK (bring their own API keys). In platform mode, the admin can
configure **system providers** — shared API keys that all users can use, metered against
their tier quota.

```sql
-- New table in loreweave_provider_registry (or platform DB)
CREATE TABLE system_providers (
  provider_id UUID PRIMARY KEY DEFAULT uuidv7(),
  provider_kind TEXT NOT NULL,         -- 'openai', 'anthropic', 'ollama'
  display_name TEXT NOT NULL,
  endpoint_base_url TEXT,
  secret_encrypted BYTEA NOT NULL,     -- encrypted at rest
  is_active BOOLEAN NOT NULL DEFAULT true,
  cost_per_1k_input_tokens NUMERIC(10,6),
  cost_per_1k_output_tokens NUMERIC(10,6),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE system_models (
  model_id UUID PRIMARY KEY DEFAULT uuidv7(),
  provider_id UUID NOT NULL REFERENCES system_providers(provider_id),
  provider_model_name TEXT NOT NULL,
  display_name TEXT NOT NULL,
  context_length INT,
  tier_codes TEXT[] NOT NULL DEFAULT '{pro,enterprise}',  -- which tiers can use
  is_active BOOLEAN NOT NULL DEFAULT true,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.2 Model Resolution Order

When a user makes an AI request, the system resolves which model to use:

```
1. User's explicit model choice (if specified)
2. Book-level translation settings → model_ref
3. User-level preferences → model_ref
4. System default model for the action type
5. Reject if no model available
```

For system models, the request goes through the platform's provider credentials,
and usage is metered against the user's tier quota.

---

## 7. Admin Panel UI

### 7.1 Pages

| Page | Route | Purpose |
|------|-------|---------|
| Dashboard | `/admin` | User count, book count, AI usage, revenue |
| Users | `/admin/users` | User list, search, role change, tier assign |
| User Detail | `/admin/users/:id` | User profile, usage, books, ban/suspend |
| Tiers | `/admin/tiers` | CRUD tiers, pricing, feature flags |
| System Settings | `/admin/settings` | All settings from §4.2 |
| AI Providers | `/admin/ai/providers` | System provider CRUD + test |
| AI Models | `/admin/ai/models` | System model CRUD + routing |
| AI Prompts | `/admin/ai/prompts` | Default prompts per action type |
| Entity Kinds | `/admin/glossary/kinds` | System kind management (current Kind Editor) |
| Moderation | `/admin/moderation` | Reported content queue |
| Billing | `/admin/billing` | Revenue, invoices, Stripe integration |

### 7.2 Access

- Admin pages hidden when `MODE=self-hosted`
- Accessible only to `admin` and `super_admin` roles
- Separate layout with admin sidebar (different from user sidebar)

---

## 8. Per-Kind AI Prompts

Each entity kind can have custom AI prompts for different operations:

```json
{
  "character": {
    "translation_system_prompt": "You are translating a character description for a novel...",
    "chat_context_prompt": "The user is asking about this character: {entity_name}...",
    "auto_fill_prompt": "Generate attribute values for this character based on the description...",
    "glossary_suggestion_prompt": "Suggest related entities for this character..."
  },
  "location": {
    "translation_system_prompt": "You are translating a location description...",
    ...
  }
}
```

This allows the AI to behave differently when translating a character bio vs. a location
description vs. a magic spell, producing more genre-appropriate results.

**Storage:** `system_settings` table with key `ai.per_kind_prompts` (JSONB).

**Override chain:** System default → per-kind → per-book → per-user (most specific wins).

---

## 9. Migration Path

### Phase 1: Role + Settings Foundation
- Add `role` column to `auth_users`
- Create `system_settings` table
- Add `requireRole()` middleware to auth-service
- Admin role seeded from env var (`SUPER_ADMIN_EMAIL`)
- Migrate Kind Editor to check `glossary.system_kinds_locked` setting

### Phase 2: Tiers + Quotas
- Create `user_tiers` table
- Add `tier_id` to `auth_users`
- Extend JWT with `role` + `tier` claims
- Quota enforcement in book-service, translation-service, chat-service
- Admin UI: Users + Tiers pages

### Phase 3: System AI
- Create `system_providers` + `system_models` tables
- Model resolution with system fallback
- Usage metering per-tier
- Admin UI: AI Providers + Models + Prompts

### Phase 4: Admin Panel
- Admin layout + sidebar
- Dashboard with metrics
- System settings editor
- Moderation queue
- Billing integration (Stripe)

### Phase 5: Per-Kind AI Prompts
- Admin UI for per-kind prompt editor
- Prompt resolution chain in translation-service + chat-service
- Auto-fill feature in entity editor

---

## 10. Task Estimates

| Phase | Backend | Frontend | Total | Size |
|-------|---------|----------|-------|------|
| P1: Roles + Settings | 4 tasks | 2 tasks | 6 | M |
| P2: Tiers + Quotas | 5 tasks | 3 tasks | 8 | L |
| P3: System AI | 4 tasks | 3 tasks | 7 | L |
| P4: Admin Panel | 2 tasks | 8 tasks | 10 | XL |
| P5: Per-Kind Prompts | 2 tasks | 2 tasks | 4 | M |
| **Total** | **17** | **18** | **35** | — |

---

## 11. Decision Log

| # | Decision | Reasoning |
|---|----------|-----------|
| 1 | Defer until after Phase 3.5 | Self-hosted mode works without this. Build user-facing features first. |
| 2 | Single `role` column, not RBAC tables | Simple enough for 4 roles. RBAC tables are over-engineering for this scale. |
| 3 | Settings as JSONB key-value, not typed columns | Flexible, no migration needed for new settings. Validated at app level. |
| 4 | Tier limits in JSONB, not separate columns | Same flexibility reasoning. Schema stays stable as limits evolve. |
| 5 | `ModeProvider` for UI feature gating | Already exists (unused). Platform features hidden in self-hosted mode. |
| 6 | System AI providers separate from user providers | Different lifecycle, different billing, different trust level. |
| 7 | Per-kind prompts in system_settings | One table for all settings. Admin UI is a generic JSONB editor. |
| 8 | Stripe for billing | Industry standard, well-documented, handles subscriptions + metering. |
