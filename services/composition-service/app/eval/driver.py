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
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.eval.defects import DefectClass, Observation

#: The public gateway. Everything goes through it — the platform's gateway invariant applies
#: to an eval as much as to a feature.
GATEWAY = "http://localhost:3123"

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

    def _draft(self, project: str, node: str) -> dict:
        return _req("POST", f"/v1/composition/works/{project}/generate", self.token,
                    {"outline_node_id": node, "model_source": "user_model",
                     "model_ref": self.model_ref, "operation": "draft_scene",
                     "mode": "auto", "reasoning": "off"})

    # ── per-class seeding ────────────────────────────────────────────────────────────────

    def _length(self, variant: Variant) -> Observation:
        """Seeded = a 900-word Vietnamese target (the measured Mị Đế case); control = 200,
        comfortably inside any budget. Same scene, same model — only the ask differs, which
        is what makes the control a control."""
        target = 900 if variant == "seeded" else 200
        _book, chapter, project = self._throwaway_work(f"length-{variant}")
        node = _req("POST", f"/v1/composition/works/{project}/outline/nodes", self.token,
                    {"kind": "scene", "chapter_id": chapter, "title": f"length {variant}",
                     "synopsis": "Nàng bước qua cổng đông lúc rạng đông, đối mặt với người "
                                 "gác cổng và đòi được vào trong.",
                     "target_words": target, "story_order": 1})["id"]
        r = self._draft(project, node)
        return Observation(fields={
            "target_words": r.get("target_words"),
            "actual_words": r.get("actual_words"),
            "word_count_method": r.get("word_count_method"),
        }, note=f"target={target}")

    def _truncation(self, variant: Variant) -> Observation:
        """Seeded = a target far beyond the scene budget's ceiling, so the wire clips;
        control = a modest one. Reads `finish_reason`, which the generate response already
        carried before this package existed."""
        target = 20000 if variant == "seeded" else 200
        _book, chapter, project = self._throwaway_work(f"trunc-{variant}")
        node = _req("POST", f"/v1/composition/works/{project}/outline/nodes", self.token,
                    {"kind": "scene", "chapter_id": chapter, "title": f"trunc {variant}",
                     "synopsis": "Một trận chiến dài giữa hai đạo quân trên cánh đồng tuyết.",
                     "target_words": target, "story_order": 1})["id"]
        r = self._draft(project, node)
        return Observation(fields={"finish_reason": r.get("finish_reason")},
                           note=f"target={target}")

    #: code → seeding function. A class absent here is NOT driveable yet, and says so.
    def _seeders(self) -> dict[str, Any]:
        return {
            "length_directive_ignored": self._length,
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
