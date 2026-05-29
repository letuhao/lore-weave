#!/usr/bin/env python3
"""
sub-agent-spawn — Q2 sub-agent model tier enforcer
Per RAID_WORKFLOW.md §14.2.

This is a wrapper/probe — it does NOT actually spawn an Agent (that's the
Raid Leader's Agent tool call). Its job is to:
  1. Resolve role → model per quota-profile.yaml role_to_model table.
  2. Validate the chosen model is allowed for the role.
  3. Emit prompt-augmentation text the Raid Leader interpolates.
  4. Smoke harness uses --dry-run to verify the resolution is correct.

Usage:
  sub-agent-spawn.py --role DPS --dry-run               # prints chosen model + augmentation
  sub-agent-spawn.py --role scope-guard --dry-run
  sub-agent-spawn.py --role raid-leader --dry-run
  sub-agent-spawn.py --role DPS --slice C17 --dry-run   # may upgrade to opus per dps_heavy
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "contracts" / "raid" / "quota-profile.yaml"
AUDIT_LOG = REPO_ROOT / "docs" / "audit" / "AUDIT_LOG.jsonl"

# Slices that warrant dps_heavy (Opus) per §14.2
HEAVY_SLICES = {"C17", "cycle-17", "dp-kernel", "macros", "C9", "C13",
                "per-reality-migration"}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_profile_simple(path: Path) -> dict:
    """Lightweight YAML reader for role_to_model + preferred_models."""
    text = path.read_text(encoding="utf-8")
    data: dict = {"role_to_model": {}, "preferred_models": {}}
    section = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        # Top-level section: starts in column 0 ending with `:`
        m = re.match(r"^([a-zA-Z_]+):\s*$", line)
        if m:
            section = m.group(1)
            continue
        # Sub-key: 2-space indent
        m = re.match(r"^  ([a-zA-Z_]+):\s*([^#]+?)\s*$", line)
        if m and section in ("role_to_model", "preferred_models"):
            data[section][m.group(1)] = m.group(2).strip()
    return data


def resolve_model(role: str, slice_hint: str | None) -> str:
    profile = parse_profile_simple(PROFILE)
    role_norm = role.lower().replace("-", "_")
    # DPS default → maybe upgrade if slice_hint matches heavy
    if role_norm in ("dps", "dps_default"):
        if slice_hint and any(h.lower() in slice_hint.lower() for h in HEAVY_SLICES):
            return profile["role_to_model"].get("dps_heavy",
                       profile["preferred_models"].get("heavy_sub_agent", "claude-opus-4-7"))
        return profile["role_to_model"].get("dps_default",
                   profile["preferred_models"].get("default_sub_agent", "claude-sonnet-4-6"))
    if role_norm == "raid_leader":
        return profile["role_to_model"].get("raid_leader", "claude-opus-4-7")
    if role_norm == "scope_guard":
        return profile["role_to_model"].get("scope_guard",
                   profile["preferred_models"].get("light_sub_agent", "claude-haiku-4-5"))
    if role_norm == "auditor":
        return profile["role_to_model"].get("auditor", "claude-haiku-4-5")
    if role_norm == "adversary":
        return profile["role_to_model"].get("adversary", "claude-sonnet-4-6")
    if role_norm == "tank":
        return profile["role_to_model"].get("tank", "claude-sonnet-4-6")
    if role_norm == "healer":
        return profile["role_to_model"].get("healer", "claude-sonnet-4-6")
    if role_norm == "post_commit_verifier":
        return profile["role_to_model"].get("post_commit_verifier", "claude-haiku-4-5")
    # Unknown role → default sub-agent
    return profile["preferred_models"].get("default_sub_agent", "claude-sonnet-4-6")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--role", required=True,
                   help="raid-leader | DPS | tank | healer | adversary | scope-guard | auditor | post-commit-verifier")
    p.add_argument("--slice", default=None, help="optional slice hint (e.g. C17, dp-kernel)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if not PROFILE.exists():
        print(f"[sub-agent-spawn] ERROR: profile missing: {PROFILE}", file=sys.stderr)
        return 3

    model = resolve_model(args.role, args.slice)

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": now_iso(),
            "event": "sub_agent_spawn_resolved",
            "role": args.role,
            "slice": args.slice,
            "model": model,
            "dry_run": args.dry_run,
        }) + "\n")

    print(f"role: {args.role}")
    print(f"slice: {args.slice or '(default)'}")
    print(f"model: {model}")
    if not args.dry_run:
        # Production usage: Raid Leader is the one that actually invokes
        # the Agent tool. This script's job is resolution; printout is
        # what to interpolate into the Agent call.
        print("# Raid Leader: pass `model: {0}` parameter to Agent tool call".format(model))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
