"""A gate's answer is about a TREE, so record which tree it was about.

🔴 **THE RULE THIS ENFORCES IS NOT "RUN FEWER GATES".** That rule produces unverified work, and
*"I thought nothing had changed"* is how F-50 survived two days inside three green instruments. The
property is:

    a gate's recorded answer must be about the tree you are committing.

Speed is a **consequence**, not the goal: if the recorded answer is already about this tree, there
is nothing to run. If it is not, the gate must run before the commit. Both halves matter, and the
second is the one that was missing.

**Measured, on the session that motivated this.** Roughly two hours went to gates: the census five
times (two of those on trees whose mirrored content had not changed at all), `falsification --run`
four times, the suite six. The batching discipline existed — *"run the gates once per row, at the
end"* — as **prose, in the session's own instructions**, and it was violated inside the hour: the
census ran, two test files were then edited, and the verdict it produced was about a tree that no
longer existed. An invariant that is only written down is one this project has watched fail eleven
times.

WHY THE KEY IS THE MIRROR AND NOT A GUESS
-----------------------------------------
Both gates measure by copying a subset of the tracked tree into a throwaway mirror and running the
suite there. **That subset is exactly what the measurement is able to read.** So the digest of the
mirrored file set is not an assumption about what the answer depends on — it is the same set the
answer is computed from. A file outside it cannot change the verdict; if one could, the gate was
non-deterministic before this module existed.

That is the whole reason this cache needs no approximation, and it is why the *tempting* next step
is deliberately not taken here: **per-site incremental** — *"only re-measure sites in modules that
changed"* — requires the extra claim that editing module A cannot flip a site in module B. Plausible,
unproven, and this run's record on unproven keys is poor. If it is ever wanted it goes in as a
STATED approximation with a full run at each checkpoint close, so the thing that would catch a bad
key runs on a schedule rather than never.

CI IS STILL THE AUTHORITY
-------------------------
`.github/workflows/lint-foundation.yml` runs both gates with `--force`, so a cached verdict can
never be the last word on a branch. The cache accelerates the inner loop; CI re-derives it from
nothing. A cache that could be the final answer would be a way to commit a verdict nobody computed.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: What a gate's mirror contains — **measured, not guessed: 1,333 of 13,599 tracked files, 7%.**
#: The census used to copy the whole repository (214.8 MB, one `copyfile` at a time) for a suite
#: that runs inside a single directory; with one mirror per parallel worker that setup cost became
#: the thing the run spent its time on rather than the measurement.
#:
#: 🔴 This list is a claim, and **its falsifier already runs on every invocation**: the census
#: selftest requires the FULL suite green in a mirror *before any injection*, so a prefix that
#: belongs here and is absent stops the run in seconds and names the missing path. It did exactly
#: that once already (`.github/workflows/`, read by a guard asserting the gate runs in CI).
MIRROR_PREFIXES: tuple[pathlib.Path, ...] = (
    pathlib.Path("services") / "chat-service",                                  # suite + subject
    pathlib.Path("scripts"),                                                    # gates read gates
    pathlib.Path("contracts"),                                                  # baseline, allowlists
    pathlib.Path(".github"),                                                    # a guard reads CI
    pathlib.Path("docs") / "specs" / "2026-08-03-agent-runtime-unification",    # guards parse it
    # 🔴 **ADDED 2026-08-09 BY THE SELFTEST, WHICH IS THE SECOND TIME THIS LIST HAS BEEN CORRECTED
    # THAT WAY.** `test_ts_source_is_present` asserts ai-gateway's `propose-edit-tool.ts` exists —
    # it is the drift-lock for a description this service advertises and the gateway owns — so a
    # mirror without it fails before any injection. Same shape as `.github/workflows/` earlier: the
    # prefix list is a CLAIM about what a measurement must see, and its falsifier runs on every
    # invocation rather than being written down.
    pathlib.Path("services") / "ai-gateway" / "src",
    # 🔴 **AND THIS ONE IS A FINDING ABOUT THE INSTRUMENT, NOT JUST A MISSING PATH.**
    # `services/chat-service/pytest.ini` pins `pythonpath = ../../sdks/python` — RELATIVE — so inside
    # a mirror that directory does not exist and the import silently falls back to whatever
    # `site-packages` holds. The gate was therefore measuring the suite against a **different SDK
    # than the suite pins**, and it surfaced as `StepProgress.__init__() got an unexpected keyword
    # argument 'session_done'`: the checkout's SDK had a field the installed copy did not. A
    # measurement that resolves different code than the thing it measures is the shape this whole
    # instrument exists to refuse, so the mirror now carries the SDK the pin names.
    pathlib.Path("sdks") / "python",
)

#: 🔴 **A VERDICT FILE MUST NOT BE PART OF ITS OWN KEY.** They live under `contracts/`, which is
#: mirrored — so writing one would change the digest that certifies it and every verdict would be
#: stale the instant it was recorded. Excluded by name, and the exclusion is by *suffix* so a new
#: gate cannot reintroduce the cycle by picking a new filename.
VERDICT_SUFFIX = "-verdict.json"


def _tracked() -> list[str]:
    listing = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    return [rel.decode("utf-8") for rel in listing.split(b"\0") if rel]


def is_mirrored(rel: str) -> bool:
    """Would a gate's mirror contain this tracked path? **The filter, as one testable function.**

    Split out so the verdict-file exclusion can be checked directly. Asserting it over the tracked
    set instead would be vacuous — verdict files are git-ignored, so they never appear there, and a
    guard whose subject cannot exist is one of this run's named failure shapes.
    """
    prefixes = tuple(str(p).replace("\\", "/") + "/" for p in MIRROR_PREFIXES)
    return rel.startswith(prefixes) and not rel.endswith(VERDICT_SUFFIX)


def mirrored_files() -> list[str]:
    """Tracked paths a gate's mirror would contain, sorted. The WORKING tree, not `HEAD`.

    These run as pre-commit gates, so what must be measured is what is about to be committed.
    """
    out = [rel for rel in _tracked() if is_mirrored(rel) and (ROOT / rel).is_file()]
    return sorted(out)


def tree_digest() -> str:
    """One digest over every mirrored file: its path AND its bytes.

    The path is hashed too, so ADDING or DELETING a file moves the digest even when no surviving
    file's content changed — a new test is exactly the kind of change that can flip a verdict, and a
    content-only digest would call the old answer current.
    """
    h = hashlib.sha256()
    for rel in mirrored_files():
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        # Line endings normalised: this tree is CRLF in one checkout and LF in another, and a
        # digest that moves with the checkout would report every fresh clone as stale.
        h.update(hashlib.sha256(
            (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")).digest())
    return h.hexdigest()


def load(path: pathlib.Path) -> dict | None:
    """The recorded verdict, or None when there is not one for THIS tree.

    Returns None rather than a stale payload on purpose: every caller's next move is *run the gate*,
    and handing back an answer about a different tree is the failure this module exists to remove.
    """
    if not path.exists():
        return None
    try:
        rec = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return rec if rec.get("tree_digest") == tree_digest() else None


def store(path: pathlib.Path, payload: dict, *, digest: str) -> None:
    """Record a verdict against the digest the measurement was TAKEN on.

    🔴 **THE DIGEST IS A PARAMETER, AND THE FIRST VERSION COMPUTED IT HERE.** These runs take
    minutes; a file edited while one is in flight would have been stamped into the verdict as though
    it had been measured, and the gate would then certify a tree it never saw. That is exactly the
    *measured-on-a-dirty-tree* failure this run has already paid for once — a correct diagnosis
    retracted because the re-measurement carried an unrelated edit — reproduced inside the mechanism
    built to end it. Callers capture the digest BEFORE they start and hand it in.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body["tree_digest"] = digest
    # `\n`, explicitly: a `write_text` default newline turned into CRLF once already in this run and
    # broke a manifest digest in production. The gate that certifies the tree must not depend on
    # which platform wrote it.
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def check(path: pathlib.Path, label: str) -> int:
    """`--check`: is the recorded verdict about this tree? Prints and returns an exit code."""
    if not path.exists():
        print(f"{label}: NO RECORDED VERDICT - run the gate")
        return 1
    rec = load(path)
    if rec is None:
        print(f"{label}: STALE - the recorded verdict is about a different tree. "
              f"Something under {', '.join(str(p) for p in MIRROR_PREFIXES)} changed since it ran.")
        return 1
    print(f"{label}: current for this tree ({rec['tree_digest'][:12]})")
    return 0
