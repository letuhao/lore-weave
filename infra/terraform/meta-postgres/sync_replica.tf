# infra/terraform/meta-postgres/sync_replica.tf
#
# L1.E.2 — Meta Postgres SYNCHRONOUS replica
# Cycle 1 of foundation-mega-task.
#
# Per parent layer plan (L1C_to_L_infrastructure.md §3 L1.E.2):
#   - 1 sync replica at V1/V2 (this resource)
#   - 2 sync replicas at V3+ (count adjusted via capacity progression L1.L)
#
# The sync replica is the durability counterparty for `synchronous_commit=on`
# in infra/postgres/postgresql.conf (`synchronous_standby_names='ANY 1
# (sync_replica_a)'`). Meta writes block until this node fsyncs the WAL → zero
# data loss on primary failover.
#
# Per Q-L1E-1: cross-region DR is V3+. This sync replica is same-AZ-or-adjacent
# in V1; cross-region replication ships later.

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

variable "sync_replica_count" {
  description = "Number of sync replicas. V1/V2 = 1; V3+ = 2 (per L1.E.2 + Q-L1E-1)."
  type        = number
  default     = 1
  validation {
    condition     = var.sync_replica_count >= 1 && var.sync_replica_count <= 2
    error_message = "sync_replica_count must be 1 (V1/V2) or 2 (V3+)."
  }
}

variable "sync_replica_instance_type" {
  description = "EC2 instance type. Matches primary for failover symmetry."
  type        = string
  default     = "m6i.large"
}

variable "sync_replica_storage_gb" {
  description = "EBS gp3 volume size. MUST equal primary for failover-as-primary."
  type        = number
  default     = 200
}

# ─── Locals ───────────────────────────────────────────────────────────────────
locals {
  cluster_name = "lw-meta-pg"
  role         = "sync-replica"
  # Postgres synchronous_standby_names entries — names referenced by primary
  standby_names = [for i in range(var.sync_replica_count) : "sync_replica_${["a", "b"][i]}"]
  common_tags = {
    Project     = "loreweave"
    Cluster     = local.cluster_name
    Role        = local.role
    Environment = var.environment
    ManagedBy   = "terraform"
    Cycle       = "raid-c1-l1e"
  }
}

# ─── Sync replica EC2 instances ───────────────────────────────────────────────
resource "aws_instance" "sync_replica" {
  count = var.environment == "prod" ? var.sync_replica_count : 0

  instance_type = var.sync_replica_instance_type
  # ami, subnet_id, vpc_security_group_ids resolved by network module (V1+30d)

  ebs_block_device {
    device_name = "/dev/sdf"
    volume_type = "gp3"
    volume_size = var.sync_replica_storage_gb
    iops        = 3000
    throughput  = 125
    encrypted   = true
  }

  tags = merge(local.common_tags, {
    Name           = "${local.cluster_name}-${local.role}-${["a", "b"][count.index]}"
    PatroniStandby = local.standby_names[count.index]
  })

  lifecycle {
    ignore_changes = [ami]
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "sync_replica_ids" {
  description = "Instance IDs of the sync replicas (empty in staging V1)."
  value       = [for inst in aws_instance.sync_replica : inst.id]
}

output "standby_names" {
  description = "Patroni standby names matching synchronous_standby_names in postgresql.conf."
  value       = local.standby_names
}
