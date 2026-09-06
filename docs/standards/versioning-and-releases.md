# Versioning & Releases

**Status: LOCKED** — enforced by `scripts/changelog-gate.py` (structural check in `all-gates`
on every push; `--release X.Y.Z` mode in `.github/workflows/oss-release.yml` at tag time).

This governs the three things a release touches: the version number, the changelog entry that
justifies it, and the artifacts that get published. It does not govern day-to-day development —
only the moment work becomes a numbered release someone outside this repo can depend on.

## 1. Versioning: SemVer 2.0.0, with the pre-1.0 caveat taken literally

Versions are `MAJOR.MINOR.PATCH` per [SemVer 2.0.0](https://semver.org/spec/v2.0.0.html), with
an optional pre-release identifier (`-alpha.N`, `-beta.N`, `-rc.N`).

`v0.1.0` is the first tagged release. While the major version is `0`, [SemVer's own item
4](https://semver.org/spec/v2.0.0.html#spec-item-4) applies without softening: **anything may
change at any time, and a MINOR bump can carry a breaking change.** This is a real statement
about this project's current maturity, not an oversight to fix later — 1.0.0 is the commitment
that the public surface has stabilized, and this repo has not made that commitment yet. Don't
invent a stricter pre-1.0 policy (e.g. "we'll still bump MAJOR for breaks") — it creates an
expectation SemVer explicitly disclaims for `0.x`, which is a worse failure than the plain
reading.

**Pre-release identifiers**, when used, are `-alpha.N` → `-beta.N` → `-rc.N` in that order
(N starts at 1 per stage). Per [SemVer item
11](https://semver.org/spec/v2.0.0.html#spec-item-11), `0.2.0-rc.1` sorts BEFORE `0.2.0` —
`scripts/changelog-gate.py`'s ordering check honors this, so don't "fix" a changelog that
appears to list a pre-release after its final release; that order is correct.

## 2. Pre-release vs. release — the only two categories, mapped onto GitHub's own

A published version is either:
- **pre-release** — the tag has a SemVer pre-release identifier (`v0.2.0-rc.1`). Marked
  `prerelease: true` on the GitHub Release. Gets its own version-tagged Docker images
  (`ghcr.io/.../<service>:v0.2.0-rc.1`); does **not** move the `:latest` tag.
- **release** — a plain `vX.Y.Z` tag. Full GitHub Release. Gets version-tagged images AND moves
  `:latest`.

No third category. This is deliberately GitHub's own `prerelease` boolean, not an invented
taxonomy — anything that needs a finer grain (an internal-only build, say) is not a *release* in
this repo's sense and doesn't get a tag.

## 3. The changelog is the SSOT — enforced, not aspirational

[`CHANGELOG.md`](../../CHANGELOG.md) follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/): an `## [Unreleased]` section at the top,
dated `## [x.y.z] - YYYY-MM-DD` sections below it in newest-first order, entries grouped under
`Added`/`Changed`/`Fixed`/`Removed`/`Security`.

**"SSOT" means a specific, checked claim: a version cannot be released unless CHANGELOG.md
names that exact version with real content.** `scripts/changelog-gate.py --release X.Y.Z`
is what checks it, and `oss-release.yml` runs that check before building a single image — see
the gate's own docstring for the two-mode split (structural, every push; release, at tag time)
and why per-PR "did your diff need an entry" enforcement is deliberately NOT attempted (a
filename-pattern heuristic for "is this user-visible" is wrong often enough to become background
noise; see `docs/standards/README.md`'s own meta-pattern note on why every gate here picks a
narrow, unambiguous thing to assert rather than a fuzzy one).

Practically: entries accumulate in `[Unreleased]` by hand as work lands (dependency-bump PRs are
exempt — see the comment in `CHANGELOG.md` itself), and the `/oss-publish` skill is what moves
them into a dated version section at cut time, summarizing rather than listing every PR.

## 4. Artifacts: per-service Docker images, tagged with the version

A release publishes one Docker image per buildable service, derived from
`infra/docker-compose.yml` by `scripts/oss/release-targets.py` — **not** a hand-maintained list
(same reasoning as `dependabot.yml`'s directory globs: a written-down list goes stale the moment
a service is added, silently). Images push to `ghcr.io/<org>/<service>`, tagged `:vX.Y.Z`
always, `:latest` only for a non-pre-release. `postgres` is excluded (base-image customization,
not a LoreWeave service) — see `EXCLUDE` in that script for the current, named exclusion list.

This repo does not publish to a package registry (PyPI/npm/crates.io) as part of this process.
If an SDK under `sdks/` ever needs standalone distribution, that's a separate, additive decision
— it does not change what "cutting a release" means for the platform as a whole.

## 5. How a release actually gets cut

1. Run the `/oss-publish` skill (`.claude/skills/oss-publish/SKILL.md`). It reads commits/PRs
   since the last tag and the accumulated `[Unreleased]` section, drafts the version's changelog
   entry, and asks for the version bump and pre-release/release decision.
2. It moves `[Unreleased]` content into a new `## [X.Y.Z] - <date>` section, commits
   `CHANGELOG.md`, creates and pushes the `vX.Y.Z` tag.
3. Pushing the tag triggers `oss-release.yml`: changelog SSOT check → derive image targets →
   build + push every image → create the GitHub Release from the changelog section.

No step here merges or pushes to `main` on its own authority beyond what committing the
changelog and pushing a tag requires — cutting a release is still a human decision made by
running the skill, not something that fires on its own.
