"""#323 Codex review — whole-section refine targets must round-trip.

`PlanForgeService.self_check` (PR #323) maps the hard compile gates to REAL spec
sections (`spec_has_arc` -> `arcs`, `spec_has_events` -> `events`), and
`handoff_autofix` feeds those paths to `refine` as `focus_paths`. But the two
consumers of `focus_paths` only understood per-item paths (`events[<id>]`,
`layers.characters[0]`, `layers.mechanics[<id>]`):

* `spec_slice_for_paths` returned `{}` for `events` / `arcs`, so the model was
  asked to repair a plan it was never shown;
* `merge_refine_output` silently dropped a section-shaped patch for those
  paths, so even a correct repair never landed.

These tests exercise the slicer and the merger directly (not a mocked `refine`
call): a whole-section target must survive slice -> patch -> merge.
"""

import json

from app.engine.plan_forge.propose_llm import normalize_spec
from app.engine.plan_forge.refine import (
    accept_refine,
    artifact_json_for_refine,
    merge_refine_output,
)
from app.engine.plan_forge.spec_index import spec_slice_for_paths
from app.engine.plan_forge.validate import run_rules

_SPEC = {
    "arcs": [
        {"id": "arc_1", "title": "Arc One"},
        {"id": "arc_2", "title": "Arc Two"},
    ],
    "events": [
        {"id": "ev_1", "arc_id": "arc_1", "title": "First", "synopsis": "s1"},
        {"id": "ev_2", "arc_id": "arc_2", "title": "Second", "synopsis": "s2"},
    ],
    "layers": {"characters": [{"name": "Mara"}], "mechanics": []},
}


def test_slice_whole_events_section():
    blob = spec_slice_for_paths(_SPEC, ["events"])
    out = json.loads(blob)
    assert [e["id"] for e in out["events"]] == ["ev_1", "ev_2"], (
        "the whole events section must reach the refine prompt — '{}' means the "
        "model is asked to repair a plan it was never shown (#323)"
    )


def test_slice_whole_arcs_section():
    blob = spec_slice_for_paths(_SPEC, ["arcs"])
    out = json.loads(blob)
    assert [a["id"] for a in out["arcs"]] == ["arc_1", "arc_2"]


def test_artifact_json_for_refine_whole_section_is_not_empty():
    blob = artifact_json_for_refine(_SPEC, {"focus_paths": ["events"]})
    assert "ev_1" in blob and blob.strip() != "{}", (
        "artifact_json_for_refine with focus_paths ['events'] must carry the "
        "section, not an empty object (#323)"
    )


def test_merge_whole_events_section():
    before = json.loads(json.dumps(_SPEC))
    patched_events = [
        {**before["events"][0], "synopsis": "repaired synopsis"},
        before["events"][1],
        {"id": "ev_3", "arc_id": "arc_1", "title": "Third", "synopsis": "s3"},
    ]
    merged = merge_refine_output(before, {"events": patched_events}, {"focus_paths": ["events"]})
    assert merged["events"] == patched_events
    assert merged["arcs"] == before["arcs"]
    assert merged["layers"] == before["layers"]


def test_merge_whole_arcs_section():
    before = json.loads(json.dumps(_SPEC))
    patched_arcs = [{**before["arcs"][0], "title": "Arc One (repaired)"}, before["arcs"][1]]
    merged = merge_refine_output(before, {"arcs": patched_arcs}, {"focus_paths": ["arcs"]})
    assert merged["arcs"] == patched_arcs
    assert merged["events"] == before["events"]


def test_merge_ignores_sections_outside_focus():
    # The merger only applies what the revision focused on — an events patch must
    # not leak in when the focus was arcs alone.
    before = json.loads(json.dumps(_SPEC))
    patch = {
        "events": [{**before["events"][0], "synopsis": "should not land"}],
        "arcs": [{**before["arcs"][0], "title": "Arc One (repaired)"}, before["arcs"][1]],
    }
    merged = merge_refine_output(before, patch, {"focus_paths": ["arcs"]})
    assert merged["events"] == before["events"]
    assert merged["arcs"][0]["title"] == "Arc One (repaired)"


def test_section_round_trip_slice_patch_merge():
    # Slice -> model patch (section-shaped) -> merge, with no mocked refine in
    # between: the repair a model produces from the slice must land in the spec.
    before = json.loads(json.dumps(_SPEC))
    sliced = json.loads(spec_slice_for_paths(before, ["events"]))
    patched = dict(sliced)
    patched["events"] = [
        {**sliced["events"][0], "synopsis": "redistributed into arc_1"},
        sliced["events"][1],
        {"id": "ev_9", "arc_id": "arc_1", "title": "New", "synopsis": "s9"},
    ]
    merged = merge_refine_output(before, patched, {"focus_paths": ["events"]})
    assert [e["id"] for e in merged["events"]] == ["ev_1", "ev_2", "ev_9"]
    assert merged["events"][0]["synopsis"] == "redistributed into arc_1"


