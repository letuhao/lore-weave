"""Unit tests for the pure decision logic of the stale-image guard (F-LIVE-1).

The docker/git IO is integration-only (exercised live); these pin the pure
timestamp/SHA→status decisions so the guard's verdict can't silently drift.

Run: python -m pytest scripts/test_check_stack_freshness.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import check_stack_freshness as g  # noqa: E402


def test_parse_iso_handles_docker_nanos_and_z():
    dt = g._parse_iso("2026-05-30T11:18:21.246241520Z")
    assert dt is not None and dt.year == 2026 and dt.tzinfo is not None


def test_parse_iso_handles_git_offset():
    dt = g._parse_iso("2026-05-31T18:22:03+07:00")
    assert dt is not None and dt.tzinfo is not None


def test_parse_iso_blank_is_none():
    assert g._parse_iso("") is None
    assert g._parse_iso("not-a-date") is None


def test_image_built_before_last_commit_is_stale():
    # image built 11:18Z, service last commit 11:22Z → behind HEAD → STALE.
    assert g.decide_drift_by_time(
        "2026-05-30T11:18:21Z", "2026-05-30T11:22:00+00:00") == "stale"


def test_image_built_after_last_commit_is_fresh():
    assert g.decide_drift_by_time(
        "2026-05-31T12:00:00Z", "2026-05-30T11:22:00+00:00") == "fresh"


def test_unparseable_timestamps_are_unknown():
    assert g.decide_drift_by_time("", "2026-05-30T11:22:00Z") == "unknown"
    assert g.decide_drift_by_time("2026-05-30T11:18:21Z", "") == "unknown"


def test_decide_status_precedence():
    # stale dominates everything.
    assert g.decide_status("stale", True) == "STALE"
    assert g.decide_status("stale", False) == "STALE"
    # fresh image but a missing route is still bad.
    assert g.decide_status("fresh", False) == "ROUTE-MISSING"
    # unknown drift surfaces as UNKNOWN (not silently FRESH).
    assert g.decide_status("unknown", None) == "UNKNOWN"
    assert g.decide_status("unknown", True) == "UNKNOWN"
    # the all-clear.
    assert g.decide_status("fresh", True) == "FRESH"
    assert g.decide_status("fresh", None) == "FRESH"


def test_drift_note_flags_unstamped_only():
    # LE-061: a stamped image gets no note; an unstamped one is flagged so the
    # degraded (tier-1-only) detection is visible.
    assert g.drift_note(True) == ""
    note = g.drift_note(False)
    assert "UNSTAMPED" in note and "build-stack.sh" in note


def test_provider_registry_is_probed():
    # LE-061: the embed seam must be in the route-presence probe set so a fully
    # stale provider-registry (route gone) is caught.
    probed = {svc for svc, _env, _default, _routes in g.PROBE_ROUTES}
    assert "provider-registry-service" in probed
    pr = next(r for r in g.PROBE_ROUTES if r[0] == "provider-registry-service")
    assert "/internal/embed" in pr[3]


# ── the source-dir map: no first-party container may be silently skipped ────
def test_worker_twins_resolve_to_their_service_source():
    """The guard used to assume `services/<container-name>` and SKIP anything that did
    not match. That silently excluded every worker twin — they build from their
    SERVICE's Dockerfile, not a directory of their own — plus the two frontends. Six
    first-party build targets it never looked at.

    It cost twice, both times with a green /health and no error anywhere:
    `composition-worker` ran a 12-hour-old image whose plan path no longer existed in
    source, and a composition image built mid-run served 12 of 17 motif locales while
    the repo held all 17. Both were visible only by counting.
    """
    smap = g.source_dir_map()
    for worker, service in (
        ("composition-worker", "services/composition-service"),
        ("translation-worker", "services/translation-service"),
        ("lore-enrichment-worker", "services/lore-enrichment-service"),
        ("video-gen-worker", "services/video-gen-service"),
    ):
        assert smap.get(worker) == service, (
            f"{worker} must diff against {service} — it is built from that Dockerfile")


def test_pulled_images_are_still_skipped():
    """A third-party image has no repo source, so "behind HEAD" is meaningless for it.
    Widening the map must not start flagging postgres."""
    smap = g.source_dir_map()
    for pulled in ("postgres", "redis", "neo4j", "minio", "rabbitmq"):
        assert not smap.get(pulled), f"{pulled} is a pulled image and has no source dir"


def test_every_compose_built_service_resolves_to_a_real_directory():
    """The regression guard for the whole class: if the compose parse silently stops
    matching (an indentation change, a reordered key), every service would fall back to
    the old assumption and the twins would go dark again — with no error. Assert the map
    is both non-trivial and pointing at directories that actually exist."""
    import os

    smap = g.source_dir_map()
    assert len(smap) >= 30, f"compose parse looks broken — only {len(smap)} services resolved"
    bad = {svc: d for svc, d in smap.items() if d and not os.path.isdir(d)}
    assert not bad, f"resolved to non-existent directories: {bad}"

def test_lore_enrichment_mcp_is_probed():
    probed = {svc for svc, _env, _default, _routes in g.PROBE_ROUTES}
    assert "lore-enrichment-service" in probed
    le = next(r for r in g.PROBE_ROUTES if r[0] == "lore-enrichment-service")
    assert "/mcp" in le[3]
