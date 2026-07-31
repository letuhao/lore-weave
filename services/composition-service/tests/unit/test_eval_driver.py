"""Teeth for the eval drivers (spec §S10-b).

The driver's defining bug was shipped once already and caught by `/review-impl`: `_draft`
read its fields off the POST response, but `mode:"auto"` ENQUEUES — the POST answers 202
`{job_id, status:"pending"}` and the draft lands on the job row. Every field came back None,
every class would have scored ERROR, and the harness would have looked like it ran.

That is not a hypothetical: `scripts/eval_a2_canon.py` has the same bug today, which is why
the one pre-existing seeded harness reports "did not detect the seeded contradiction" for a
reason with nothing to do with canon.

So the polling is tested against a fake transport rather than a live stack — the point of the
replay/live split is that the deterministic half is exercisable in CI.
"""
from __future__ import annotations

import json

import pytest

from app.eval import driver as drv
from app.eval.defects import DEFECTS, Outcome
from app.eval.suite import observe

_LENGTH = next(d for d in DEFECTS if d.code == "length_target_unmet")


# ── ReplayDriver ──────────────────────────────────────────────────────────────────────────

def test_replay_serves_a_recorded_observation():
    r = drv.ReplayDriver(recordings={
        "length_target_unmet:seeded": {
            "fields": {"target_words": 1500, "actual_words": 559,
                       "word_count_method": "whitespace"}}})
    obs = r.run(_LENGTH, "seeded")
    assert obs.fields["actual_words"] == 559
    assert observe(_LENGTH, obs) is Outcome.FIRED


def test_a_missing_recording_is_an_error_not_a_quiet_detector():
    """A gap in the recording must not score as "the engine did not have this defect"."""
    obs = drv.ReplayDriver(recordings={}).run(_LENGTH, "seeded")
    assert obs.failed and observe(_LENGTH, obs) is Outcome.ERROR


def test_replay_round_trips_a_recording_file(tmp_path):
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps({"observations": {
        "length_target_unmet:control": {"fields": {"target_words": 500,
                                                        "actual_words": 565,
                                                        "word_count_method": "whitespace"}}}}),
                 encoding="utf-8")
    obs = drv.ReplayDriver.from_file(p).run(_LENGTH, "control")
    assert observe(_LENGTH, obs) is Outcome.QUIET


# ── LiveDriver: the enqueue path ──────────────────────────────────────────────────────────

class _Transport:
    """Records requests and replays canned responses, keyed by (method, path-prefix)."""

    def __init__(self, job_status_sequence, job_result=None):
        self.calls: list[tuple[str, str]] = []
        self._statuses = list(job_status_sequence)
        self._result = job_result or {}

    def __call__(self, method, path, token=None, body=None, timeout=300):
        self.calls.append((method, path))
        if path.endswith("/generate"):
            return {"job_id": "job-1", "status": "pending", "enqueued": "ok"}
        if "/composition/jobs/" in path:
            # Keep returning the LAST status once the sequence is exhausted. Falling back to
            # "completed" made the timeout test pass for the wrong reason — the job "finished"
            # with an empty result instead of timing out.
            status = self._statuses.pop(0) if len(self._statuses) > 1 else (
                self._statuses[0] if self._statuses else "completed")
            return {"status": status, "result": self._result if status == "completed" else {}}
        if path == "/v1/books":
            return {"book_id": "b1"}
        if path.endswith("/chapters"):
            return {"chapter_id": "c1"}
        if path.endswith("/work"):
            return {"project_id": "p1"}
        if path.endswith("/outline/nodes"):
            return {"id": "n1"}
        raise AssertionError(f"unexpected request {method} {path}")


@pytest.fixture()
def live(monkeypatch):
    def _make(transport):
        monkeypatch.setattr(drv, "_req", transport)
        d = drv.LiveDriver(token="t", model_ref="m")
        object.__setattr__(d, "poll_interval_s", 0.0)
        return d
    return _make


def test_the_driver_polls_the_job_instead_of_reading_the_202(live):
    """THE regression. Reading the POST response yields None for every field."""
    t = _Transport(["pending", "running", "completed"],
                   job_result={"target_words": 1500, "actual_words": 559,
                               "word_count_method": "whitespace"})
    obs = live(t).run(_LENGTH, "seeded")
    assert obs.fields["actual_words"] == 559, "the driver read the enqueue response again"
    assert sum(1 for m, p in t.calls if "/composition/jobs/" in p) == 3, "it did not poll"


def test_a_failed_job_is_a_failed_observation_not_a_quiet_detector(live):
    obs = live(_Transport(["failed"])).run(_LENGTH, "seeded")
    assert obs.failed and observe(_LENGTH, obs) is Outcome.ERROR
    assert "failed" in obs.note


