# Local test environment — TEMPLATE

**Copy this file to `docs/dev/LOCAL_TEST_ENV.md` and fill it in. That copy is git-ignored.**

```bash
cp docs/dev/LOCAL_TEST_ENV.example.md docs/dev/LOCAL_TEST_ENV.md
```

## Why this file is not tracked

Every value below is **specific to one machine**. A UUID from your local `loreweave_auth`, a
`user_model_id` from your local `loreweave_provider_registry`, a port you happened to map — none of
them mean anything on anyone else's checkout. A tracked file full of them does not save the next
contributor time; it sends them to a 404 or, worse, to a row that silently belongs to someone else.
This repo already learned that lesson once with `user_model_id` (see the `scripts/dev-model.py`
section of [`AGENTS.md`](../../AGENTS.md)), and the fix was the same: **resolve it, don't pin it.**

The account described here is a **local development seed**. It is not a shared credential, it must
never be created on a deployed instance, and nothing from a real deployment belongs in this file
even after you have git-ignored it.

---

## 1. Seed the test account

Bring the stack up, then register through the normal signup flow (dev has no email-verification
gate) or seed directly:

```bash
docker compose -f infra/docker-compose.yml up -d
# then register at http://localhost:5174/register, or:
curl -X POST http://localhost:3123/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"<YOUR_TEST_EMAIL>","password":"<YOUR_TEST_PASSWORD>","name":"<YOUR_TEST_NAME>"}'
```

Pick your own values. Do not reuse a password you use anywhere real — this one will sit in plaintext
in a local file and in your shell history.

Several suites need a **second** account to exercise cross-user isolation (tenancy tests assert that
user A cannot see or mutate user B's rows). Seed that one the same way.

## 2. Record what you seeded

```
# Primary test account
email:      <fill in>
password:   <fill in>
name:       <fill in>
auth id:    <SELECT id FROM users WHERE email = '<your email>';  -- in loreweave_auth>

# Second account — cross-user isolation tests
email:      <fill in>
password:   <fill in>
auth id:    <fill in>
```

## 3. Export for the E2E suite

The Playwright helpers read these and fall back to a dev-seed default only when unset — see
[`frontend/tests/e2e/helpers/auth.ts`](../../frontend/tests/e2e/helpers/auth.ts). Setting them
explicitly is what makes the suite portable off your machine.

```bash
export PLAYWRIGHT_TEST_EMAIL="<fill in>"
export PLAYWRIGHT_TEST_PASSWORD="<fill in>"
export PLAYWRIGHT_TEST_EMAIL_B="<fill in>"
export PLAYWRIGHT_TEST_PASSWORD_B="<fill in>"
```

## 4. BYOK models — for real LLM smokes

Browser tests only need the login above. Anything that exercises a real model call needs at least
one **BYOK credential + `user_models` row** on the account, registered through
`provider-registry-service` (the only service allowed to hold provider SDKs or keys — see the
Provider-gateway invariant in [`AGENTS.md`](../../AGENTS.md)).

A local backend (LM Studio, Ollama, `local-rerank-service`, …) is registered the *same* way — as a
BYOK provider credential with an `endpoint_base_url`, **never** as a per-service `*_URL` /
`*_MODEL` env var. That shortcut is a known defect class here (`D-RERANK-NOT-BYOK`).

**Never hardcode a `user_model_id` anywhere.** Resolve it:

```bash
python scripts/dev-model.py --list          # what you have, and what would be picked
python scripts/dev-model.py chat            # the user_model_id for this stack, this role
python scripts/dev-model.py --env           # exportable lines for every role
```

The resolver refuses to return a billed model without `--allow-paid`, so a local-only setup cannot
quietly start spending. Note that `user_default_models` is typically empty on a fresh account —
always pass an explicit `model_ref` rather than relying on "the default model for capability X".

Record which backends you have running:

```
# e.g. lm_studio @ http://localhost:1234/v1  — Gemma-4 26B-A4B QAT — chat, local/free
<fill in>
```

## 5. Local ports and anything else machine-specific

Defaults are in the Project Constants section of [`AGENTS.md`](../../AGENTS.md). Record only your
**deviations** here — a remapped port, a service you run natively instead of in Docker, a proxy.

```
<fill in, or "none — all defaults">
```

---

**If you are an AI agent reading this template rather than a filled-in
`docs/dev/LOCAL_TEST_ENV.md`:** the developer has not set up their local test environment yet. Say
so and ask. Do not invent credentials, and do not scavenge them out of `docs/plans/**` or
`docs/sessions/**` — those are historical records from one machine and are wrong here.
