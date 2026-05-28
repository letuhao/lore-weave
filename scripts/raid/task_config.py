#!/usr/bin/env python3
"""
task-config — RAID v1.6 active-task config loader.

Reads .raid/active-task.yaml and emits resolved paths/values for RAID scripts.
Replaces hardcoded `docs/plans/<task-slug>/` paths so RAID is portable across
branches and tasks.

Usage:
  task-config.py dump                  # full config as JSON
  task-config.py get <key>             # raw value for <key>
  task-config.py path <key>            # value resolved as repo-relative path
  task-config.py abspath <key>         # value resolved as absolute path
  task-config.py validate              # verify all path-keys point to existing files/dirs
  task-config.py keys                  # list all defined keys

Exit codes:
  0 success
  2 missing key (or key not a path for path/abspath)
  3 config file missing/unreadable
  4 invalid YAML
  5 validate found missing paths
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("[task-config] pyyaml required; pip install pyyaml", file=sys.stderr)
    sys.exit(3)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / ".raid" / "active-task.yaml"

PATH_KEYS = {
    "plan_dir",
    "workflow_doc",
    "decomposition_doc",
    "locked_qs_doc",
    "pre_flight_doc",
    "brief_dir",
    "cycle_log",
    "audit_log",
    "escalations_log",
    "in_progress_dir",
    "quota_log",
    "quota_profile",
}


def load_config() -> dict:
    """Importable helper for other Python RAID scripts."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f".raid/active-task.yaml not found at {CONFIG_PATH}. "
            "Create one or copy from a sibling branch."
        )
    try:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML in {CONFIG_PATH}: {e}") from e
    if not isinstance(cfg, dict):
        raise ValueError(f"expected mapping at top level of {CONFIG_PATH}")
    return cfg


def _load_or_exit() -> dict:
    try:
        return load_config()
    except FileNotFoundError as e:
        print(f"[task-config] {e}", file=sys.stderr)
        sys.exit(3)
    except ValueError as e:
        print(f"[task-config] {e}", file=sys.stderr)
        sys.exit(4)


def cmd_dump(_args) -> int:
    cfg = _load_or_exit()
    print(json.dumps(cfg, indent=2))
    return 0


def cmd_keys(_args) -> int:
    cfg = _load_or_exit()
    for k in cfg.keys():
        print(k)
    return 0


def cmd_get(args) -> int:
    cfg = _load_or_exit()
    if args.key not in cfg:
        print(f"[task-config] key not found: {args.key}", file=sys.stderr)
        return 2
    val = cfg[args.key]
    print(val if not isinstance(val, (dict, list)) else json.dumps(val))
    return 0


def cmd_path(args) -> int:
    cfg = _load_or_exit()
    if args.key not in cfg:
        print(f"[task-config] key not found: {args.key}", file=sys.stderr)
        return 2
    val = cfg[args.key]
    if not isinstance(val, str):
        print(f"[task-config] key {args.key} is not a string path", file=sys.stderr)
        return 2
    print(val)
    return 0


def cmd_abspath(args) -> int:
    cfg = _load_or_exit()
    if args.key not in cfg:
        print(f"[task-config] key not found: {args.key}", file=sys.stderr)
        return 2
    val = cfg[args.key]
    if not isinstance(val, str):
        print(f"[task-config] key {args.key} is not a string path", file=sys.stderr)
        return 2
    abs_path = (REPO_ROOT / val).resolve()
    print(str(abs_path))
    return 0


def cmd_validate(_args) -> int:
    cfg = _load_or_exit()
    missing = []
    for key in sorted(PATH_KEYS):
        if key not in cfg:
            continue
        val = cfg[key]
        if not isinstance(val, str):
            continue
        p = REPO_ROOT / val
        if not p.exists():
            missing.append(f"{key}: {val} (resolved to {p}) — MISSING")
    if missing:
        print("[task-config] validate FAILED:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 5
    print(f"[task-config] validate OK ({len([k for k in PATH_KEYS if k in cfg])} path keys verified)")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="task-config", description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dump")
    sub.add_parser("keys")
    sub.add_parser("validate")
    pg = sub.add_parser("get")
    pg.add_argument("key")
    pp = sub.add_parser("path")
    pp.add_argument("key")
    pa = sub.add_parser("abspath")
    pa.add_argument("key")
    args = p.parse_args(argv)
    if args.cmd == "dump":
        return cmd_dump(args)
    if args.cmd == "keys":
        return cmd_keys(args)
    if args.cmd == "get":
        return cmd_get(args)
    if args.cmd == "path":
        return cmd_path(args)
    if args.cmd == "abspath":
        return cmd_abspath(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