def test_a_job_that_never_terminates_times_out_as_an_error(live, monkeypatch):
    d = live(_Transport(["pending"]))
    object.__setattr__(d, "job_timeout_s", 0.05)
    obs = d.run(_LENGTH, "seeded")
    assert obs.failed and "TimeoutError" in obs.note


def test_an_unimplemented_class_reports_what_is_missing(live):
    """Uses a SYNTHETIC class, not a real one.

    It used to name `gone_cast_asserted_active`, which made the test assert an accident of
    the registry's current wiring: the day that class got a seeder (2026-08-01) the test went
    red for a good change. What is being pinned is the DRIVER's contract — an unseeded class
    is a failed Observation naming what is missing, never a quiet detector — and that must
    hold whatever the registry happens to contain.
    """
    from app.eval.defects import DefectClass

    unseeded = DefectClass(
        code="__no_seeder_exists__", defect="d", seeded="s", control="c",
        detector=lambda o: False, provenance="synthetic — see the docstring")
    obs = live(_Transport(["completed"])).run(unseeded, "seeded")
    assert obs.failed and "no live seeding implemented" in obs.note


def test_every_driveable_class_is_a_real_registry_code(live):
    """The inverse guard: a seeder keyed on a code the registry does not contain would never
    run and nothing would say so."""
    from app.eval.defects import DEFECTS as _D
    from app.eval.driver import LiveDriver

    codes = {d.code for d in _D}
    stray = set(LiveDriver(token="", model_ref="")._seeders()) - codes
    assert not stray, f"seeder(s) for unknown class code(s): {sorted(stray)}"


# ── the truncation seeding must use a lever that actually moves ───────────────────────────

def test_truncation_seeds_with_an_output_CAP_not_a_large_target(live):
    """`target_words` does not drive length — measured, ~580 words across a 7.5x target range.
    Seeding a clip with a big target is a recipe built on a lever that does not move, so the
    class could never fire. `max_output_tokens` is the real cap."""
    t = _Transport(["completed"], job_result={"finish_reason": "length"})
    trunc = next(x for x in DEFECTS if x.code == "structured_output_truncated")
    d = live(t)
    captured: dict = {}

    real = drv._req

    def spy(method, path, token=None, body=None, timeout=300):
        if path.endswith("/generate"):
            captured.update(body or {})
        return real(method, path, token, body, timeout)

    import app.eval.driver as mod
    mod._req = spy
    try:
        obs = d.run(trunc, "seeded")
    finally:
        mod._req = real

    assert captured.get("max_output_tokens"), "no output cap was sent — nothing would clip"
    assert captured["max_output_tokens"] < 1000
    assert obs.fields["finish_reason"] == "length"


def test_the_control_variant_gets_ample_room(live):
    t = _Transport(["completed"], job_result={"finish_reason": "stop"})
    trunc = next(x for x in DEFECTS if x.code == "structured_output_truncated")
    d = live(t)
    captured: dict = {}
    real = drv._req

    def spy(method, path, token=None, body=None, timeout=300):
        if path.endswith("/generate"):
            captured.update(body or {})
        return real(method, path, token, body, timeout)

    import app.eval.driver as mod
    mod._req = spy
    try:
        obs = d.run(trunc, "control")
    finally:
        mod._req = real

    assert captured["max_output_tokens"] >= 4096
    assert observe(trunc, obs) is Outcome.QUIET


# ── throwaway discipline ──────────────────────────────────────────────────────────────────

def test_every_live_book_is_prefixed_as_a_throwaway(live):
    """A content-CREATING eval seeds DELIBERATE canon violations. Debris left in a real book
    reads as a product bug months later."""
    t = _Transport(["completed"], job_result={"target_words": 1500, "actual_words": 559,
                                              "word_count_method": "whitespace"})
    d = live(t)
    titles: list[str] = []
    real = drv._req

    def spy(method, path, token=None, body=None, timeout=300):
        if path == "/v1/books":
            titles.append((body or {}).get("title", ""))
        return real(method, path, token, body, timeout)

    import app.eval.driver as mod
    mod._req = spy
    try:
        d.run(_LENGTH, "seeded")
    finally:
        mod._req = real

    assert titles and all(t_.startswith("[eval-throwaway]") for t_ in titles), titles


def test_a_result_missing_a_declared_field_is_an_error_not_a_quiet_detector(live):
    """Found by the timeout test on its first run. Building the observation with `r.get(k)`
    inserts the key with None, which passes the missing-field guard — so a job that completed
    with an EMPTY result scored QUIET, i.e. "the engine did not have this defect"."""
    obs = live(_Transport(["completed"], job_result={})).run(_LENGTH, "seeded")
    assert obs.fields == {}, "an absent field must stay absent, not become None"
    assert observe(_LENGTH, obs) is Outcome.ERROR