# ── #323 Codex review, round 2 ───────────────────────────────────────────────
# F4 — a whole-section slice was still cut at 12,000 chars, so for a 30-event
# arc_1 the model received truncated (unparseable) JSON, and the whole-section
# merge then silently dropped every event past the cut while accept_refine —
# which only guards arc_2 titles/counts — accepted the loss. A section that
# will be replaced wholesale must reach the model whole.
def _large_spec(n_events: int = 30) -> dict:
    return {
        "version": 1,
        "meta": {"title": "STORY PLAN"},
        "charter": {"consistency_anchors": ["a1", "a2"], "forbids": [], "style_constraints": []},
        "layers": {"characters": [{"name": "Mara", "traits": ["calm"]}], "mechanics": [], "variables": []},
        "arcs": [
            {"id": "arc_1", "title": "Arc One", "arc_kind": "setup"},
            {"id": "arc_2", "title": "Arc Two", "arc_kind": "discovery"},
        ],
        "events": [
            {
                "id": f"ev_{i:02d}",
                "arc_id": "arc_1",
                "title": f"Arc One Event {i}",
                "synopsis": (
                    f"Event {i} in arc one, with a long synopsis so the section "
                    "serializes well past twelve thousand characters in total. "
                ) * 4,
            }
            for i in range(1, n_events + 1)
        ],
        "links": [],
    }


def test_whole_events_slice_is_not_truncated():
    before = _large_spec(30)
    blob = artifact_json_for_refine(before, {"focus_paths": ["events"]})
    assert len(blob) > 12000, "fixture must serialize past the old 12,000-char cap"
    # Parses (the old slice was cut mid-string) and carries every event: the
    # model cannot repair a tail it was never shown.
    sliced = json.loads(blob)
    assert [e["id"] for e in sliced["events"]] == [f"ev_{i:02d}" for i in range(1, 31)]


def test_large_section_repair_round_trip_keeps_every_event():
    # Slice -> model patch over the WHOLE visible section -> merge -> normalize
    # -> accept: no event may be lost in the chain.
    before = _large_spec(30)
    sliced = json.loads(artifact_json_for_refine(before, {"focus_paths": ["events"]}))
    patched = [dict(e) for e in sliced["events"]]
    patched[0] = {**patched[0], "synopsis": "repaired synopsis"}
    merged = merge_refine_output(before, {"events": patched}, {"focus_paths": ["events"]})
    after = normalize_spec(merged, "checksum")
    assert len(after["events"]) == 30, (
        "the whole-section merge must not drop events the model saw — the "
        "12,000-char slice cut used to lose the section tail here (#323 F4)"
    )
    assert accept_refine(before, after, {"focus_paths": ["events"]}).accepted


def test_per_item_slice_still_capped():
    # The cap is gone ONLY for whole-section targets: a per-item slice is still
    # bounded, because the merge only replaces the named item and unseen events
    # are untouched there.
    spec = _large_spec(1)
    spec["events"][0]["synopsis"] = "x" * 20000
    blob = artifact_json_for_refine(spec, {"focus_paths": ["events[ev_01]"]})
    assert len(blob) == 12000


# F5 — the empty-arc repair: two events in arc_2, none in arc_1. The correct
# section patch MOVES one event into arc_1 (both IDs retained) and clears
# every_arc_has_events — but accept_refine rejected it as "events removed
# outside scope" + "arc_2 events shrank" when the revision carried no scope.
# handoff_autofix now scopes a whole-events revision to ["events"]; the guard
# itself must still reject the same patch when no scope allows the change.
def test_empty_arc_move_accepted_with_events_scope():
    before = {
        "version": 1,
        "meta": {"title": "STORY PLAN"},
        "charter": {"consistency_anchors": ["a1", "a2"], "forbids": [], "style_constraints": []},
        "layers": {"characters": [{"name": "Mara", "traits": ["calm"]}], "mechanics": [], "variables": []},
        "arcs": [
            {"id": "arc_1", "title": "Arc One", "arc_kind": "setup"},
            {"id": "arc_2", "title": "Arc Two", "arc_kind": "discovery"},
        ],
        "events": [
            {"id": "ev_1", "arc_id": "arc_2", "title": "Arc Two Event 1", "synopsis": "s1"},
            {"id": "ev_2", "arc_id": "arc_2", "title": "Arc Two Event 2", "synopsis": "s2"},
        ],
        "links": [],
    }
    moved = [
        {"id": "ev_1", "arc_id": "arc_1", "title": "Arc Two Event 1", "synopsis": "s1"},
        {"id": "ev_2", "arc_id": "arc_2", "title": "Arc Two Event 2", "synopsis": "s2"},
    ]
    merged = merge_refine_output(before, {"events": moved}, {"focus_paths": ["events"]})
    after = normalize_spec(merged, "checksum")
    assert [e["id"] for e in after["events"]] == ["ev_1", "ev_2"]
    rules = {r["rule"]: r["pass"] for r in run_rules(after)}
    assert rules["every_arc_has_events"] is True

    unscoped = accept_refine(before, after, {"focus_paths": ["events"]})
    assert unscoped.accepted is False
    assert any("events removed outside scope" in r for r in unscoped.reasons)
    assert any("arc_2 events shrank" in r for r in unscoped.reasons)

    scoped = accept_refine(before, after, {"focus_paths": ["events"], "scope": ["events"]})
    assert scoped.accepted, (
        "a whole-events revision scoped to events must accept the empty-arc "
        "move — both IDs are retained, only the arc assignment changed (#323 F5)"
    )
