# infra/minio/lw-event-archive-bucket.tf — L2.J.3 dedicated MinIO bucket for
# cold-tier archived event partitions.
#
# Cycle 11 (2026-05-29). LOCKED Q-L2J-1: archive-worker is a DEDICATED service
# (mirrors publisher pattern from cycle 10); it owns this bucket.
#
# WHY A NEW BUCKET (separate from cycle-7 `lw-db-backups`)?
#   * Different LIFECYCLE: db-backups expire at 30d (max tier retention).
#     Event-archive is FOREVER — once a partition is archived, the only legal
#     "delete" is per the L2.J restore-then-recompact escape hatch, which
#     happens out-of-band. Sharing the bucket would force one rule to win.
#   * Different ACCESS PATTERN: backups are read on disaster-recovery drills
#     only (low IOPS). Event-archive can serve restore-on-demand for any
#     ad-hoc forensic query (medium IOPS, by reality+month key prefix).
#   * Different RBAC: archive-worker SVID is the sole writer; sre + admin
#     readers; backup-scheduler MUST NOT touch this bucket.
#   * Different KEY SCHEME: `events/<reality_id>/<YYYY>-<MM>.parquet` —
#     reality_id partitioning enables per-tenant restore + per-tenant cost
#     accounting in V3+.
#
# V1 ships as a STUB README pattern (same Q-L1C-1 reasoning as `lw-db-backups`):
# foundation V1 = docker-compose; IaC for prod V1+30d. The .tf body below is
# the prod topology and intentionally NOT applied yet — `terraform plan` would
# refuse because no provider is configured. See infra/minio/README.md.
#
# OBJECT-LOCK: NOT enabled in V1 (would block the restore-then-recompact
# escape hatch). V2+ may enable retention-mode = GOVERNANCE with bypass for
# sre role once the restore workflow is exercised at scale.
#
# VERSIONING: ENABLED — defense against an archive-worker bug that uploads
# a corrupted Parquet over a good one. The verify-after-upload check in
# pkg/archive_loop reads back the just-uploaded object and asserts the
# header / row-count footer; versioning is the second line of defense.

resource "minio_s3_bucket" "lw_event_archive" {
  bucket         = "lw-event-archive"
  acl            = "private"
  force_destroy  = false    # safety: refuse `terraform destroy` if non-empty

  versioning {
    enabled = true
  }

  # NO lifecycle_rule { expiration } — archive is FOREVER. The only legal
  # delete path is operator-driven via the restore-then-recompact runbook.
  # If a future regulatory ask requires per-tenant erasure (e.g. GDPR
  # right-to-be-forgotten), runbooks/archive/erase_for_reality.md covers
  # the manual fan-out delete by `events/<reality_id>/` key prefix.

  # Keep prior versions 30d so a same-key overwrite is recoverable.
  lifecycle_rule {
    id      = "keep-prior-versions"
    enabled = true
    noncurrent_version_expiration {
      days = 30
    }
  }
}

# Bucket policy: archive-worker full write; sre + admin read-only.
resource "minio_iam_policy" "lw_event_archive_writer" {
  name = "lw-event-archive-writer"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetObjectVersion",
        ]
        Resource = [
          "arn:aws:s3:::lw-event-archive",
          "arn:aws:s3:::lw-event-archive/*",
        ]
      },
      # Intentionally NO s3:DeleteObject — the archive-worker SVID can never
      # delete archived rows. Operator-driven delete uses the sre policy
      # via runbooks/archive/erase_for_reality.md.
    ]
  })
}

resource "minio_iam_policy" "lw_event_archive_reader" {
  name = "lw-event-archive-reader"
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
          "arn:aws:s3:::lw-event-archive",
          "arn:aws:s3:::lw-event-archive/*",
        ]
      },
    ]
  })
}
