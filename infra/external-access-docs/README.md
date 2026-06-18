# External Access Docs — Out-of-band Mirror

> **Layer:** L7.B.19 (RAID cycle 35) · **Spec:** SR03 §12AF.9 + problem 9

This directory is the source for the **out-of-band runbook mirror** — a curated
subset of runbooks + access procedures hosted on S3 + CloudFront, accessible
when the primary observability stack (CloudWatch, Vault, Grafana, SSO) is
itself part of the incident.

## Why this exists

SR3 problem 9: "External access documentation during incident (when AWS/Vault
may be down)". If the SRE cannot SSO into Grafana because the auth-service is
the incident, they need a phone-readable URL that returns markdown.

## Hosting

| Layer | Detail |
|---|---|
| Origin | S3 bucket `loreweave-sre-oob-docs` (private — CloudFront OAI) |
| CDN | CloudFront distribution with WAF allowlist by IP+JWT |
| URL | `https://oob.sre.loreweave.dev/` |
| Auth | Static bearer token in 1Password (`sre-oob-cf-token`); rotated quarterly |
| Sync | `scripts/oob-docs-sync.sh` (V1+30d cron; cycle-35 V1 manual) |

## What is mirrored

V1 manual sync — copy the following to S3 by hand on every release tag:

- `docs/sre/runbooks/generic/escalation-chains.md`
- `docs/sre/runbooks/generic/new-on-call-first-day.md`
- `docs/sre/runbooks/generic/i-don-t-know-what-s-wrong.md`
- `docs/sre/runbooks/admin/break-glass.md`
- `docs/sre/runbooks/meta/failover-to-standby.md`
- `docs/sre/runbooks/meta/write-audit-hash-mismatch.md`
- `docs/governance/oncall-sla.md`
- `infra/pagerduty/rotation_schedule.yaml`
- `infra/pagerduty/escalation_policy.yaml`

The mirror is intentionally SMALL — the on-call only needs the "I cannot
reach the platform" recovery surface, not the full library.

## Break-glass access

If the CloudFront URL is itself down (rare — separate AWS account from prod):

1. Pull from S3 directly via aws-cli with the IAM access keys in the founder's
   safe (`s3://loreweave-sre-oob-docs/`).
2. If AWS is the incident, pull from the static-site backup at GitHub Pages
   (private repo, mirrored hourly): `https://loreweave.github.io/sre-oob/`.
3. If GitHub Pages is also down, the founder has a printed copy of the top-3
   runbooks (escalation-chains, break-glass, failover-to-standby) in the
   physical safe at the office. V2+ when paid tier launches.

## Sync procedure (manual V1)

```bash
# From repo root, after a release tag:
bash scripts/oob-docs-sync.sh --dry-run
# Verify the file list matches the "What is mirrored" section above.
bash scripts/oob-docs-sync.sh --apply
```

V1+30d this becomes a CI job on every PR touching `docs/sre/runbooks/generic/`
or `docs/governance/oncall-sla.md`.

## References

- SR3 §12AF.9 — external access protocol
- SR3 problem 9 — accessibility when primary stack is down
- `docs/sre/runbooks/README.md` — full library
- LOCKED Q-L7B-1 — stub allowance (mirrored runbooks may be stubs; flag visibly)
