# infra/minio — MinIO bucket provisioning

LOCKED Q-L1H-1 2026-05-29: MinIO is **pre-existing** for the LoreWeave novel
platform (front-end BLOB store). Foundation adds ONLY the dedicated
`lw-db-backups` bucket for L1.H database backups so the backup data is
isolated from the assets bucket (different lifecycle, RBAC, IO budget).

## V1 vs V1+30d

| What | V1 | V1+30d |
|---|---|---|
| Bucket creation | manual `mc mb lw-platform/lw-db-backups` | `terraform apply infra/minio/` |
| Policy attachment | manual via `mc admin policy add` | terraform-managed |
| Lifecycle rules | dev `mc admin bucket lifecycle add` | terraform-managed |
| Versioning | `mc version enable` | terraform-managed |

Per Q-L1C-1 cycle 5 STUB pattern: this directory ships the `.tf` body but
**no `provider "minio"` block** — `terraform plan` will refuse cleanly until
the prod-config commit lands at V1+30d.

## Bucket contract

- **Bucket name:** `lw-db-backups`
- **Lifecycle:** objects expire 30d max; `backup-scheduler` does early-delete
  for shorter-tier objects per `contracts/backup/policy.yaml`.
- **Versioning:** ENABLED (defense against accidental deletion).
- **Object-lock:** NOT enabled V1 (blocks lifecycle expiry). Revisit V2+ if
  regulator requires.
- **RBAC:**
  - `backup-scheduler` SVID → `lw-db-backups-writer` policy (PUT/GET/DELETE/LIST)
  - `sre`, `admin-cli` SVIDs → `lw-db-backups-reader` policy (GET/LIST only)
  - everyone else → DENY

## Manual V1 bootstrap

```bash
# Configure mc alias pointing at the foundation docker-compose MinIO
mc alias set lw-local http://minio:9000 minio minio123

# Create the bucket (idempotent)
mc mb --ignore-existing lw-local/lw-db-backups

# Enable versioning
mc version enable lw-local/lw-db-backups

# Apply expire-30d lifecycle
cat > /tmp/lifecycle.json <<'EOF'
{
  "Rules": [
    {
      "ID": "expire-stale-backups",
      "Status": "Enabled",
      "Expiration": { "Days": 30 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 7 }
    }
  ]
}
EOF
mc ilm import lw-local/lw-db-backups < /tmp/lifecycle.json
```

## Restore-drill integration

`scripts/restore-drill.sh` reads from `lw-db-backups` via the
`lw-db-backups-reader` policy and writes a row into `archive_verification_log`
(meta table) on success. On failure, the script exits non-zero which drives
a PagerDuty alert per `infra/prometheus/alerts/meta.yaml::BackupDrillFailed`.
