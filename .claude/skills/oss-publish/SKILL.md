---
name: oss-publish
description: Cut a versioned LoreWeave release — draft the CHANGELOG.md entry from what shipped since the last tag, confirm the SemVer bump and pre-release/release decision with the user, then tag and push to trigger the automated build + GitHub Release. Use when the user says "cut a release", "publish v...", "ship v0.1.0", "make a release", or asks what's changed since the last version.
argument-hint: "[version | 'check' | 'draft']"
allowed-tools: Read Write Edit Bash(git *) Bash(gh *) Bash(python scripts/changelog-gate.py *) AskUserQuestion
disable-model-invocation: false
metadata:
  author: LoreWeave
  version: "1.0"
  category: release
---

# /oss-publish — cut a versioned release

Reads what actually shipped since the last tag, drafts the `CHANGELOG.md` entry, gets the
version-bump decision from a human (never inferred silently), then tags and pushes — which is
the one action that triggers `.github/workflows/oss-release.yml` to build every service image
and publish the GitHub Release. See
[`docs/standards/versioning-and-releases.md`](../../../docs/standards/versioning-and-releases.md)
for the policy this skill implements; this file is the procedure, that doc is the authority —
if they ever disagree, the standards doc wins and this file has drifted.

## Why this is a skill and not just "edit the changelog and tag it"

Three things need to happen **in order** and the order matters: draft → human confirms the
version number and release/pre-release status → changelog is written and self-checked → THEN
tag and push. Tagging first and asking questions after means `oss-release.yml` has already
fired on a version nobody actually chose. This skill exists to keep those in sequence, and to
make step 2 an actual question (`AskUserQuestion`), not a guess dressed as one — a version
number is a promise to whoever pulls the tag, not a formatting choice.

## Step 0 — orient

1. `git fetch --tags` then find the last release: `git tag --list 'v*' --sort=-v:refname | head
   -1`. If empty, **this is the first release** — the version floor is `v0.1.0`, not something
   to derive (see `docs/standards/versioning-and-releases.md` §1; it is the literal starting
   point this project chose, not a default this skill invented).
2. Read `CHANGELOG.md`. Note what's already sitting under `## [Unreleased]` — entries land there
   by hand as work merges, so this is not starting from zero even on a fresh repo.
3. Run `python scripts/changelog-gate.py` (structural mode, no `--release`). If it fails, STOP
   and fix `CHANGELOG.md`'s structure before doing anything else — everything below assumes a
   well-formed file to parse and rewrite.

If the user's argument was `check`, stop here and just report: last tag, current
`[Unreleased]` contents, and whether the changelog is structurally clean. Don't draft or tag.

## Step 1 — gather what shipped

1. `git log <last-tag>..HEAD --oneline` (or the full history if there is no last tag) for the
   raw commit list.
2. `gh pr list --state merged --search "merged:>=<last-tag date>"` (or `--base main` with no
   date filter for the first release) for PR-level titles and numbers — usually a cleaner unit
   than individual commits, since squash-merged PRs collapse a feature's commit noise to one
   line already.
3. **Ask the user what this release should headline as shipping** — don't only derive silently
   from git history. Something like: *"Here's what I found merged since <last-tag>: [list].
   Anything missing, anything that shouldn't be called out, or a theme you want this release to
   lead with?"* This is the "capture the user's shipping requirement" step — git history says
   what CHANGED, only the user reliably knows what actually MATTERS to call out for this
   version's audience.
4. Classify each item into Keep a Changelog's buckets (`Added`/`Changed`/`Fixed`/`Removed`/
   `Security`) by what it reads as to someone outside this repo, not by its commit-type prefix
   verbatim — a `fix:` commit that closes a CVE goes under `Security`, not `Fixed`, because that
   is the fact a consumer actually needs surfaced. Dependency-bump PRs (dependabot) do NOT get
   one line each — summarize them once (e.g. *"Updated `fastapi`, `boto3`, and 6 other
   dependencies to their latest patch releases"*), per the exemption already noted inside
   `CHANGELOG.md` itself.

## Step 2 — the version decision (never silent)

Ask the user directly — this is a real `AskUserQuestion`, not a default this skill picks for
them:

- **If there is no prior tag:** the version IS `0.1.0`. Confirm it, don't re-derive it — but
  still ask whether this first release is itself a pre-release (`0.1.0-rc.1`, `0.1.0-beta.1`)
  or the real `0.1.0`.
- **Otherwise**, given the drafted entries from Step 1, ask which applies (SemVer 2.0.0, with
  the pre-1.0 reading `docs/standards/versioning-and-releases.md` §1 states plainly — while
  major is `0`, MINOR is the ceiling either a breaking change or a new feature bumps to; PATCH
  is fixes-only; MAJOR is reserved until this project commits to `1.0.0`):
  - **PATCH** (`x.y.Z+1`) — fixes/dependency bumps only, nothing new or changed in behavior.
  - **MINOR** (`x.Y+1.0`) — new features, or ANY breaking change (pre-1.0 — see above).
  - **Pre-release** of either — append `-alpha.N` / `-beta.N` / `-rc.N` (stage order in that
    sequence; N starts at 1 per stage). This is the pre-release/release brand split GitHub's
    own `prerelease` flag reads at publish time.

Compute the final version string from the answer. Do not proceed past this step on an assumed
answer, including "obviously patch" — the cost of asking is one question; the cost of guessing
wrong is a published tag, which this repo's own convention treats as something you don't undo
by force-pushing over it.

## Step 3 — write the changelog entry

1. In `CHANGELOG.md`, insert a new section directly below `## [Unreleased]`:
   `## [X.Y.Z] - <today, YYYY-MM-DD>`, populated with the classified entries from Step 1 under
   their Keep a Changelog subheadings (omit empty subheadings in the new section — the seed
   file keeps them empty at the top only so contributors know the vocabulary).
2. Reset `## [Unreleased]` back to the empty subheading template (see the current top of the
   file for the exact shape) — anything moved into the new version section is removed from
   here, not duplicated.
3. Run `python scripts/changelog-gate.py --release X.Y.Z`. If it fails, the edit is wrong —
   fix it and re-run before touching git. This is the same check `oss-release.yml` runs at tag
   time; failing it here is cheap, failing it there means redoing this step anyway after a
   failed workflow run.

## Step 4 — commit, tag, push (confirm before this line)

**Stop and get an explicit go-ahead before this step.** Pushing a `v*` tag is what triggers
`oss-release.yml`: it builds and pushes ~41 Docker images to `ghcr.io` and publishes a public
GitHub Release. That is outward-facing and not casually reversible (images are pullable the
moment they push; a GitHub Release can be deleted but a tag someone already pulled cannot be
un-pulled) — this is exactly the class of action this project's own working convention treats
as needing a human's explicit yes, not an inferred one from "the changelog looks done."

Once confirmed:
```bash
git add CHANGELOG.md
git commit -m "docs(changelog): v X.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

Then tell the user: the tag push just triggered `oss-release.yml` (link:
`https://github.com/<org>/<repo>/actions/workflows/oss-release.yml`); it will fail closed at
the changelog gate if anything about this got out of sync, before building a single image.

## Guardrails

- Never invent a version number the user hasn't confirmed, including for a "trivial" release.
- Never tag/push without the Step 4 confirmation, even if every earlier step went cleanly.
- Never let a dependency-bump PR accumulate its own changelog line — summarize once per
  release, per the exemption already written into `CHANGELOG.md`.
- If `scripts/changelog-gate.py` fails at ANY point, that is the file telling you it is
  currently unsafe to release from — fix the structure, don't work around the check.
