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
