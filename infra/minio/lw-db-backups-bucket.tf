# infra/minio/lw-db-backups-bucket.tf — dedicated MinIO bucket for L1.H backups.
#
# LOCKED Q-L1H-1 2026-05-29: MinIO is pre-existing for the LoreWeave novel
# platform's BLOB storage; foundation adds ONLY this dedicated bucket so backup
# data is isolated from front-end assets (different lifecycle, different access
# pattern, different RBAC).
#
# V1 ships as a STUB README pattern (cycle 5 / Q-L1C-1: foundation V1 =
# docker-compose; IaC for prod V1+30d). The .tf body below is the prod
# topology and intentionally NOT applied yet — `terraform plan` would refuse
# because no provider is configured. See infra/minio/README.md.
#
# When V1+30d ships:
#   1. Add `provider "minio"` block in a sibling file (read endpoint from env)
#   2. Run `terraform plan` to confirm the bucket would be created idempotent
#   3. Apply and validate via `mc ls lw-platform/lw-db-backups`
#
# Bucket policy lockdown:
#   * Only `backup-scheduler` SVID may PUT / DELETE
#   * Only `backup-scheduler` + `sre` role may LIST / GET
#   * Versioning ENABLED (defense against accidental deletion)
#   * Object-lock NOT enabled in V1 (would block lifecycle expiry); revisit V2+
#     if regulatory requirement adds (then enable retention-mode = GOVERNANCE
#     with the retention_days from contracts/backup/policy.yaml).
#
# Lifecycle: expire objects per policy.yaml tier retention_days. Since the same
# bucket holds multiple tiers, the bucket lifecycle rule applies the MAX
# retention (30d) and the backup-scheduler does per-object early-delete on
# tiers with shorter retention.

resource "minio_s3_bucket" "lw_db_backups" {
  bucket         = "lw-db-backups"
  acl            = "private"
  force_destroy  = false    # safety: refuse `terraform destroy` if non-empty

  versioning {
    enabled = true
  }

  lifecycle_rule {
    id      = "expire-stale-backups"
    enabled = true
    expiration {
      days = 30  # max tier retention; per-object early-delete by backup-scheduler
    }
    noncurrent_version_expiration {
      days = 7   # keep 1 prior version 7d for rollback
    }
  }
}

# Bucket policy: backup-scheduler full access; sre + admin read-only.
resource "minio_iam_policy" "lw_db_backups_writer" {
  name = "lw-db-backups-writer"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetObjectVersion",
        ]
        Resource = [
          "arn:aws:s3:::lw-db-backups",
          "arn:aws:s3:::lw-db-backups/*",
        ]
      },
    ]
  })
}

resource "minio_iam_policy" "lw_db_backups_reader" {
  name = "lw-db-backups-reader"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetObjectVersion",
        ]
        Resource = [
          "arn:aws:s3:::lw-db-backups",
          "arn:aws:s3:::lw-db-backups/*",
        ]
      },
    ]
  })
}
