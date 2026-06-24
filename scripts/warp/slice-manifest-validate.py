#!/usr/bin/env python3
"""slice-manifest-validate.py — the /warp independence guarantee.

Validates a warp Slice Manifest (docs/warp/<task>/manifest.yaml) BEFORE any
fan-out is spawned. This is the machine-checkable backbone of the /warp parallel
workflow mode (see docs/specs/2026-06-12-warp-parallel-mode.md §6): it converts
"I hope these slices don't collide" into an asserted invariant.

The single most important check is **pairwise-disjoint write-sets**: if two
slices could write the same file, parallel execution in isolated worktrees will
produce a merge conflict (or worse, a silent divergence) at the reconcile node.
Blocking here is cheaper than discovering it at integration time.

Manifest shape (YAML or JSON):

    task: <slug>
    frozen_interface:
      - path: contracts/api/campaign.yaml
        sha: <git-blob-sha-at-freeze>
    slices:
      - id: 1
        label: budget-validate-backend
        writes: [services/campaign-service/internal/budget/**]   # OWN subtree
        reads:  [contracts/api/campaign.yaml]                     # frozen only
        acceptance: ["go test ./internal/budget/..."]
    merge_plan:
      integrate_order: [1]
      reconcile_evidence: "live smoke: ..."
      on_contract_violation: HALT_REDESIGN

Checks (BLOCK = exit 1; WARN = advisory, exit 0):
  R0  structural    — task slug, >=2 slices, unique ids, each slice has writes
  R1  frozen pinned — frozen_interface non-empty, every entry has a sha
  R1b frozen        — no slice WRITES a frozen path (frozen = immutable in fan-out)
  R2  disjoint      — pairwise path-prefix-disjoint write-sets (the core invariant)
  R3  reads bounded — no slice READS another slice's write-set (= runtime dependency)
  R4  merge plan    — integrate_order is a permutation; HALT_REDESIGN; evidence present

Overlap is COMPONENT-WISE path-prefix, not string-prefix: `services/book` does
NOT overlap `services/book-service` (different path components), but it DOES
overlap `services/book/internal`.

Usage:
  python scripts/warp/slice-manifest-validate.py <manifest.yaml|.json> [--json]

Exit codes:
  0  no BLOCK findings (clean, or WARN-only)
  1  at least one BLOCK finding
  2  usage error
  3  manifest unreadable / PyYAML missing for a .yaml file
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

Finding = namedtuple("Finding", ["severity", "rule", "message"])  # severity: BLOCK|WARN


# ── path-glob normalization + overlap ────────────────────────────────


def components(glob: str) -> tuple[str, ...]:
    """Normalize a write/read glob to its concrete path-prefix components.

    Trailing wildcard segments (`**`, `*`) are stripped — a slice owning
    `services/x/**` owns the subtree rooted at `services/x`. Backslashes are
    posix-normalized so Windows-authored manifests behave identically.

      services/x/**        -> ('services', 'x')
      services/x/types.go  -> ('services', 'x', 'types.go')
      **                   -> ()          (whole repo — overlaps everything)
    """
    s = str(glob).replace("\\", "/").strip()
    parts = [p for p in s.split("/") if p not in ("", ".")]
    while parts and parts[-1] in ("**", "*"):
        parts.pop()
    return tuple(parts)


def overlaps(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """True if path-prefix `a` and `b` overlap: equal, or one is a
    component-wise prefix of the other.

    Component-wise is load-bearing — a plain string-prefix test would wrongly
    flag `services/book` vs `services/book-service` as overlapping.

    Comparison is CASE-INSENSITIVE (/review-impl MED-3): the project's target
    filesystems (Windows, macOS default) are case-insensitive, so `services/Book`
    and `services/book` are the SAME directory and MUST be treated as overlapping.
    Case-folding is conservative on a case-sensitive FS (Linux) — a false BLOCK
    there is a safe annoyance; a false CLEAR is the merge collision we exist to
    prevent (asymmetric cost → fail toward overlap)."""
    af = tuple(x.casefold() for x in a)
    bf = tuple(x.casefold() for x in b)
    n = min(len(af), len(bf))
    return af[:n] == bf[:n]


_GLOB_META = frozenset("*?[]{}")


def unsupported_glob(glob: str) -> str | None:
    """Return a reason string if `glob` uses a wildcard the validator cannot
    reason about, else None (/review-impl HIGH-1 — fail closed).

    The disjointness guarantee (R2) only holds for path globs whose wildcard is a
    single TRAILING `/**` or `/*` (a whole-subtree claim). An INTERIOR wildcard
    (`services/*/budget`, `services/**/x.go`) or a partial-segment glob
    (`services/x*`) is matched against literal components by `components()` and
    would produce a FALSE 'disjoint' verdict — e.g. `services/*/budget/**` vs
    `services/campaign/budget/**` reads as disjoint though the first matches the
    second. That is the exact catastrophic failure the validator exists to
    prevent, so we fail CLOSED: reject such globs and require a concrete subtree."""
    s = str(glob).replace("\\", "/").strip()
    for suffix in ("/**", "/*"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    bad = "".join(sorted(ch for ch in _GLOB_META if ch in s))
    if bad:
        return (f"unsupported wildcard {bad!r} in '{glob}' — declare a concrete "
                f"subtree (e.g. services/x/budget/**), not an interior or "
                f"partial-segment glob")
    return None


def _any_overlap(globs_a, globs_b):
    """Yield (ga, gb) for every overlapping pair across two glob lists."""
    norm_a = [(g, components(g)) for g in globs_a]
    norm_b = [(g, components(g)) for g in globs_b]
    for ga, ca in norm_a:
        for gb, cb in norm_b:
            if overlaps(ca, cb):
                yield ga, gb


# ── validation core (pure — operates on a dict, no I/O) ──────────────


def _as_list(v):
    return v if isinstance(v, list) else []


def validate_manifest(manifest: dict) -> list[Finding]:
    """Validate a parsed manifest dict. Returns a list of Findings (possibly
    empty). Pure: no file or process I/O, so unit tests pass dicts directly."""
    findings: list[Finding] = []

    if not isinstance(manifest, dict):
        return [Finding("BLOCK", "R0", "manifest is not a mapping")]

    # ── R0 structural ───────────────────────────────────────────────
    task = manifest.get("task")
    if not (isinstance(task, str) and task.strip()):
        findings.append(Finding("BLOCK", "R0", "missing/empty `task` slug"))

    slices = manifest.get("slices")
    if not isinstance(slices, list):
        findings.append(Finding("BLOCK", "R0", "`slices` missing or not a list"))
        return findings  # nothing else is checkable without slices
    if len(slices) < 2:
        findings.append(Finding(
            "BLOCK", "R0",
            f"{len(slices)} slice(s): /warp needs >=2 disjoint slices — "
            f"fall back to serial /loom",
        ))

    seen_ids: dict = {}
    for idx, sl in enumerate(slices):
        if not isinstance(sl, dict):
            findings.append(Finding("BLOCK", "R0", f"slice[{idx}] is not a mapping"))
            continue
        sid = sl.get("id")
        label = sl.get("label", f"slice[{idx}]")
        if sid is None:
            findings.append(Finding("BLOCK", "R0", f"{label}: missing `id`"))
        elif sid in seen_ids:
            findings.append(Finding(
                "BLOCK", "R0", f"duplicate slice id {sid!r} ({label} & {seen_ids[sid]})"))
        else:
            seen_ids[sid] = label
        if not _as_list(sl.get("writes")):
            findings.append(Finding(
                "BLOCK", "R0",
                f"{label}: empty `writes` — cannot guarantee disjointness"))
        # /review-impl HIGH-1: reject globs the overlap check can't reason about,
        # BEFORE they can produce a false-disjoint verdict in R1b/R2/R3.
        for kind in ("writes", "reads"):
            for g in _as_list(sl.get(kind)):
                reason = unsupported_glob(g)
                if reason:
                    findings.append(Finding("BLOCK", "R0", f"{label} {kind}: {reason}"))
        if not _as_list(sl.get("acceptance")):
            findings.append(Finding(
                "WARN", "R0", f"{label}: no `acceptance` — slice cannot self-verify"))

    # ── R1 frozen interface pinned ──────────────────────────────────
    frozen = manifest.get("frozen_interface")
    frozen_components: list[tuple[str, ...]] = []
    if not isinstance(frozen, list) or not frozen:
        findings.append(Finding(
            "BLOCK", "R1",
            "`frozen_interface` missing/empty — nothing is actually frozen; "
            "all shared-write decisions must be pinned before fan-out"))
    else:
        for fi in frozen:
            if not isinstance(fi, dict):
                findings.append(Finding("BLOCK", "R1", f"frozen entry {fi!r} not a mapping"))
                continue
            fpath = fi.get("path")
            fsha = fi.get("sha")
            if not (isinstance(fpath, str) and fpath.strip()):
                findings.append(Finding("BLOCK", "R1", "frozen entry has empty `path`"))
                continue
            if not (fsha is not None and str(fsha).strip()):
                findings.append(Finding(
                    "BLOCK", "R1",
                    f"frozen `{fpath}` has no `sha` — not actually frozen "
                    f"(pin the git blob sha at freeze time)"))
            frozen_components.append(components(fpath))

    # Precompute per-slice normalized write/read sets for R1b/R2/R3.
    valid_slices = [s for s in slices if isinstance(s, dict)]

    def _label(s, i):
        return s.get("label", f"slice[{i}]")

    # ── R1b no slice writes a frozen path ───────────────────────────
    for i, sl in enumerate(valid_slices):
        for w in _as_list(sl.get("writes")):
            cw = components(w)
            for fc in frozen_components:
                if overlaps(cw, fc):
                    findings.append(Finding(
                        "BLOCK", "R1b",
                        f"{_label(sl, i)} writes `{w}` which is inside the frozen "
                        f"interface — frozen paths are immutable during fan-out "
                        f"(change the interface in DESIGN, not a slice)"))

    # ── R2 pairwise-disjoint writes (the core invariant) ────────────
    for i in range(len(valid_slices)):
        for j in range(i + 1, len(valid_slices)):
            wi = _as_list(valid_slices[i].get("writes"))
            wj = _as_list(valid_slices[j].get("writes"))
            for ga, gb in _any_overlap(wi, wj):
                findings.append(Finding(
                    "BLOCK", "R2",
                    f"write-set overlap: {_label(valid_slices[i], i)} `{ga}` "
                    f"vs {_label(valid_slices[j], j)} `{gb}` — slices would "
                    f"collide in parallel worktrees"))

    # ── R3 reads bounded (no reading another slice's churn) ─────────
    for i, sl in enumerate(valid_slices):
        for r in _as_list(sl.get("reads")):
            cr = components(r)
            for j, other in enumerate(valid_slices):
                if j == i:
                    continue
                for w in _as_list(other.get("writes")):
                    if overlaps(cr, components(w)):
                        findings.append(Finding(
                            "BLOCK", "R3",
                            f"{_label(sl, i)} reads `{r}` which is in "
                            f"{_label(other, j)}'s write-set (`{w}`) — that is a "
                            f"runtime dependency; the slices are not independent "
                            f"(freeze the shared surface or merge the slices)"))

    # ── R4 merge plan (advisory) ────────────────────────────────────
    mp = manifest.get("merge_plan")
    if not isinstance(mp, dict):
        findings.append(Finding("WARN", "R4", "`merge_plan` missing — Tank has no integrate order / evidence"))
    else:
        ids = [s.get("id") for s in valid_slices if s.get("id") is not None]
        order = mp.get("integrate_order")
        if order is not None and sorted(order, key=str) != sorted(ids, key=str):
            findings.append(Finding(
                "WARN", "R4",
                f"`integrate_order` {order} is not a permutation of slice ids {ids}"))
        if str(mp.get("on_contract_violation", "")).strip().upper() != "HALT_REDESIGN":
            findings.append(Finding(
                "WARN", "R4",
                "`on_contract_violation` should be HALT_REDESIGN — never patch a "
                "slice to absorb a frozen-interface change (it re-introduces drift)"))
        if not str(mp.get("reconcile_evidence", "")).strip():
            findings.append(Finding(
                "WARN", "R4",
                "`reconcile_evidence` empty — define the cross-service smoke that "
                "proves the slices integrate"))

    return findings


def has_block(findings) -> bool:
    return any(f.severity == "BLOCK" for f in findings)


# ── frozen-interface drift check (/review-impl MED-4) ────────────────


def _head_blob_sha(path: str):
    """(status, sha) for `path` AS COMMITTED IN HEAD.

    status ∈ {"ok", "absent", "unavailable"}:
      - "ok"          → sha is the blob sha of path in HEAD
      - "absent"      → repo is fine but path is NOT committed in HEAD
      - "unavailable" → no git / no repo / no HEAD (can't verify)

    HEAD — not the working tree (`git hash-object`) — is the right reference:
    /warp slices fan out in worktrees based on a COMMITTED ref (dry-run finding
    D1: `isolation:worktree` starts from HEAD, never the orchestrator's
    uncommitted edits). So an uncommitted-but-on-disk frozen file is exactly the
    failure mode — the slices won't see it. Verifying against HEAD catches that;
    verifying the working tree would falsely pass."""
    try:
        repo = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ("unavailable", None)
    if repo.returncode != 0:
        return ("unavailable", None)
    r = subprocess.run(["git", "rev-parse", f"HEAD:{path}"],
                       capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return ("absent", None)  # repo ok, but path not committed in HEAD
    return ("ok", r.stdout.strip() or None)


def verify_frozen_shas(manifest: dict, blob_getter=_head_blob_sha) -> list[Finding]:
    """Check each frozen_interface file's COMMITTED (HEAD) blob sha against its
    declared sha. The structural validator (R1) only proves a sha is *present*;
    this proves the frozen surface is actually committed AND unchanged — the
    immutability the slices depend on (/review-impl MED-4 + dry-run D1).

    `blob_getter` is injectable so unit tests need no real git; it returns a
    (status, sha) tuple. An abbreviated declared sha (>=7) matches as a prefix.
    NOT committed in HEAD → BLOCK (slices won't see it). git unavailable → WARN
    (infra, not drift). Committed but sha mismatch → BLOCK (drift)."""
    findings: list[Finding] = []
    frozen = manifest.get("frozen_interface")
    if not isinstance(frozen, list):
        return findings  # R1 already blocks a missing/!list frozen_interface
    for fi in frozen:
        if not isinstance(fi, dict):
            continue
        path, declared = fi.get("path"), fi.get("sha")
        if not (isinstance(path, str) and path.strip()):
            continue
        if not (declared is not None and str(declared).strip()):
            continue
        declared = str(declared).strip().lower()
        status, current = blob_getter(path)
        if status == "absent":
            findings.append(Finding(
                "BLOCK", "R1c",
                f"frozen '{path}' is not committed in HEAD — slices fan out from a "
                f"committed base and won't see it; commit the frozen interface before fan-out"))
            continue
        if status != "ok" or current is None:
            findings.append(Finding(
                "WARN", "R1c",
                f"could not verify frozen '{path}' (git unavailable) — freeze UNVERIFIED"))
            continue
        current = current.lower()
        ok = current == declared or (len(declared) >= 7 and current.startswith(declared))
        if not ok:
            findings.append(Finding(
                "BLOCK", "R1c",
                f"frozen '{path}' changed since freeze: declared {declared[:12]}, "
                f"HEAD {current[:12]} — re-freeze in DESIGN, or a slice mutated it"))
    return findings


# ── I/O + CLI ────────────────────────────────────────────────────────


def load_manifest(path: Path) -> dict:
    """Load a manifest from .yaml/.yml/.json. Raises SystemExit(3) on failure."""
    if not path.exists():
        print(f"BLOCKED: manifest not found: {path}", file=sys.stderr)
        raise SystemExit(3)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"BLOCKED: invalid JSON in {path}: {e}", file=sys.stderr)
            raise SystemExit(3)
    try:
        import yaml
    except ImportError:
        print("BLOCKED: PyYAML required for .yaml manifests (pip install pyyaml), "
              "or pass a .json manifest", file=sys.stderr)
        raise SystemExit(3)
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        print(f"BLOCKED: invalid YAML in {path}: {e}", file=sys.stderr)
        raise SystemExit(3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a /warp slice manifest.")
    parser.add_argument("manifest", help="path to manifest.yaml|.json")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--verify-frozen", action="store_true",
                        help="also check each frozen_interface file's current git "
                             "blob sha matches its declared sha (freeze immutability)")
    args = parser.parse_args(argv)

    manifest = load_manifest(Path(args.manifest))
    findings = validate_manifest(manifest)
    if args.verify_frozen:
        findings = findings + verify_frozen_shas(manifest)

    blocks = [f for f in findings if f.severity == "BLOCK"]
    warns = [f for f in findings if f.severity == "WARN"]

    if args.json:
        print(json.dumps({
            "ok": not blocks,
            "blocks": [f._asdict() for f in blocks],
            "warns": [f._asdict() for f in warns],
        }, indent=2))
    else:
        for f in findings:
            stream = sys.stderr if f.severity == "BLOCK" else sys.stdout
            print(f"  [{f.severity}] {f.rule}: {f.message}", file=stream)
        n_slices = len(manifest.get("slices", []) if isinstance(manifest, dict) else [])
        if blocks:
            print(f"\nBLOCKED: {len(blocks)} blocking finding(s), "
                  f"{len(warns)} warning(s) across {n_slices} slice(s). "
                  f"Fix before fan-out, or fall back to serial /loom.", file=sys.stderr)
        else:
            print(f"\nOK: manifest valid — {n_slices} disjoint slices, "
                  f"{len(warns)} warning(s). Cleared for fan-out.")

    return 1 if blocks else 0


if __name__ == "__main__":
    sys.exit(main())
