# Contributing to LoreWeave

Welcome. This file is the **entry point** — enough to get you running, oriented, and shipping a
first PR without reading all 2,000 documents in `docs/`.

LoreWeave is a large monorepo: **47 services** in four languages, plus two frontends and a Rust
kernel tier. That size is manageable once you know that **you only ever need the slice you are
working on.** Nobody reads it all. This file tells you which slice.

---

## 1. Read in this order

| # | File | Why |
|---|---|---|
| 1 | This file | Setup, layout, PR process |
| 2 | [`AGENTS.md`](AGENTS.md) | **The rulebook.** Invariants, standards, and the bug lore behind them |
| 3 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | What each service is for |
| 4 | [`docs/standards/README.md`](docs/standards/README.md) | Index of every cross-cutting rule — has a *quick-nav by concern* |
| 5 | [`docs/sessions/SESSION_HANDOFF.md`](docs/sessions/SESSION_HANDOFF.md) | **What is in flight right now**, and what is deferred |

**[`AGENTS.md`](AGENTS.md) is not optional reading and it is not style guidance.** Nearly every rule
in it is there because the failure it describes *actually shipped in this repo*. A test that wiped a
real production table. A vacuous assertion that could not fail, shipped twenty-seven times. A tool
argument with no enum that made the LLM hallucinate success. Reviewers will point at that file, so
you may as well read it first.

