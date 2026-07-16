# PlanForge — "Run to next checkpoint" (coverage gap H2)

> **Status:** detail spec (design). NOT built. Origin: S3 coverage run found that reaching the end of
> the 7-pass compiler is **7 manual `run…` clicks + 2 checkpoint approvals** — real friction for a
> long book. The obvious fix ("run everything") has genuine design questions (batch cost, stop
> conditions, partial failure), so it earns a spec rather than a blind build.

## 1 · The gap
The rail runs passes one at a time. To go from a compiled package to a full scene plan an author must:
run motifs → run cast → (approve cast) → run world → run beats → (approve beats) → run character_arcs
→ run scenes → run self_heal. That is a lot of clicking + waiting, and the author must know which pass
is runnable next. The compiler already knows the dependency order (`PASS_ORDER` + `blockers_for`) — it
can advance itself to the next point where a **human is actually needed** (a blocking checkpoint).

## 2 · What "run to next checkpoint" means
A button "**Run to next checkpoint**" that, from the current cursor, runs each **runnable, advisory**
pass in `PASS_ORDER`, stopping when it reaches:
- a **blocking** pass that is not yet accepted (cast/beats) — the human must review it, OR
- a pass whose upstream is stale/unaccepted (it can't run yet — should not happen mid-sequence), OR
- a **pass failure**, OR
- the **end** (self_heal done).

So one click can take the author motifs→cast (stop, review cast), then after approving cast, one click
world→beats (stop, review beats), then after beats, one click char_arcs→scenes→self_heal (done). The
2 human decisions stay; the 7 mechanical runs collapse to 3 clicks.

## 3 · Design questions (why this is a spec, not a build)

### OQ-1 — batch cost confirm
Each pass is a paid LLM call. The per-pass PS-6 confirm doesn't fit a batch. Options:
- **A (recommended):** ONE batch confirm before the sequence — "Run up to N passes · ~N LLM calls ·
  model X" with the model picker, then run without further per-pass confirms until it stops. Matches
  the author's intent ("go until you need me").
- **B:** confirm each pass anyway (defeats the purpose).
The **paid=true / no-estimate** rule (F-P8) means there is no cost *estimate* — the confirm states the
call count + model, not a dollar figure (same as the per-pass confirm today).

### OQ-2 — stop-at-blocking is the core contract
The loop MUST stop at a blocking checkpoint (never auto-approve — that would defeat PF-6, the whole
point of the human gate). Confirm the stop is on `checkpoint == 'blocking' && not accepted`, computed
from the fresh ledger after each pass (freshness re-derives between passes — the ledger is the truth).

### OQ-3 — partial failure
If pass k fails mid-sequence: stop, surface the error, leave passes 1..k-1 completed (they are real
artifacts). The author fixes (re-run k, or repair) and clicks "Run to next checkpoint" again. Do NOT
roll back completed passes (they are valid; PF-3 freshness handles any re-stale).

### OQ-4 — where the loop runs
- **FE-orchestrated (recommended):** the rail calls `run_pass` sequentially, re-reading the ledger
  after each, stopping per §2. Simple, cancellable, visible progress; no new backend. The cost: the
  browser must stay open for the sequence (acceptable — the author is watching).
- **BE-orchestrated:** a new `run_to_checkpoint` route/worker op. More robust (survives a closed tab)
  but a new async surface + a new MCP tool (MCP-first) + progress streaming. Heavier.
Recommend **FE-orchestrated v1**; promote to a BE op only if authors want fire-and-forget.

### OQ-5 — UX
A progress line ("running world… 3 of 7") + a **Cancel** (stop after the current pass). On stop,
scroll/focus the pass that needs the human (the blocking checkpoint) so the next action is obvious.

## 4 · Acceptance criteria
1. From a compiled run with 0 passes, "Run to next checkpoint" runs motifs+cast then STOPS at cast
   (blocking, pending) — a live smoke asserting cast is `completed/pending` and world did NOT run.
2. After approving cast, the button runs world+beats then STOPS at beats.
3. After approving beats, the button runs char_arcs+scenes+self_heal to the end (cursor 7).
4. A mid-sequence pass failure stops the loop, surfaces the error, and leaves prior passes completed.
5. ONE batch confirm (not per-pass) gates the whole sequence (OQ-1 A).
6. Cancel stops after the current pass; the ledger is consistent.

## 5 · Effort / risk
S–M (FE-orchestrated). Risk is entirely in the OQs above — decide OQ-1 (batch confirm) and OQ-4
(FE vs BE) before building. No migration, no new tenancy surface (reuses run_pass's gates).
