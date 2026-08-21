#!/usr/bin/env python3
"""Keep the per-agent skill renderings in lockstep.

WHY THIS EXISTS
---------------
AI Factory (https://github.com/lee-to/ai-factory, MIT) installs the SAME skill pack
once per agent target listed in `.ai-factory.json` — today `claude`, `cursor`,
`codex`, `codex-app` and `copilot`. Each tree is a generated rendering of one
upstream source, differing only by mechanical substitution: the install root, the
`npx skills install --agent <name>` flag, and the invocation sigil (`$aif-commit`
for Codex, `/aif-commit` for Claude/Copilot).

That is fine until somebody hand-edits ONE copy. Then two contributors running two
different agents silently follow two different processes on the same repository —
the exact failure the committed workflow is meant to prevent, and an invisible one,
because each copy looks self-consistent. Five near-identical 150-file trees are
also precisely what no human reviews line-by-line in a pull request.

So the parity is checked mechanically instead of trusted: normalise the documented
substitutions away, then require the renderings to be byte-identical. The target
list is read from the manifest, so adding a sixth agent puts it under the gate
without editing this file.

Run:  python scripts/agent-skills-parity.py
Wired as a pre-commit hook (see .githooks/pre-commit) and in CI.

If this fails, the fix is NOT to patch the other copies by hand — it is to change
the upstream skill and regenerate every target
(`npx ai-factory@<version> init --agents <all of them> --skills all`), so the next
regeneration does not silently revert your change. See
docs/standards/agent-workflow.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_result import GateResult  # noqa: E402  (repo-local helper; path set above)

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / ".ai-factory.json"

# `npx skills install --agent codex <name>` / `... --agent github-copilot <name>` /
# `... <name>` (codex-app passes no flag) all render the same instruction.
# The trailing \s+ is load-bearing: codex-app renders no flag at all, leaving a
# double space that would otherwise read as a difference.
_AGENT_FLAG = re.compile(r"npx skills install(?: --agent [A-Za-z0-9._-]+)?\s+")
# `$aif-commit` (Codex) vs `/aif-commit` (Copilot) — same command, different sigil.
_SIGIL = re.compile(r"[$/](aif[a-z-]*)")


def normalise(text: str, root: str) -> str:
    """Erase the three documented per-target substitutions.

    `root` is the target's install directory (".codex", ".agents", ".github"), which
    appears throughout the prose as `~/.codex/skills/...` and similar.

    Only `<root>/skills` is rewritten, never a bare `<root>/`. The copilot target
    installs into `.github`, and `.github/workflows` is a real GitHub Actions path
    that means the same thing in all three copies — normalising it away would make
    genuine drift in any CI skill invisible.
    """
    text = text.replace(root + "/skills", "<ROOT>/skills")
    text = _AGENT_FLAG.sub("npx skills install <AGENT> ", text)
    text = _SIGIL.sub(r"<SIGIL>\1", text)
    return text


# Known upstream RENDERING quirks — differences the generator itself produces, not a
# contributor hand-edit. Each needs a reason, and the gate reports an entry that has
# become unnecessary so this list shrinks instead of accumulating.
#
# Keyed by the skill-relative PATH, not by (target, path): which tree is canonical is
# whatever `ai-factory init` happens to list first in the manifest, and it moved once
# already when the `claude` target was added. A key that depends on that ordering
# turns a green gate red for a reason having nothing to do with the files.
KNOWN_RENDER_QUIRKS: dict[str, str] = {
    "aif/SKILL.md":
        "upstream renders the per-agent MCP-config path differently for each target "
        "(empty for one, a literal `.codex/config.toml` for another) and spells the "
        "install command per agent; all of them describe the same file",
}


def rel_files(base: Path, managed: set[str]) -> dict[str, Path]:
    """Files under `base` belonging to an aif-MANAGED skill.

    Scoped to the skills the manifest says the generator installed, because a skill
    directory also holds project-authored skills that legitimately live in ONE
    agent's tree — `.claude/skills/playwright-cli` is ours, not AI Factory's, and
    demanding it exist for Copilot would be nonsense.

    This enumeration is safe where a hand-written one would not be: the generator
    maintains `installedSkills` itself, so a skill it adds tomorrow is in scope the
    moment it lands, with nobody remembering to update a list.
    """
    if not base.is_dir():
        return {}
    out: dict[str, Path] = {}
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(base)).replace("\\", "/")
        if rel.split("/", 1)[0] in managed:
            out[rel] = p
    return out


def main() -> int:
    if not MANIFEST.is_file():
        print(f"agent-skills-parity: no {MANIFEST.name} — nothing to check.")
        return 0

    agents = json.loads(MANIFEST.read_text(encoding="utf-8")).get("agents", [])
    targets = [
        (a["id"], a["skillsDir"], "." + a["skillsDir"].split("/")[0].lstrip("."),
         set(a.get("installedSkills") or []))
        for a in agents
        if a.get("skillsDir")
    ]
    if len(targets) < 2:
        print("agent-skills-parity: fewer than two skill targets — nothing to compare.")
        return 0

    canon_id, canon_dir, canon_root, canon_managed = targets[0]
    if not canon_managed:
        print(f"agent-skills-parity: FAIL — {canon_id} lists no installedSkills in the manifest; "
              f"every comparison below would be trivially empty.")
        return 1
    canon_files = rel_files(REPO / canon_dir, canon_managed)
    if not canon_files:
        # An empty canonical tree would make every comparison trivially pass. That is
        # the "scope never reaches it" vacuity shape — fail loudly instead.
        print(f"agent-skills-parity: FAIL — canonical tree {canon_dir} is empty or missing.")
        return 1

    problems: list[str] = []
    accounted: set[str] = set()

    for agent_id, skills_dir, root, managed in targets[1:]:
        # Compare only skills BOTH targets are supposed to have. A target configured
        # with a narrower skill set is a legitimate choice, not drift.
        shared = canon_managed & managed
        files = rel_files(REPO / skills_dir, shared)
        canon_scoped = {k: v for k, v in canon_files.items() if k.split("/", 1)[0] in shared}

        for missing in sorted(set(canon_scoped) - set(files)):
            problems.append(f"{skills_dir}/{missing}: MISSING (present in {canon_dir})")
        for extra in sorted(set(files) - set(canon_scoped)):
            problems.append(f"{skills_dir}/{extra}: EXTRA (absent from {canon_dir})")

        for name in sorted(set(canon_scoped) & set(files)):
            a = canon_scoped[name].read_bytes()
            b = files[name].read_bytes()
            if a == b:
                continue
            try:
                na = normalise(a.decode("utf-8"), canon_root)
                nb = normalise(b.decode("utf-8"), root)
            except UnicodeDecodeError:
                problems.append(f"{skills_dir}/{name}: binary content differs from {canon_dir}")
                continue
            key = name
            if na != nb:
                if key not in KNOWN_RENDER_QUIRKS:
                    problems.append(
                        f"{skills_dir}/{name}: differs from {canon_dir}/{name} beyond the "
                        f"documented per-agent substitutions"
                    )
                else:
                    accounted.add(key)
            elif key in KNOWN_RENDER_QUIRKS:
                problems.append(
                    f"{skills_dir}/{name}: now matches {canon_dir}/{name} — delete its "
                    f"KNOWN_RENDER_QUIRKS entry in scripts/agent-skills-parity.py"
                )

    for stale in sorted(set(KNOWN_RENDER_QUIRKS) - accounted):
        problems.append(
            f"{stale}: has a KNOWN_RENDER_QUIRKS entry but now renders identically in every "
            f"target — remove the stale entry"
        )

    # Reported through the shared `aif-gate-result` contract (adopted from AI Factory —
    # see scripts/gate_result.py) so any orchestrator reads this gate the same way it
    # reads $aif-verify, instead of needing one parser per gate.
    result = GateResult(
        gate="rules",
        suggested_command="/aif-fix" if problems else None,
        suggested_reason=(
            "regenerate the per-agent skill renderings from one upstream source"
            if problems else None
        ),
    )
    for i, problem in enumerate(problems, start=1):
        path, _, summary = problem.partition(": ")
        result.blocker(id=f"skills-parity-{i}", summary=summary or problem, file=path)

    if not problems:
        checked = len(canon_files) * len(targets)
        result.note(
            f"{len(targets)} agent targets ({', '.join(t[0] for t in targets)}), "
            f"{checked} files in lockstep"
        )

    print(result.render())
    if problems:
        print(
            "\nEdit the upstream skill and REGENERATE all targets; do not hand-patch one\n"
            "copy (a regeneration would silently drop it). See docs/standards/agent-workflow.md."
        )
    return result.exit_code()


if __name__ == "__main__":
    sys.exit(main())
