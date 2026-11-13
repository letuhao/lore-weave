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

from app.engine.plan_forge.refine import artifact_json_for_refine, merge_refine_output
from app.engine.plan_forge.spec_index import spec_slice_for_paths

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
