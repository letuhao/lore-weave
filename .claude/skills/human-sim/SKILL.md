# /human-sim — simulate a human user against the running product

Drive real user journeys through the live UI as a named persona, and report what a person
would actually hit. Reusable: add a persona or a journey, run it, keep it.

## What this is for, and what it is not

A simulated user that clicks around and reports impressions is noise — nobody can act on
*"the search felt confusing"* and nothing can go red. **A journey here ends in a claim that
can be FALSE.** That is the whole difference, and it is why this lives in the Playwright
suite rather than in a chat transcript.

Prior art: [UXAgent](https://github.com/neuhai/uxagent) (CHI 2026) runs LLM agents as
usability-testing participants with a persona generator and its own browser connector. The
**shape** is borrowed — persona → journey → trace → findings. The dependency is not: this
repo already has Playwright, a live stack, testid conventions and an e2e harness, and
UXAgent's own Chrome layer would fight all four.

## The two personas, and why they are these two

| persona | starting state | what it catches |
|---|---|---|
| `newcomer` | fresh account, genuinely empty, onboarding unseen | empty states, dead ends, unexplained vocabulary |
| `frequent` | stable account seeded to ≥25 books, past onboarding | **scale** — pagination, truncation, search that only reads page one |

**The scale field is load-bearing, not decoration.** On 2026-08-30 this repo fixed a defect
where a user with 83 books searched their library by title and got nothing: the page loaded
20 rows, displayed the true total of 83, and filtered those 20 in the browser. The book sat
at rank 32. It was recorded for six days as *"book search is broken for Vietnamese
diacritics"* because the queries that happened to work were for recent books.

**Below 21 books that defect does not exist.** A persona suite on a fresh account walks that
journey, finds its book, and reports success forever. So `minBooks` is declared per persona
and **enforced** — `ensureScale` seeds up to it and fails rather than proceeding.

Each persona owns its **account** for the same reason. The first version borrowed the shared
developer login; a "newcomer" on an account with 83 books and completed onboarding is not a
newcomer, and every empty-state claim it made was vacuous.

## Run

```bash
cd frontend
PLAYWRIGHT_BASE_URL=http://localhost:25174 \
  npx playwright test tests/e2e/specs/persona-journeys.spec.ts --reporter=list
```

`25174` is the `lw-iso` frontend. **These journeys WRITE** — they register accounts and seed
books — so `assertDisposableTarget` refuses any non-loopback target. Point it at a shared or
real deployment and it fails closed rather than creating junk accounts under someone else's
domain.

Rebuild the image first if you are testing your own change; the container serves a baked
build, so an un-rebuilt frontend silently tests the previous commit:

```bash
bash infra/iso.sh build frontend && bash infra/iso.sh up -d frontend
```

## Adding a persona or a journey

Personas live in `frontend/tests/e2e/personas/types.ts`; journeys are Playwright tests in
`frontend/tests/e2e/specs/persona-journeys.spec.ts`.

Every expectation carries a `because`. That is a requirement, not a style note: **an
assertion nobody can justify is how a suite ends up pinning a bug in place.** If the only
reason for an expectation is "that is what the code does today", it is not a user
expectation and it does not belong here.

Three rules that came out of building this:

1. **Search for something OLD.** Searching for the most recently created item cannot
   distinguish a working search from one that reads only the first page — which is exactly
   how the original defect survived every test written against it.
2. **Assert the request, not just the render**, when the behaviour is "this reaches the
   server". A filter that never leaves the browser is the defect; a rendered list alone
   cannot tell the two apart.
3. **Say what a failure means to the user.** Playwright prints the assertion message, so
   write it as the person's sentence: *"this book is one of your 25 and was searched by its
   exact title; not finding it tells you it does not exist."*

## Calibration — does it actually catch anything?

Yes, and it is checked rather than claimed. Re-introducing the search defect (dropping `q`
from the frontend call) and rebuilding makes the `frequent` journey fail with the message
above, while `newcomer` keeps passing — the failure is specific, not a blanket break. Any
new journey should be calibrated the same way: **break the thing it claims to protect and
watch it go red**, or you have written a check that cannot fail.

## What this found on its first run

Two things, neither of which was the journey's subject:

- **A newly registered user lands on `/onboarding`, not `/books`.** Correct product
  behaviour, and the shared `loginViaUI` helper hard-codes the books URL — an assumption
  that only ever described an account someone had already onboarded by hand.
- **The library search input had no `data-testid`**, so it could only be reached by its
  translated placeholder — which E2E CONVENTIONS §1 exists to prevent, on a product whose
  UI language changes.
