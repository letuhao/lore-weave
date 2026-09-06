# Changelog

All notable changes to LoreWeave are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) — with the pre-1.0 caveat
SemVer itself states in [item 4](https://semver.org/spec/v2.0.0.html#spec-item-4): while the
major version is `0`, anything may change at any time, and a MINOR bump (`0.x.0`) can carry a
breaking change. `0.1.0` is the first tagged release; nothing before it is versioned.

**This file is the source of truth for what shipped in each release, not a summary written
after the fact.** `scripts/changelog-gate.py` enforces the one invariant that makes that true:
a release cannot be cut (`.github/workflows/oss-release.yml` fails closed) unless the version
being tagged has a matching `## [x.y.z]` section here with real content. The `/oss-publish`
skill is what moves entries from `[Unreleased]` into a dated version section when a release is
cut — see `docs/standards/versioning-and-releases.md` for the full policy (bump rules,
pre-release identifiers, what "release" vs "pre-release" means for this repo, artifact scope).

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

### Security

<!--
  Entries go under the section matching their kind, newest first within a section. A line
  should name the user-visible effect, not the implementation: "chapter drag-and-drop no longer
  loses unsaved edits" reads as a changelog; "fix race in useChapterOrder debounce" reads as a
  commit message these two are not obligated to look the same. Link a PR/issue where one exists.

  Dependency-bump PRs (dependabot) are exempt from adding their own entry per PR — that would be
  pure noise across dozens of routine bumps. They land in the release's own entry (usually under
  Changed, or Security when the bump closes a CVE) written once, at cut time, by whoever runs
  `/oss-publish`, summarizing what actually moved rather than listing every PR number.
-->
