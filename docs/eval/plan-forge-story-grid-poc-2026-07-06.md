# D-PLANFORGE-STORY-GRID-POC — Story Grid vs the 7 core PlanForge rules (2026-07-06)

**Question answered:** `docs/specs/2026-07-05-narrative-forge/00_METHODOLOGY.md` decision #3
locked that Story Grid (or Truby, etc.) is **NOT a swap-in** for PlanForge's validator — the
current 7 rules are the trusted baseline, and any structure-framework addition needs its OWN
POC, scored side-by-side against the SAME fixtures the 7 rules already pass, before adoption is
even considered. This is that POC.

**Scope decision (kept honest):** no new spec fields were added to make Story Grid fit. Story
Grid (Shawn Coyne) is a large methodology — Five Commandments beat sequencing (Inciting Incident
/ Progressive Complications / Crisis / Climax / Resolution) and genre-level obligatory scenes
both need a `beat_type`/scene-role field the current `NovelSystemSpec` schema does not carry.
Adding that field would no longer be "the same fixtures" comparison the decision asked for — it
would be inventing a new fixture. So this POC operationalizes only the two Story Grid principles
that are mechanically checkable against the CURRENT schema (`events[].var_deltas`, `arcs[]`):

- **`sg_value_shift_per_scene`** — Story Grid's foundational unit test: a scene that doesn't turn
  a value at stake isn't a scene. Checked as: does every event in the arc under test carry at
  least one `var_delta`?
- **`sg_negative_turn_exists`** — Story Grid rejects a monotonically-positive arc: the value at
  stake must swing both ways (a cost alongside a gain), or there's no real dramatic tension.
  Checked as: does the arc's `var_deltas` include at least one cost-coded variable (`CD`, or a
  decreasing `HA`) alongside at least one gain-coded one (`PA`)?

**Harness:** `services/composition-service/app/engine/plan_forge/validate_story_grid.py`
(`run_story_grid_rules`, `format_story_grid_report`) + 8 unit tests in
`tests/unit/test_plan_forge_story_grid.py`. Deliberately **NOT** imported by
`validate.run_rules` / `validate_golden` — this stays a side-by-side comparison module until a
human decides to wire it, per the locked decision.

## Result — run against the same `story-plan-v1.md` fixture + `arc_2` the 7 core rules use

```
# Story Grid POC — side-by-side vs core PlanForge rules

## Core rules (existing 7, unchanged baseline)

- `vars_four`: PASS — codes=['CD', 'HA', 'PA', 'THR']
- `pa_not_realm`: PASS —
- `arc2_discovery`: PASS — Arc khám phá và trả giá — không phải arc sức mạnh
- `anchors_min`: PASS — count=6
- `thr_no_early_explain`: PASS —
- `open_questions_preserved`: PASS — count=8
- `premise_max`: PASS — chars=747
- `notes_linked`: PASS — ratio=1.00

## Story Grid rules (POC, not wired into the real gate)

- `sg_value_shift_per_scene`: FAIL — events_without_value_shift=['arc_2_event_3', 'arc_2_event_7']
- `sg_negative_turn_exists`: PASS — has_cost=True has_gain=True

**Finding: Story Grid surfaces 1 gap(s) the current 7 rules do not check.**
```

**All 7 core rules pass, as expected** (nothing about this POC touches them). **One of the two
Story Grid rules finds a real gap the current 7 rules never checked**: `arc_2_event_3` (Thử
Nghiệm) and `arc_2_event_7` (Quyết Định Tiếp Tục) parse with zero `var_deltas` — plot beats that
exist in the story plan but never move a tracked value. Nothing in the current 7 rules (variable
presence, PA/realm coupling, arc-kind, anchor count, THR-early-explain, open-question count,
premise length, notes-link ratio) checks per-event value movement at all — this is a genuinely
new axis, not a re-statement of an existing rule.

`sg_negative_turn_exists` passes: Event 6's `CD +1` (Corruption_Debt, a cost) sits alongside
Event 2/5's `PA` gains — the arc already has real dramatic cost, not just a power-up ladder. This
is a useful confirmation, not a novel finding (nothing currently regresses it), but it establishes
the rule actually discriminates (see negative test below), rather than being vacuously true.

## A real, pre-existing parsing bug found and fixed while building this (not a Story Grid defect)

