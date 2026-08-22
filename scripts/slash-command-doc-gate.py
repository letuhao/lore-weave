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

    RETIRED: set[str] = set()
    for line in section.split("\n"):
        # Only the names INSIDE the bold marker are retired. A line-wide scan is
        # wrong, and was measured wrong: the real notice reads
        #   **Retired …: `/loom`, `/raid`, `/warp`, `/amaw`.** `/review-impl` is the
        #   only runner left…
        # so scanning the whole line retires the one command that is still live.
        # Harmless while RETIRED only excused orphaned prose; the moment it also had
        # to say what counts as DOCUMENTED, the survivor was reported undocumented.
        m = re.match(r"\s*(\*\*Retired\b.*?\*\*)", line)
        if m:
            RETIRED.update(re.findall(r"`/([a-z][a-z0-9-]*)`", m.group(1)))

    #: Vendor built-ins the guide legitimately discusses. They are commands, they are
    #: real, and they will never be files in `.claude/commands` — `/goal` appears in the
    #: run-discipline section and the `/goal-prompt` row cannot describe itself without
    #: naming what it emits. Same class as the `aif*` carve-out below, and enumerated for
    #: the same reason: nothing in a name distinguishes a vendor built-in from a runner
    #: this repo owes a file. Kept SMALL so that adding one is a decision, not a habit.
    BUILTINS = {"goal", "compact", "clear", "help", "config"}

    # A name that appears ONLY in a `**Retired…`** line is not documented, it is
    # contradicted: the file is still on disk while the prose says it is gone. Those
    # names are computed below, so this check is deferred until after them.
    for name in sorted(on_disk - (mentioned - RETIRED)):
        result.blocker(
            id=f"undocumented-{name}",
            summary=(f"/{name} exists in .claude/commands but {GUIDE.name} never mentions it — "
                     f"a runner nobody is told about is a runner nobody reviews"),
            file=f".claude/commands/{name}.md",
        )

    # A retirement note deliberately names commands that are gone ("Retired: /loom"),
    # and the vendored `/aif-*` skills are not files in this directory. Neither is a
    # broken promise, so neither counts as an orphan.
    # Only a line that STARTS with a bold `**Retired…` marker exempts the commands
    # named ON THAT LINE. Deliberately narrow: matching the whole paragraph would let
    # a live-but-undocumented runner hide next to a retirement note, which is the
    # blanket suppression this gate exists to avoid being.
    for name in sorted(mentioned - on_disk - RETIRED - BUILTINS):
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


def self_test() -> int:
    """Prove this gate can go RED — and that it does not cry wolf.

    `gate-teeth-gate` refuses a gate with no proof, and it is right to: this one
    ships three deliberate REFUSALS (a missing section, an empty command dir, a
    narrow retirement exemption) and every one of them is a path that, if it
    inverted, would turn the gate into a reassuring pass over nothing.
    """
    import tempfile

    fails: list[str] = []
    arms = {"red": 0, "clean": 0}

    def run(commands: list[str], guide_body: str) -> int:
        """Drive main() against a synthetic tree. Returns its exit code."""
        global COMMANDS_DIR, GUIDE
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cdir = root / ".claude" / "commands"
            cdir.mkdir(parents=True)
            for c in commands:
                (cdir / f"{c}.md").write_text(f"# /{c}\n", encoding="utf-8")
            guide = root / "AGENTS.md"
            guide.write_text(guide_body, encoding="utf-8")
            saved = (COMMANDS_DIR, GUIDE)
            COMMANDS_DIR, GUIDE = cdir, guide
            try:
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()):
                    return main()
            finally:
                COMMANDS_DIR, GUIDE = saved

    def want(label: str, rc: int, expect_red: bool) -> None:
        arms["red" if expect_red else "clean"] += 1
        if (rc != 0) != expect_red:
            fails.append(f"{label}: rc={rc}, expected {'non-zero' if expect_red else '0'}")

    SEC = "## Slash commands\n\n| Command | When |\n|---|---|\n"

    want("a documented command passes",
         run(["review-impl"], SEC + "| `/review-impl` | review |\n"), False)
    want("a command on disk that the guide never names REDS",
         run(["review-impl", "ghost"], SEC + "| `/review-impl` | review |\n"), True)
    want("a guide naming a command that does not exist REDS",
         run(["review-impl"], SEC + "| `/review-impl` | review |\n| `/gone` | ? |\n"), True)
    want("...unless a **Retired** line names it",
         run(["review-impl"],
             SEC + "| `/review-impl` | review |\n\n**Retired 2026-08-03: `/gone`.**\n"), False)
    want("prose AFTER the bold marker on a retirement line is not retired",
         run(["review-impl"],
             SEC + "| `/review-impl` | review |\n\n"
                   "**Retired: `/gone`.** `/review-impl` is the only runner left.\n"), False)
    want("a retirement line does NOT excuse a command that still EXISTS undocumented",
         run(["review-impl", "ghost"],
             SEC + "| `/review-impl` | review |\n\n**Retired: `/ghost`.**\n"), True)
    want("a `/aif-*` skill is not a file here and is not an orphan",
         run(["review-impl"], SEC + "| `/review-impl` | r |\n| `/aif-plan` | vendored |\n"), False)
    # The three refusals. Each one is a path where a wrong answer is SILENCE.
    want("no 'Slash commands' section is a FAILURE, not an empty scan",
         run(["review-impl"], "# Guide\n\nNo registry here.\n"), True)
    want("an empty commands dir is a FAILURE, not a vacuous pass",
         run([], SEC), True)
    want("an HTTP route in the section is not read as a command",
         run(["review-impl"], SEC + "| `/review-impl` | hits `/v1/worlds` |\n"), False)

    for f in fails:
        print(f"FAIL: {f}", file=sys.stderr)
    if fails:
        return 1
    print(f"slash-command-doc-gate: SELFTEST PASS — {arms['red']} arm(s) go RED "
          f"(undocumented command, orphaned mention, a retirement line that does not cover a live "
          f"runner, a missing registry section, an empty command dir) and {arms['clean']} stay "
          f"clean (documented command, retired mention, vendored /aif-*, an HTTP route)")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
