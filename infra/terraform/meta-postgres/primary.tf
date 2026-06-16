# infra/terraform/meta-postgres/primary.tf
#
# L1.E.1 — Meta Postgres PRIMARY (sync replication owner)
# Cycle 1 of foundation-mega-task.
#
# Per OPEN_QUESTIONS_LOCKED.md:
#   Q-L1E-1 — cross-region DR deferred to V3+ (NO multi-region resources in V1)
#   Q-L1E-2 — etcd self-hosted on dedicated EC2/EKS (no managed etcd)
#   Q-L1C-1 — V1 = docker-compose single shard; IaC (this file) prod target = V1+30d
#
# Per parent layer plan (docs/plans/2026-05-29-foundation-mega-task/L1C_to_L_infrastructure.md §3):
#   - synchronous_commit=on with synchronous_standby_names='ANY 1 (sync_replica_a)'
#   - WAL archive ship 60s cadence to MinIO bucket `lw-meta-wal-archive`
#   - PITR retention 30 days
#   - Failover RTO target: 30s (via Patroni — see ../patroni/patroni.yml)
#
# V1 STATUS: this file is the staging-target sketch. Foundation-dev uses
# infra/docker-compose.meta-ha.yml (see Q-L1B-5). Prod-apply gate ships V1+30d
# per Q-L1C-1.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────
variable "environment" {
  description = "Deployment environment (staging | prod). V1 staging only."
  type        = string
  default     = "staging"
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be one of: staging, prod."
  }
}

variable "primary_instance_type" {
  description = "EC2 instance type for the meta-postgres primary."
  type        = string
  default     = "m6i.large" # V1 staging baseline; V2+ scaling per L1.L progression
}

variable "primary_storage_gb" {
  description = "EBS gp3 volume size for primary data volume."
  type        = number
  default     = 200
}

variable "wal_archive_bucket" {
  description = "MinIO/S3 bucket name receiving 60s-cadence WAL ship (see L1.E.7)."
  type        = string
  default     = "lw-meta-wal-archive"
}

variable "patroni_etcd_endpoints" {
  description = "etcd cluster endpoints (see L1.E.5)."
  type        = list(string)
  default     = []
}

# ─── Locals ───────────────────────────────────────────────────────────────────
locals {
  cluster_name = "lw-meta-pg"
  role         = "primary"
  common_tags = {
    Project     = "loreweave"
    Cluster     = local.cluster_name
    Role        = local.role
    Environment = var.environment
    ManagedBy   = "terraform"
    Cycle       = "raid-c1-l1e"
  }
}

# ─── Primary EC2 instance ─────────────────────────────────────────────────────
# NOTE: AMI + subnet + SG come from a shared `network` module that V1+30d
# will introduce. For now we declare the resource skeleton so future
# `terraform plan` works once those modules ship.
resource "aws_instance" "primary" {
  count = var.environment == "prod" ? 1 : 0 # staging V1 uses docker-compose

  instance_type = var.primary_instance_type
  # ami, subnet_id, vpc_security_group_ids resolved by network module (V1+30d)

  ebs_block_device {
    device_name = "/dev/sdf"
    volume_type = "gp3"
    volume_size = var.primary_storage_gb
    iops        = 3000
    throughput  = 125
    encrypted   = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-${local.role}"
  })

  lifecycle {
    # Patroni performs failover; replace-on-AMI-change is unsafe for stateful node
    ignore_changes = [ami]
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "primary_id" {
  description = "Instance ID of the primary (empty in staging V1)."
  value       = try(aws_instance.primary[0].id, "")
}

output "wal_archive_bucket_name" {
  description = "Bucket name for WAL ship target."
  value       = var.wal_archive_bucket
}
