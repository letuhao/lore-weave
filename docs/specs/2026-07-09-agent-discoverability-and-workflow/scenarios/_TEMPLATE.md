# S0x · <Scenario title> — <one-line job in the user's words>

> **BLACK-BOX RULE (read first).** A scenario is written entirely from the chair of a user who does
> **not** know this platform — no tool names, no "workflow", no "kind/attribute/entity", no modes, no
> mechanism. It contains only: what the user *wants*, what the user *does* (types/clicks), and what the
> user can *see and verify*. Success/failure is judged on the **observable outcome**, never on which
> internal tool fired. The internal happy-path goes in §8 **Builder hint** and is explicitly
> **non-binding** — the assistant may reach the outcome any way; §8 is a guess for implementers and may
> be wrong. If you find yourself writing "the assistant should call X" anywhere in §1–§6, you've slipped
> into white-box — move it to §8.
>
> Why: the platform's core failure is that it was *designed* assuming the caller knows the internals.
> A white-box test re-encodes that assumption and passes while real users fail. This template forces the
> test to fail the way users fail.

| Field | Value |
|---|---|
| **Scenario id** | S0x |
| **Maps to umbrella workflow** | W0x (`<slug>`) — see [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) §5 |
| **Persona** | P1 Mai (author) · P2 Linh (worldbuilder) · N-* newcomer |
| **Surface** | chat / editor / book / studio |
| **Model under test** | `gemma-4-26b-a4b-qat` (mid-tier local) |
| **Fixture** | book Mị Đế (or: …) |
| **Status** | ⬜ drafting · 🔬 baseline-captured · 🔧 building · ✅ passing |
| **Owner** | (session/branch) |

## 1. Who I am (the unknown user)

- **Persona + mental model:** who I am, how much I know (assume little), why I'm here.
- **The words I actually use:** the plain phrases I'd type.
- **Words I do NOT know (must never be required of me):** e.g. *ontology, kind, attribute, entity,
  workflow, extraction, tool, mode, confirm-token*. If the assistant needs me to say any of these to
  succeed, that is a scenario failure.

## 2. What I'm trying to get done

One short paragraph, in my words. The outcome I want — not the steps.

## 3. What I have / where I'm starting

Only what I can perceive: which book/screen I'm on, whether I already have anything (chapters? a seed
doc I can paste?). No internal preconditions ("a knowledge project must exist") — if the system needs
that, *it* must handle it, and if it can't, that's a finding.

## 4. What I do and what I expect to see (my side only)

Two columns. **No assistant internals.** "I type / I click" and "I expect to see" (an observable
response or end state I can point at).

| # | I say / do | I expect to see |
|---|---|---|
| 1 | "<what I actually type>" | a response that makes sense to me + visible progress toward my goal (or a sensible clarifying question) |
| 2 | "<my reply>" | … |
| … | | the thing I wanted, visibly done, where I'd look for it |

## 5. How I'll know it worked (my success test) — and how I'll know it failed

- **Worked (I can verify without help):** the concrete thing I can open/see — e.g. "I open the glossary
  and my 5 characters are there with their details." State it as *I* would check it.
- **Failed (what I'd experience):** it keeps "searching / thinking" and nothing appears · it tells me it
  can't do a thing I know it should · it asks me to name something I don't know · it says "done" but I
  don't see anything · it makes a mess I didn't ask for · it takes so long I give up.

## 6. Acceptance (observable, from my chair)

The scenario passes only if, with gemma on the real GUI:
- [ ] **My goal is actually achieved and I can verify it myself** (restate the §5 "worked" check).
- [ ] **No rescue needed** — I never had to know a tool/feature name, paste an id, or rephrase into
      platform jargon to get there.
- [ ] **No visible thrashing** — the assistant doesn't spin/repeat "searching" with nothing to show; it
      makes steady progress or asks one sensible question. *(Evidence to record, not the spec: #
      internal discovery calls, wall-clock — a run that thrashes even if it eventually succeeds is a
      degraded pass, noted.)*
- [ ] **Honest** — it doesn't claim success without the result existing, and it surfaces real blockers
      plainly.
- [ ] Finishes within a time I'd tolerate (state a ceiling).

## 7. Baseline — what actually happens TODAY when I try (fill via live test)

Run it against the current system with gemma, as this user, and record reality:
- **Date / stack / model_ref:** …
- **What I experienced:** (paste the turns as the user sees them)
- **Did I get my goal?** yes / partial / no · **Where it broke for me:** …
- **Evidence (instrumented):** # discovery calls, wall-clock, whether it thrashed/gave up.
- **Transcript saved at:** `docs/eval/discoverability/YYYY-MM-DD-S0x-gemma.md`
- **Verdict:** ❌ / ⚠️ / ✅

## 8. Builder hint (NON-BINDING — not part of acceptance)

> Implementers only. A hypothesized internal happy-path + the capabilities it implies. The assistant is
> free to reach §5's outcome any other way; do not test against this. This section may be wrong — if the
> real path differs, that's fine as long as §6 passes.

- Likely capabilities involved (tools/workflows/skills), the rough order, known gotchas.
- Maps to umbrella phase(s): …
- Any **new backing capability** this outcome seems to require (flag it as a feature, not a recipe).

## 9. Re-test gate

After the build, re-run §4 as this user; ✅ only when §6 all checks with gemma. Save the passing
transcript beside the baseline. Record separately whether a residual failure is a mid-tier-model ceiling
vs. a real product gap.
