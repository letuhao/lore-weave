# infra/terraform/meta-postgres/async_replica.tf
#
# L1.E.3 — Meta Postgres ASYNCHRONOUS replica (read scaling)
# Cycle 1 of foundation-mega-task.
#
# Per parent layer plan (L1C_to_L_infrastructure.md §3 L1.E.3):
#   - 1 async replica for reads (V1)
#   - Used by `contracts/meta/read_audit.go` (L1.B) for hot-path sensitive
#     reads when full sync visibility is not required
#
# Async replica is NOT in synchronous_standby_names → primary does NOT wait
# for it to fsync. Lag tolerance: ~5s typical, alert at >30s (L1.I).
#
# Per Q-L1F-1: a separate Redis cache layer absorbs cache-hit traffic; this
# replica handles cache-miss reads + replication targets for L1.I Prometheus
# scrape.

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

variable "async_replica_count" {
  description = "Number of async replicas. V1 = 1; V2+ scales per L1.L capacity gates."
  type        = number
  default     = 1
}

variable "async_replica_instance_type" {
  description = "EC2 instance type. Async can run on smaller class than primary."
  type        = string
  default     = "m6i.large"
}

variable "async_replica_storage_gb" {
  description = "EBS gp3 volume size. Match primary for safe failover-as-primary in DR."
  type        = number
  default     = 200
}

variable "max_replication_lag_seconds" {
  description = "Alert threshold for replication lag (L1.I alerts/per-reality.yaml hook)."
  type        = number
  default     = 30
}

# ─── Locals ───────────────────────────────────────────────────────────────────
locals {
  cluster_name = "lw-meta-pg"
  role         = "async-replica"
  common_tags = {
    Project       = "loreweave"
    Cluster       = local.cluster_name
    Role          = local.role
    Environment   = var.environment
    ManagedBy     = "terraform"
    Cycle         = "raid-c1-l1e"
    MaxLagSeconds = var.max_replication_lag_seconds
  }
}

# ─── Async replica EC2 instances ──────────────────────────────────────────────
resource "aws_instance" "async_replica" {
  count = var.environment == "prod" ? var.async_replica_count : 0

  instance_type = var.async_replica_instance_type
  # ami, subnet_id, vpc_security_group_ids resolved by network module (V1+30d)

  ebs_block_device {
    device_name = "/dev/sdf"
    volume_type = "gp3"
    volume_size = var.async_replica_storage_gb
    iops        = 3000
    throughput  = 125
    encrypted   = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-${local.role}-${count.index}"
  })

  lifecycle {
    ignore_changes = [ami]
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "async_replica_ids" {
  description = "Instance IDs of async replicas (empty in staging V1)."
  value       = [for inst in aws_instance.async_replica : inst.id]
}

output "async_replica_lag_alert_threshold_seconds" {
  description = "Lag alert threshold consumed by L1.I per-reality alert config."
  value       = var.max_replication_lag_seconds
}
