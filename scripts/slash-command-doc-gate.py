#!/usr/bin/env python3
"""Every slash command that exists is documented, and every one documented exists.

WHY THIS EXISTS
---------------
`.claude/commands/*.md` are the runners a contributor can actually type. `AGENTS.md`
has a table telling them which ones to type and when. Nothing kept the two in sync,
and both directions rot in a way nobody notices:

- **Documented but gone** — the table names a command the file no longer provides.
  A contributor types it, nothing happens, and they conclude the docs lie. This is
  the failure that arrives *during* a cleanup: the deletion is the easy half, and
  the prose is what gets forgotten.
- **Present but undocumented** — a runner sits in the repo that nobody is told about
  and nobody reviews. Measured when this gate was written: `/raid` and `/warp` were
  both in that state, which is a large part of why they fell out of use unnoticed.

The retirement of `/loom`, `/warp`, `/raid` and `/amaw`
(`docs/plans/2026-08-03-retire-unused-workflow-runners.md`) is exactly the kind of
multi-step change that leaves orphaned prose behind, so it gets a mechanism rather
than an acceptance-criteria bullet. Intent is not a mechanism.

Discovery, not enumeration: the command set is read off disk, so a runner added
tomorrow is covered without anyone updating this file.

    python scripts/slash-command-doc-gate.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_result import GateResult  # noqa: E402  (repo-local helper; path set above)

REPO = Path(__file__).resolve().parent.parent
COMMANDS_DIR = REPO / ".claude" / "commands"
GUIDE = REPO / "AGENTS.md"

# Scanning the whole guide does not work: a slash command and an HTTP route are
# spelled identically, so `/v1/worlds`, `/internal/*` and `/record` all read as
# commands. (Measured — the first version of this gate reported five.)
#
# So the registry is the "Slash commands" section specifically. That is a real
# coupling to one heading, and the mitigation is to FAIL when the heading cannot be
# found rather than silently scanning nothing: a renamed section turns into a loud
# error instead of a gate that quietly stops checking.
_SECTION = re.compile(r"^#{2,4}\s+Slash commands\s*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^#{1,4}\s+\S", re.MULTILINE)
_MENTION = re.compile(r"`/([a-z][a-z0-9-]*)(?=[`\s\[])")


def registry_section(guide: str) -> str | None:
    m = _SECTION.search(guide)
    if not m:
        return None
    rest = guide[m.end():]
    nxt = _NEXT_HEADING.search(rest)
    return rest[: nxt.start()] if nxt else rest


def main() -> int:
    result = GateResult(gate="rules")

    if not COMMANDS_DIR.is_dir():
        print("slash-command-doc-gate: no .claude/commands — nothing to check.")
        return 0
    if not GUIDE.is_file():
        print(f"slash-command-doc-gate: FAIL — {GUIDE.name} is missing.")
        return 1

    on_disk = {p.stem for p in COMMANDS_DIR.glob("*.md")}
    if not on_disk:
        # Zero commands would make both comparisons below trivially empty and the
        # gate would report a reassuring pass. That is the "scope never reaches it"
        # vacuity shape — refuse it.
        print("slash-command-doc-gate: FAIL — .claude/commands holds no command files; "
              "the check would be vacuous.")
        return 1

    guide = GUIDE.read_text(encoding="utf-8")
    section = registry_section(guide)
    if section is None:
        print(f"slash-command-doc-gate: FAIL — no '## Slash commands' section in {GUIDE.name}. "
              f"That section is this gate's registry; without it the check would scan nothing "
              f"and report a pass. Restore the heading or update _SECTION in this script.")
        return 1
    mentioned = {m.group(1) for m in _MENTION.finditer(section)}

    for name in sorted(on_disk - mentioned):
        result.blocker(
            id=f"undocumented-{name}",
            summary=(f"/{name} exists in .claude/commands but {GUIDE.name} never mentions it — "
                     f"a runner nobody is told about is a runner nobody reviews"),
            file=f".claude/commands/{name}.md",
        )

    # A retirement note deliberately names commands that are gone ("Retired: /loom"),
    # and the vendored `/aif-*` skills are not files in this directory. Neither is a
    # broken promise, so neither counts as an orphan.
    RETIRED = set(re.findall(r"\*\*Retired:\*\*\s*`/([a-z][a-z0-9-]*)`", section))
    for name in sorted(mentioned - on_disk - RETIRED):
        if name.startswith("aif"):
            continue
        result.blocker(
            id=f"orphaned-doc-{name}",
            summary=(f"{GUIDE.name} documents /{name} but .claude/commands/{name}.md does not "
                     f"exist — the prose outlived the command"),
            file=GUIDE.name,
        )

    if not result.findings:
        result.note(f"{len(on_disk)} slash command(s) on disk, all documented: "
                    f"{', '.join('/' + n for n in sorted(on_disk))}")

    print(result.render())
    if result.findings:
        print("\nEither document the command in AGENTS.md, or remove the stale mention. "
              "If you are retiring a runner, see docs/plans/2026-08-03-retire-unused-workflow-runners.md.")
    return result.exit_code()


if __name__ == "__main__":
    sys.exit(main())