`AGENTS.md` is also what AI coding assistants load — see [§9](#9-ai-assisted-contributions).

---

## 2. Where things live

```
services/          47 microservices, one Postgres DB each
frontend/          the main app — Vite + React + Tailwind + shadcn/ui
cms-frontend/      admin CMS
frontend-game/     the Living Worlds client (unbuilt track — design only)
crates/ pkg/       Rust kernel + shared Go packages
contracts/         OpenAPI specs, JSON schemas, the language rule
infra/             docker-compose and infra config
scripts/           gates, dev tooling, RAID/workflow automation
docs/              governance, planning, standards, session history
```

**Which language does a service use?** [`contracts/language-rule.yaml`](contracts/language-rule.yaml)
is authoritative and CI-enforced. The rule: **Rust** = kernel-derived (world/travel/tilemap) ·
**Go** = domain + meta · **Python** = AI/LLM · **TypeScript** = gateway/BFF + realtime.

**Which service backs a screen?** [`docs/FEATURE_INDEX.md`](docs/FEATURE_INDEX.md) maps all 41
frontend feature folders → route → owning service. **Look it up; do not infer from the URL** —
`/v1/glossary-translate` and `/v1/extraction` both hit `translation-service`, and `/v1/worlds` hits
`book-service`.

Two unrelated trees are called "features": `frontend/src/features/*` is shipped UI;
`docs/03_planning/LLM_MMO_RPG/features/*` is design for an unbuilt track. Neither indexes the other.

---

## 3. Local setup

**Toolchain:** Go 1.25 · Rust edition 2024 · Python 3.11+ · Node 20+ with pnpm 9.15.9 · Docker.

```bash
git clone <your fork>
cd lore-weave
cd infra && docker compose up --build
```

UI at **http://localhost:5174** · gateway `:3123` · admin CMS `:5175`.

> `:5174` serves the **baked** nginx production build. Rebuild the image to see frontend changes — a
> host `vite dev` can silently shadow it. For fast FE iteration use `vite dev` on `:5199`.

`docker compose up` starts the **novel platform**. The Living Worlds reality-ops tier (the SRE
services, the Rust world/travel services, the Patroni meta cluster) is not in the default stack.

**Install the git hooks — once per checkout:**

```bash
git config core.hooksPath .githooks
```

This wires the gates described in [§6](#6-the-gates). Skipping it means CI catches things your
laptop should have.

**Set up your test account:** copy [`docs/dev/LOCAL_TEST_ENV.example.md`](docs/dev/LOCAL_TEST_ENV.example.md)
to `docs/dev/LOCAL_TEST_ENV.md` (git-ignored) and fill it in. Those values are per-machine —
credentials, local DB UUIDs, and `user_model_id`s from another developer's checkout will not work on
yours, which is exactly why they are not tracked.

---

## 4. The rules that get PRs rejected

Full detail lives in [`AGENTS.md`](AGENTS.md) and [`docs/standards/`](docs/standards/). This is the
short list of what reviewers actually catch:

- **Multi-tenant, always.** Self-hosted does **not** mean single-user. Every user-facing table
  carries a scope key (`owner_user_id` / `book_id`) and every query filters by it. A `UNIQUE(code)`
  on a shared, user-writable table is a tenancy defect — the correct constraint is
  `UNIQUE(owner_user_id, code)`. A regular user must never be able to mutate a System-tier row.
- **All provider calls go through `provider-registry-service`.** No service imports an LLM,
  embedding, rerank, image, audio, or STT SDK directly. **Local backends are not an exception** —
  LM Studio / Ollama / a local rerank service is reached as a BYOK provider credential, never via a
  per-service `*_URL` / `*_MODEL` env var.
- **No hardcoded model names or pricing.** They resolve from `provider-registry-service`.
- **All external traffic through `api-gateway-bff`** — with one sanctioned exception, the
  `game-server` WebSocket transport.
- **New AI *agent* capability ⇒ an MCP tool through `ai-gateway`**, not a bespoke HTTP endpoint
  driven by a raw prompt. Non-agentic LLM pipelines (translation, enrichment) are exempt.
- **A new public `/v1` route needs a contract entry** in `contracts/api/` — CI fails otherwise
  (currently enforced for `glossary-service`, and the pattern is being extended).
- **No hardcoded secrets.** Everything via env vars; services fail to start when one is missing.
- **A check that cannot fail is worse than no check.** If you add a test, gate, lint, or assertion:
  break the thing it guards, watch it go red, put it back, and paste that output in the PR. See
  [`docs/standards/non-vacuity.md`](docs/standards/non-vacuity.md).
- **Tests must not be able to destroy a real database.** Scope every cleanup
  (`WHERE owner_user_id = $1`), read the DSN only from a dedicated `*_TEST_*` variable, and call the
  runtime throwaway-DB guard before any destructive statement. This rule exists because an unscoped
  `DELETE FROM books` once hard-deleted every user's books, unrecoverably.
- **Frontend follows an imposed MVC split** — `hooks/` own logic, `components/` only render,
  `context/` shares state. Never conditionally unmount a stateful component; never use `useEffect`
  to react to a user action.
- **Every persisted artifact is written in English** — code, comments, identifiers, docs, commit
  messages, PR bodies, log and error messages. Non-English is fine where the text *is* the subject
  matter (corpus fixtures, i18n bundles, CJK/RTL test data, domain terms — gloss those on first
  use). Conversation in issues and discussions can be any language; the artifact cannot be mixed.

---

## 5. Tests

```bash
# Python services
python -m pip install pytest-xdist          # once per machine
python -m pytest tests -q -n auto --dist loadgroup

# composition-service ONLY — it gives each worker its own DB
python -m pytest tests -q -n auto --dist load

# Go
go test ./... -count=1

# Rust
cargo test

# Frontend — there is no lockfile committed, so install first
cd frontend && npm install && npm test
```

### Why so much of the suite says SKIPPED

A full run reports roughly a thousand skipped tests. Almost none of that is dead code — they are
integration tests that need a live Postgres, Neo4j, Redis, MinIO or KMS, and they skip cleanly when
the matching `*_TEST_*` variable is unset. Unit tests run for everyone; **you do not need any of
this to open a PR.**

To see exactly which suites are switched off and what would switch them on:

```bash
python scripts/test-skip-census.py            # grouped by gating variable
python scripts/test-skip-census.py --files    # which files each one covers
```

It walks the tree rather than reading a list, so a suite added tomorrow shows up without anyone
maintaining an inventory. Point the variables at a throwaway database — never a real one — and
read [`docs/dev/LOCAL_TEST_ENV.example.md`](docs/dev/LOCAL_TEST_ENV.example.md) first.

A new test file that touches a real database or port must carry
`pytestmark = pytest.mark.xdist_group("pg")`, or parallel workers interleave and the counts lie.
**Never run two suites against the same test database at once** — a contaminated run produces
failures that look exactly like code defects.

**Unit-green is not enough for cross-service work.** If your change touches two or more services,
run a real call across them on a live stack and say so in the PR. Mock-only coverage has repeatedly
hidden contract bugs here. If the stack genuinely will not boot for you, say *that* instead — an
honest "could not live-smoke, here is why" is fine; a silent skip is not.

---

## 6. The gates

Pre-commit hooks (after `git config core.hooksPath .githooks`) and CI both run:

| Gate | Blocks |
|---|---|
| `scripts/ai-provider-gate.py` | Direct provider SDK imports · hardcoded model literals |
| `scripts/db-safety-gate.py` | Unscoped `DELETE`/`TRUNCATE`/`DROP` in tests · a `*_TEST_*_URL` pointing at a production DB |
| `scripts/language-rule-lint.sh` | A service written in the wrong language, or missing from `contracts/language-rule.yaml` |
| `scripts/deferral-gate.py` | A tracked deferral with no mechanism to wake it up |
| `scripts/workflow-gate.py` | Phase order and evidence (see [§7](#7-the-workflow)) |
| `make lint` | Repo-wide lint |

If a gate fires on a genuine false positive, add the documented inline exemption **with a reason** —
do not bypass with `--no-verify` except in a real emergency.

---

## 7. The workflow

The maintainer runs a 12-phase workflow (`CLARIFY → DESIGN → REVIEW → PLAN → BUILD → VERIFY →
REVIEW → QC → POST-REVIEW → SESSION → COMMIT → RETRO`), enforced by `scripts/workflow-gate.py`.
It is documented in [`agentic-workflow/WORKFLOW.md`](agentic-workflow/WORKFLOW.md).

**You do not have to adopt it for an outside PR.** What is expected of any contribution:

1. **Open an issue first** for anything beyond a small fix — so scope is agreed before you build.
2. **One logical change per PR.** Stage the files you changed; no `git add -A`.
3. **Evidence in the PR body** — the actual command output, not "tests pass". For a new
   check, the red-then-green proof from [§4](#4-the-rules-that-get-prs-rejected).
4. **Say what you did not do.** A known gap stated plainly is welcome; a silent one is the problem.
5. **No deadline pressure exists here.** This is a hobby project with no ship date, so "good enough
   for now, we'll fix it later" is never the right trade. If something is worth fixing and you can
   fix it in scope, fix it.

Reviewers work from [`AGENTS.md`](AGENTS.md), not from taste.

---

## 8. What should I work on?

This is the question a clean codebase cannot answer on its own, so here is where the direction lives:

- **[`docs/sessions/SESSION_HANDOFF.md`](docs/sessions/SESSION_HANDOFF.md)** — the `▶ NEXT SESSION`
  block at the top is what is actively being built. The **Deferred Items** section below it is the
  honest backlog: known problems, why each was postponed, and what should trigger picking it up.
  **That list is the best source of contributable work.**
- **[`docs/ARCHITECTURE_WEAKNESSES.md`](docs/ARCHITECTURE_WEAKNESSES.md)** — known structural debt.
- **[`docs/standards/README.md`](docs/standards/README.md)** — has a *Known gaps* section.
- **GitHub Issues** — for anything not yet mirrored from the above.

Good first contributions: a deferred row you can close, a missing test for an existing rule, a
service README, or extending an existing gate's coverage. If you are unsure whether something is
wanted, open an issue and ask before building — that costs you five minutes and can save a weekend.

---

## 9. AI-assisted contributions

They are welcome, and the repo is set up for them. Point your assistant at
**[`AGENTS.md`](AGENTS.md)** — it is tool-neutral, and `CLAUDE.md` is a pointer to it. Shared agent
tooling under `.claude/commands/` and `.claude/skills/` is committed on purpose; per-developer
session state is git-ignored.

Two expectations, because this is where AI-assisted PRs usually fail review:

- **You are the author.** Review every line before you open the PR. "The model wrote it" is not a
  defence for a rule violation, and a PR whose author cannot explain its own diff will be closed.
- **Verify by effect, not by claim.** A model asserting that a test passes is not evidence. Run it,
  read the whole output, paste it. This repo has a documented history of checks that reported
  coverage while being incapable of failing — that is the specific failure mode to avoid.

---

## 10. License

LoreWeave is [AGPL-3.0-or-later](LICENSE). By contributing you agree your contributions are licensed
under the same terms. If you deploy a modified version as a network service, the AGPL requires you
to offer its source to users of that service.

---

Questions are welcome in Issues and Discussions — in any language. Thanks for being here.
