# /human-sim — the evidence tools

Three pieces, added 2026-09-04. They exist because a human-simulation run's output is a
**judgement** ("did the assistant write five coherent chapters"), and a judgement needs evidence
a person can re-read. The default Playwright config captures nothing on a passing run.

---

## 1. `x-trace-id` — find a click in the logs

**The backend half was always there.** Every Python service reads `x-trace-id` off the incoming
request and reuses it when it matches `^[A-Za-z0-9._-]{1,128}$`, minting a fresh one otherwise
(`middleware/trace_id.py`). **Nothing was sending it**, so locating "the log lines for the click
that failed" meant `docker logs --since 2m` across a dozen containers and hoping nothing else
overlapped — which, on a stack with outbox relays and a scheduler, is a hope rather than a method.

`frontend/src/lib/traceId.ts` + `frontend/src/api.ts` now stamp every `apiJson` call. A test pins
one id per step via `window.__LW_TRACE_ID__`; outside a test each request gets its own, which is
still worth having when a user reports one failed action.

**The id carries a LABEL on purpose.** `write-ch3.9f2a1c…` is greppable by eye across a dozen
containers in a way a bare hex string is not. The label is a slug the test chooses — it reaches
every service's log at info level, so **never put a book title, an email or an account id in it.**

---

## 2. `collect_run_evidence.py` — the logs for one step

```bash
# one step, exactly
python scripts/e2e/collect_run_evidence.py --trace write-ch3.9f2a1c4b --out evidence/ch3

# every step of a run (the label prefix)
python scripts/e2e/collect_run_evidence.py --label newbook-5ch --out evidence/run

# no correlation available — a time window, and it says so
python scripts/e2e/collect_run_evidence.py --since 10m --out evidence/window

# the other stack
python scripts/e2e/collect_run_evidence.py --label newbook-5ch --project infra --out evidence/run
```

Writes `<service>.log` per container, a `timeline.log` merged in timestamp order, and a
`manifest.json` with per-service line counts.

🔴 **A correlated ask that matches nothing exits 2, not 0.** An empty file and a green exit would
say "the step was clean" when it may mean the frontend image predates the header, the id was
never pinned, or the id was malformed and silently replaced server-side. The failure message
names those three in the order worth checking. This repo has already shipped a gate that
"reported a clean scan of nothing"; that is the failure this floor exists to prevent.

It does **not** parse or judge the lines. A collector that decided what counted as an error would
be a second opinion nobody asked for, and would hide the line it did not recognise.

### Which services actually put the id in their logs — measured, not assumed

| service | logs the trace id? | how it behaves |
|---|---|---|
| knowledge-service | **yes** | structured JSON: `"trace_id": "toolproof2.1788…"` |
| composition-service, lore-enrichment | middleware present | same JSON logger family |
| **chat-service** | **no** | plain uvicorn text. Its middleware is real and registered — it adopts the inbound id, echoes it on the response, and **forwards it to downstream httpx clients** — but the service ships no structured logger, which its own docstring says outright: *"Chat-service does not currently ship a structured JSON logger… A future logging overhaul can pull the ContextVar without touching this file."* |
| book-service, auth-service (Go) | **no** | accept the header, do not echo it into log lines |

**This is not a defect and it is not a hole in the correlation.** A chat turn's id travels WITH
the request into knowledge-service, so the interesting work still lands in a searchable line —
you just will not find `GET /v1/chat/sessions` itself by trace id.

**What it means when you collect:** a chat-only step legitimately returns few or no lines, and
that is the one case where the exit-2 floor can mislead. Collect the whole run by `--label` and
read the timeline, rather than asking for a single chat step and concluding the step was silent.

---

## 3. `humanRun.ts` — a step recorder with snapshots

```ts
import { startHumanRun } from '../helpers/humanRun';

test('a newcomer writes five chapters', async ({ page }, testInfo) => {
  const run = startHumanRun(page, 'newbook-5ch', testInfo);

  await run.step('open studio', async () => { /* … */ });
  await run.step('create book', async () => { /* … */ }, 'title is throwaway-dated');
  await run.step('ask for chapter 1', async () => { /* … */ });

  // run.steps[] carries { name, traceId, screenshot, ms } — feed the traceIds to the collector.
});
```

- **A snapshot per step, pass or fail**, full-page, into `testInfo.outputDir/human-run-<label>/`.
- **The snapshot is still taken when the step throws**, and the error is recorded on the step
  before being re-raised. A run that dies at step 4 of 9 should leave the picture of step 4.
- `run.json` is rewritten after **every** step, so a run killed mid-way still leaves its record.
- Snapshots are **not** assertions. Nothing compares them to a golden image — a visual baseline
  nobody looks at goes stale and then fails for reasons unrelated to the change. These exist to
  be read.

---

## Which stack, and why it matters more than it looks

| stack | frontend | BFF | credentials | notes |
|---|---|---|---|---|
| `infra` | `:5174` | `:3123` | `docs/dev/LOCAL_TEST_ENV.md` (git-ignored) | the documented account; provider models configured here |
| `lw-iso` | `:25174` | `:23123` | **not the documented ones** | the isolated stack; AGE overlay lives here |

**The documented account does not log in to `lw-iso`.** `LOCAL_TEST_ENV.md` §4 says "FE/BFF on
:5174" — it describes `infra`. Pointing a journey at `:25174` with those credentials returns
`AUTH_INVALID_CREDENTIALS`, which reads like a broken login and is a wrong-stack error.

**A fresh account cannot write prose.** `freshAccount()` is right for empty-state journeys and
wrong for anything that generates: provider credentials and default models are per
`owner_user_id`, so a newly registered user has no model and the assistant has nothing to write
with. For a generation journey, use the documented account and create a **throwaway book** —
the constraint is that no run writes into a book someone cares about, not that the account is new.

**Rebuild before you believe a result.** Both stacks serve a baked build. A journey run against
an un-rebuilt image tests the previous commit and looks exactly like a passing regression test:

```bash
cd infra && docker compose -p infra -f docker-compose.yml build frontend chat-service
docker compose -p infra -f docker-compose.yml up -d --no-deps frontend chat-service
```

Then **verify the image, not the build log** — `docker exec <container> grep -c <a string only
your change contains> <the file>`. A green build says the image was made, not that the running
container is it.

---

## Cost

Generation journeys call the configured models. On this machine every default resolves to
**`lm_studio` on `localhost:1234`** — verify before a long run rather than assuming:

```sql
select d.capability, m.provider_kind, m.provider_model_name
from user_default_models d join user_models m using (user_model_id);
```

Anything not `lm_studio` (or a local endpoint) **spends money**, and a five-chapter run is not a
small number of calls. Check first, and say the expected call count out loud before starting.
