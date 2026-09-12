# Security Policy

## Supported Versions

LoreWeave is pre-1.0 (see [`docs/standards/versioning-and-releases.md`](../docs/standards/versioning-and-releases.md)
for what that means for this project). Only the **latest published release** gets security
fixes — there is no separate maintenance branch for older tags.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for a security vulnerability.**

Use GitHub's private vulnerability reporting instead: go to the
[Security tab](../../security/advisories/new) and click **"Report a vulnerability"**. That
opens a private advisory only you, the maintainer, and (once you both agree) anyone you invite
can see — nothing becomes public until a fix is ready and you choose to publish it.

If the Security tab's report button isn't available for any reason, open a regular issue asking
the maintainer to enable private reporting, without describing the vulnerability itself.

## What to expect

This is a hobby project maintained by one person (see
[`CONTRIBUTING.md`](../CONTRIBUTING.md#7-the-workflow) — "no deadline pressure" applies here
too), so there's no SLA to promise. In practice: a real report gets read promptly, and a fix
that's clearly in scope gets prioritized over other work. If a report turns out to be a
misconfiguration or expected behavior rather than a vulnerability, you'll get an honest answer
saying so, not silence.

## Scope

This covers LoreWeave's own code and the images built from
[`infra/docker-compose.yml`](../infra/docker-compose.yml). It does not cover:

- Vulnerabilities in third-party dependencies with no LoreWeave-specific exploit path (report
  those upstream; a dependency-bump PR is still welcome here)
- A deliberately insecure **local-development default** that's already documented as such (e.g.
  the `_change_me`/`dev_*`-shaped secrets in `infra/docker-compose.yml`, all documented in
  [`infra/.env.example`](../infra/.env.example) with the real override path) — those are a
  known, intentional dev convenience, not a report-worthy finding, unless you've found one that
  is genuinely undocumented or has no override path at all
