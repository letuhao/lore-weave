# `infra/terraform/postgres-shard/` — STUB (V1+30d)

## Status

**EMPTY by design.** Per Q-L1C-1 (locked):

> V1 shard provisioning: foundation V1 = docker-compose single shard;
> IaC for prod is V1+30d.

This directory is a **placeholder** so future Terraform PRs have a stable
target path. The actual `.tf` files (RDS instance, VPC subnets, parameter
groups, monitoring resources) will be added in the V1+30d staging-gate
sub-program.

## V1 substitute

Use `infra/docker-compose.meta-ha.yml` (cycle 1) for local dev + CI +
integration tests. The provisioner integration test in
`tests/integration/reality_lifecycle_test.go` runs against this stack.

## DEFERRED tracking

Tracked under `D-L1C-PROD-SHARD-IAC` in
`docs/deferred/DEFERRED.md` (Track 2 planning row):

- **Origin:** Cycle 5 (L1.C)
- **Target phase:** V1+30d staging-gate sub-program
- **Inputs needed:** AWS account selection, RDS instance class budget,
  multi-AZ vs single-AZ decision, KMS key rotation policy
- **Definition of done:** `terraform plan` cleanly applies to a fresh
  AWS account; smoke-test `psql` against the resulting endpoint
  succeeds from a bastion host.

## Why ship the empty dir now

So that:
1. `verify-cycle-5.sh` can grep for this README and confirm the
   placeholder is in place (no silent drift to a different path)
2. Cycle 6 (L1.D migration orchestrator) can reference this path in
   its `manifest.yaml` without a "path does not exist" warning