Building the POC surfaced a genuine bug in the existing rules-based parser
`app/engine/plan_forge/propose.py::_parse_events_in_block`. It splits an arc's markdown body on
`\n### ` to find event boundaries, but the **last** event in a block has no following `### ` to
stop at — its body ran all the way to the arc's closing `**Trạng thái cuối Arc N:**` summary
bullet list. That summary text literally contains "THR: rò rỉ đầu tiên", which spuriously matched
the `THR` var_delta regex — before the fix, `arc_2_event_7` incorrectly showed a `THR +leak`
delta that has nothing to do with Event 7's actual content (a decision beat, not a past-life-seed
beat). Root-caused as a body-boundary bug (fixed by truncating each event's parsed body at the
first `\n---` marker — the document's own section-separator convention), not anything Story Grid
specific. Fixed in the same commit; all 40 `plan_forge` unit tests + full composition suite
(1636 passed / 150 skipped) green after the fix. Without this fix, the POC's own baseline data
would have been wrong (falsely making `sg_value_shift_per_scene`'s gap look like 1 event instead
of the real 2).

## Negative-test discrimination (same convention as the golden fixture's `negative_tests`)

- `sg_value_shift_per_scene` correctly flips to PASS when every arc_2 event is patched to carry a
  synthetic delta (`test_sg_value_shift_passes_when_every_event_has_a_delta`).
- `sg_negative_turn_exists` correctly flips to FAIL when the only cost-coded delta (`CD`) is
  stripped from the spec, leaving an all-gain arc (`test_sg_negative_turn_fails_when_all_deltas_are_gains`).

Both rules discriminate real signal, not fixture noise.

## Conclusion

**Recommendation: `sg_value_shift_per_scene` is a strong candidate for an 8th core rule** — it
caught a real, pre-existing gap in the fixture that had gone unnoticed through 7 existing rules
and a full unit-test suite. `sg_negative_turn_exists` is a weaker candidate on its own (it never
fires on this single fixture beyond the contrived negative test) but costs nothing to keep as a
guard against a future "monotonic power fantasy" regression drift.

**Not adopted in this commit** — per the locked decision, adoption is a separate call for whoever
next revisits PlanForge's validator, not assumed by this POC. If adopted, the two events flagged
by `sg_value_shift_per_scene` (`arc_2_event_3`, `arc_2_event_7`) are real story-plan gaps worth
fixing in the fixture itself (Event 3's "Thử Nghiệm" and Event 7's "Quyết Định" both plausibly
deserve a var_delta — a small PA or CD nudge — on narrative grounds, independent of this rule).

**Not pursued in this POC** (genuinely out of scope, not silently dropped): the Five
Commandments' beat-sequencing rules and genre-level obligatory scenes — both need a
`beat_type`/scene-role field the spec doesn't have. If Story Grid is adopted for
`sg_value_shift_per_scene`, extending to beat-sequencing is the natural next POC, scoped
separately (it would need real fixture/schema design, not just a new rule function).

**Superseded by the addendum below** — the recommendation above was based on a single
generation method (the regex-only parser). Read the addendum before acting on it; the refined
recommendation is at its end.

## Addendum (2026-07-06, same day) — cross-validated against a REAL LLM propose run + a real
## false-positive found in an EXISTING core rule

User: "approve, now do more evaluate before we consider to update current validator." Since both
Story Grid rules are deterministic/mechanical (no LLM judge involved, unlike the canon-check
gate), the "more evaluation" a mechanical rule needs isn't judge-accuracy scoring — it's
**checking the rule against more than one spec-generation method**, since the whole POC above
only ever exercised the regex-only `propose_spec` (its own docstring: "rules-first; fixture-quality
for POC" — never claimed production-representative). The REAL production path is the async LLM
propose (`propose_spec_llm_async` / `ProviderPlanForgeLLM`, used by the actual worker). This
addendum runs that REAL path — real provider-registry route, real BYOK local model (Gemma-4
26B-A4B QAT 200K, $0, the test account's already-provisioned model), real story-plan-v1.md
fixture, zero mocking — and reruns both the 7 core rules and the 2 Story Grid rules against its
output.

**Per-event var_delta comparison, regex-parser spec vs real LLM-produced spec:**

| Event | Regex-parser spec | LLM-produced spec |
|---|---|---|
| e2_1 Nhập Môn | `HA hold=100` | **none** |
| e2_2 Biến Hóa Đầu Tiên | `PA +1` | `PA +1` |
| e2_3 Thử Nghiệm | **none** | **none** |
| e2_4 Dị Thường Đầu Tiên | `THR +leak` | **none** |
| e2_5 Tiểu Thành | `PA +large` | `PA large_increase` |
| e2_6 Tác Dụng Phụ Đầu Tiên | `CD +1` | `CD increase_first_time` |
| e2_7 Quyết Định Tiếp Tục | **none** | **none** |

**Key finding — the signal splits into a robust half and a noisy half.** `e2_3` and `e2_7` have
**no var_delta under BOTH independent generation methods** — a crude regex parser AND a real LLM
both materialize these two events without touching a tracked variable. That is a much stronger
basis for "this is a real authoring gap" than the original single-method POC could support. `e2_1`
and `e2_4`, by contrast, only fail under ONE method each (regex catches `e2_1`'s literal "HA = 100"
and `e2_4`'s literal "THR" mention; the LLM materializes neither) — this is **generation-method
noise, not a stable signal**, and would be a bad thing to hard-block on. Practical read: on this
fixture, `sg_value_shift_per_scene` flags **4/7 events with the LLM path** vs 2/7 with the regex
path — trust the intersection (`e2_3`, `e2_7`), treat the rest as "worth a human glance," exactly
why this stays advisory/quarantine-tier and not hard-block if ever adopted (same taxonomy tier as
the canon-check gate and Enrichment's H0 — see `docs/specs/2026-07-05-narrative-forge/00_METHODOLOGY.md`
§4.2).

**A caveat made concrete, not just asserted:** `sg_value_shift_per_scene` can only ever see shifts
in the spec's OWN tracked variables (PA/HA/CD/THR for this story). A scene with obvious dramatic
value shift on an untracked axis (e.g. a trust betrayal) still reads as a "gap" — this is a scope
limit, not a bug. Encoded as an executable regression test,
`test_sg_value_shift_blind_to_untracked_narrative_value`, so this caveat can't silently rot.

**A real false-positive found in an EXISTING core rule (`pa_not_realm`), NOT a Story Grid
finding — surfaced only because this addendum ran a real LLM for the first time:**
`pa_not_realm` fails on the LLM-produced spec. Cause: event `e2_5`'s `PA` delta carries
`coupled_to_realm: false` (correct — the LLM followed the prompt's explicit rule) but its
`reason` field reads `"Đột phá cảnh giới đầu tiên"` ("first realm breakthrough") — and
`pa_not_realm`'s second heuristic string-matches `"cảnh giới"` (realm) anywhere in a PA delta's
`reason` text, regardless of the `coupled_to_realm` boolean. That heuristic conflates two
different things: "PA rises *because of* a realm-breakthrough *experience*" (legitimate — this
story's OWN design explicitly lists "một lần đột phá... cảnh giới" as a PA trigger event) vs "PA
rises *proportionally with* realm" (the actual forbidden coupling). Every unit test exercising
`pa_not_realm` before this addendum used either the regex-parser spec (which never generates this
phrasing) or a synthetic negative-test patch — **this is the first time `pa_not_realm` was ever
checked against real LLM output, and it produces a false positive.** Not fixed here — this is a
different, existing core rule, not Story Grid, and the correct fix (distinguish
trigger-experience wording from actual-coupling wording without simply deleting the keyword
check) needs its own considered pass, not a same-session regex tweak. Tracked as
**`D-PLANFORGE-PA-REALM-FALSE-POSITIVE`** in `docs/sessions/SESSION_HANDOFF.md` Deferred Items.

## Revised conclusion (supersedes the single-method conclusion above)

- **`sg_value_shift_per_scene`: still a good candidate, but scope the trusted signal to
  cross-method agreement** (this fixture: `e2_3`/`e2_7`), not every method-specific FAIL — a
  single-method run overstates the finding, mirroring the `canon-check` judge-eval lesson
  (`docs/eval/canon-check-judge-2026-07-06.md`) that one run understates true noise. If adopted,
  must be `quarantine`/`advisory`, never `hard-block`, precisely because of this noise floor.
- **`sg_negative_turn_exists`: unchanged** — still passes on both specs, still only discriminates
  via the contrived negative test. Low-cost regression guard, not a strong finding either way.
- **The bigger discovery isn't about Story Grid at all**: the existing 7-rule validator had NEVER
  been checked against a real LLM-produced spec before this addendum — only the regex-parser
  spec and synthetic patches. That gap let a real false positive (`pa_not_realm`) go unnoticed.
  **Recommendation for whoever next touches PlanForge's validator: add a real-LLM-path smoke
  test (even just golden-comparison, not full CI) for the EXISTING 7 rules before adding an 8th —
  the validator's blind spot toward its own production path is a bigger risk than which
  literary framework supplies rule #8.**
