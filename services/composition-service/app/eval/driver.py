"""How an Observation is obtained (spec §S10-b).

Two drivers, and the split is the point.

`LiveDriver` seeds a throwaway book and drives the real engine — the only way to learn
anything new about it. `ReplayDriver` replays observations recorded from a previous live run,
which is what lets the SCORER be exercised in CI without a stack. The nine `scripts/eval_*.py`
have only the first kind, which is why none of them runs anywhere: a harness whose every
failure reads "no stack today" gets ignored, then stops being maintained, then rots.

A recorded run is also the **baseline** §S10 asks for. Scoring is deterministic given the
observations, so a replay that changes verdict means the scorer changed — a regression the
live half could never isolate from model variance.

Throwaway books only
--------------------
Every live scenario creates its own book. A content-CREATING eval that writes into a real book
leaves debris that reads as a product bug months later, and the seeded defects here are
DELIBERATE canon violations — exactly the thing you must never leave lying in an author's
manuscript.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.eval.defects import DefectClass, Observation

#: The public gateway. Everything goes through it — the platform's gateway invariant applies
#: to an eval as much as to a feature.
GATEWAY = os.environ.get("EVAL_GATEWAY", "http://localhost:3123")

Variant = str  # "seeded" | "control"


class Driver(Protocol):
    def run(self, cls: DefectClass, variant: Variant) -> Observation: ...


# ── replay ────────────────────────────────────────────────────────────────────────────────

@dataclass
class ReplayDriver:
    """Serves observations recorded by a live run. Missing rows are ERROR, never QUIET.

    A missing recording must not look like "the detector stayed silent" — that scores as
    MISSED on a seeded variant, i.e. an engine defect, when the truth is that nothing was ever
    measured. Same distinction the suite draws between blind, errored and missed.
    """

    recordings: dict[str, dict[str, Any]]

    @classmethod
    def from_file(cls, path: Path) -> "ReplayDriver":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(recordings=raw.get("observations", {}))

    def run(self, cls_: DefectClass, variant: Variant) -> Observation:
        row = self.recordings.get(f"{cls_.code}:{variant}")
        if row is None:
            return Observation(failed=True, note="no recording for this class/variant")
        return Observation(fields=row.get("fields", {}), failed=bool(row.get("failed")),
                           note=row.get("note", ""))


# ── live ──────────────────────────────────────────────────────────────────────────────────

def _req(method: str, path: str, token: str | None = None,
         body: dict | None = None, timeout: int = 300) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GATEWAY + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode().strip()
    return json.loads(raw) if raw else {}


def login(email: str, password: str) -> str:
    return _req("POST", "/v1/auth/login", body={"email": email, "password": password})["access_token"]


def _project(result: dict, keys: tuple[str, ...]) -> dict:
    """Copy only the keys the result ACTUALLY carries.

    Building the observation with `r.get(k)` inserts every key with a None value, which
    defeats the suite's missing-field guard: the key is present, so `observe` does not raise
    ERROR, and the detector then reads `int(None or 0)` and goes QUIET — scoring as "the
    engine did not have this defect" when the engine reported nothing at all.

    That is the same false-negative-dressed-as-a-finding class the blindness handling exists
    for, reintroduced one layer out. A key the result omits must stay omitted.
    """
    return {k: result[k] for k in keys if k in result}


@dataclass
class LiveDriver:
    """Drives the real engine through the public gateway, on a fresh throwaway book per run.

    Only the classes whose seeding is implemented here are driveable; the rest report a
    failed Observation naming what is missing rather than silently scoring. `run` never
    invents a result — an unimplemented seeding path is an ERROR, which the suite reports as
    "this class scored nothing" instead of "the engine missed it".
    """

    token: str
    model_ref: str
    language: str = "vi"
    #: A local-model scene draft takes ~10-60s; the ceiling is generous because a TIMEOUT is
    #: reported as a failed Observation (ERROR), never as a quiet detector.
    job_timeout_s: float = 600.0
    poll_interval_s: float = 4.0

    def _throwaway_work(self, label: str) -> tuple[str, str, str]:
        """(book_id, chapter_id, project_id) — a book that exists only for this scenario."""
        stamp = int(time.time() * 1000)
        book = _req("POST", "/v1/books", self.token,
                    {"title": f"[eval-throwaway] {label} {stamp}",
                     "original_language": self.language})["book_id"]
        chapter = _req("POST", f"/v1/books/{book}/chapters", self.token,
                       {"original_language": self.language, "title": "Chapter 1"})["chapter_id"]
        project = _req("POST", f"/v1/composition/books/{book}/work", self.token)["project_id"]
        return book, chapter, project

    def _draft(self, project: str, node: str, *, max_output_tokens: int | None = None) -> dict:
        """Start a draft and return the JOB RESULT — not the POST response.

        `mode:"auto"` ENQUEUES: the POST answers 202 with `{job_id, status:"pending"}` and the
        draft lands on the job row. Reading fields off that immediate response yields None for
        everything, which the suite scores as ERROR for every class.

        `scripts/eval_a2_canon.py` does exactly that — it reads `canon` off the POST — so the
        one pre-existing seeded harness reports "did not detect the seeded contradiction" for a
        reason that has nothing to do with canon. This function exists in this shape so the
        replacement does not inherit the bug it was written to replace.
        """
        body: dict[str, Any] = {
            "outline_node_id": node, "model_source": "user_model",
            "model_ref": self.model_ref, "operation": "draft_scene",
            "mode": "auto", "reasoning": "off",
        }
        if max_output_tokens is not None:
            body["max_output_tokens"] = max_output_tokens
        posted = _req("POST", f"/v1/composition/works/{project}/generate", self.token, body)
        job_id = posted.get("job_id")
        if not job_id:
            raise RuntimeError(f"generate returned no job_id: {posted}")
        # An inline/replay response already carries the result.
        if posted.get("status") == "completed":
            return posted
        return self._await_job(job_id)

    def _await_job(self, job_id: str) -> dict:
        deadline = time.time() + self.job_timeout_s
        last = "pending"
        while time.time() < deadline:
            time.sleep(self.poll_interval_s)
            job = _req("GET", f"/v1/composition/jobs/{job_id}", self.token, timeout=60)
            last = job.get("status") or last
            if last in ("completed", "failed", "cancelled"):
                if last != "completed":
                    raise RuntimeError(f"job {job_id} ended {last}: {(job.get('result') or {})}")
                return job.get("result") or {}
        raise TimeoutError(f"job {job_id} still {last} after {self.job_timeout_s}s")

    # ── per-class seeding ────────────────────────────────────────────────────────────────

    def _length(self, variant: Variant) -> Observation:
        """Seeded = a 2500-word Vietnamese target; control = 1200.

        Both halves are MEASURED, 2026-08-01, after D-LENGTH-DIRECTIVE-NEVER-SENT was fixed:
        1200 → 1375/1260/1319 (1.10x, quiet) and 2500 → 1557/1515 (0.61x, fires). Neither
        depends on a coincidence.

        The previous pair — seeded 1500, control 500 — was derived from runs on which the
        LENGTH directive never reached the prompt, and its own docstring admitted the control
        "makes the detector quiet WITHOUT the directive having been obeyed". Both values are
        now wrong in opposite directions: 1500 is comfortably MET (so the seeded half would go
        quiet and score MISSED — a false finding, the exact failure this instrument exists to
        avoid), and 500 is over-met by 15%.
        """
        target = 2500 if variant == "seeded" else 1200
        _book, chapter, project = self._throwaway_work(f"length-{variant}")
        node = _req("POST", f"/v1/composition/works/{project}/outline/nodes", self.token,
                    {"kind": "scene", "chapter_id": chapter, "title": f"length {variant}",
                     "synopsis": "Nàng bước qua cổng đông lúc rạng đông, đối mặt với người "
                                 "gác cổng và đòi được vào trong.",
                     "target_words": target, "story_order": 1})["id"]
        r = self._draft(project, node)
        return Observation(
            fields=_project(r, ("target_words", "actual_words", "word_count_method")),
            note=f"target={target}")

    def _truncation(self, variant: Variant) -> Observation:
        """Seeded = a hard output CAP the draft cannot fit in; control = ample room.

        The cap is `max_output_tokens`, NOT a large `target_words`. The first version of this
        used `target_words=20000` to "ask for more than fits" — and that is still wrong, though
        the reason has changed. It was rejected because "output is ~580 words regardless of the
        target", which was an artefact of the directive never being sent. The target lever DOES
        move now (400→1.14x, 1200→1.10x). But it is still not a truncation lever: past ~1500
        words the model STOPS on its own, `finish="stop"`, and asking for 4000 produced FEWER
        words than asking for 2500 (849/1052 vs 1557/1515). A larger target buys less text, not
        a clipped response — so it can never seed a capacity failure.

        `max_output_tokens` is a real lever: it rides to the wire as the request's cap, and
        `eval_a2_canon.py` already uses it to bound its runs.
        """
        cap = 64 if variant == "seeded" else 4096
        _book, chapter, project = self._throwaway_work(f"trunc-{variant}")
        node = _req("POST", f"/v1/composition/works/{project}/outline/nodes", self.token,
                    {"kind": "scene", "chapter_id": chapter, "title": f"trunc {variant}",
                     "synopsis": "Một trận chiến dài giữa hai đạo quân trên cánh đồng tuyết.",
                     "target_words": 800, "story_order": 1})["id"]
        r = self._draft(project, node, max_output_tokens=cap)
        return Observation(fields=_project(r, ("finish_reason",)),
                           note=f"max_output_tokens={cap}")

    #: code → seeding function. A class absent here is NOT driveable yet, and says so.
    def _seeders(self) -> dict[str, Any]:
        return {
            "length_target_unmet": self._length,
            "structured_output_truncated": self._truncation,
        }

    def run(self, cls: DefectClass, variant: Variant) -> Observation:
        seed = self._seeders().get(cls.code)
        if seed is None:
            return Observation(
                failed=True,
                note=f"no live seeding implemented for {cls.code} — "
                     f"see scripts/eval_a2_canon.py for the gone-cast path",
            )
        try:
            return seed(variant)
        except Exception as exc:  # a live run failing is data, not a crash
            return Observation(failed=True, note=f"{type(exc).__name__}: {exc}")
