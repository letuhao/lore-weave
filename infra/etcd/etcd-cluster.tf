# infra/etcd/etcd-cluster.tf
#
# L1.E.5 — Self-hosted etcd cluster (Patroni DCS)
# Cycle 1 of foundation-mega-task.
#
# Per OPEN_QUESTIONS_LOCKED.md Q-L1E-2:
#   etcd self-hosted on dedicated EC2/EKS — NOT managed etcd / AWS
#   Rationale: vendor lock avoidance + Patroni upstream docs match
#
# Per parent layer plan L1.E.5: 3-node etcd cluster (Raft quorum = 2/3).
#
# V1 staging: 3 t3.small (etcd is light); V2+ scales to t3.medium per L1.L.

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

variable "etcd_node_count" {
  description = "Number of etcd nodes. MUST be odd (Raft quorum). V1 = 3."
  type        = number
  default     = 3
  validation {
    condition     = var.etcd_node_count % 2 == 1 && var.etcd_node_count >= 3
    error_message = "etcd_node_count must be odd and >= 3 for Raft quorum."
  }
}

variable "etcd_instance_type" {
  description = "EC2 instance type. etcd is light — t3.small in V1 staging."
  type        = string
  default     = "t3.small"
}

variable "etcd_data_volume_gb" {
  description = "EBS gp3 volume for etcd data dir. 20 GB sufficient (lease/lock metadata)."
  type        = number
  default     = 20
}

variable "etcd_client_port" {
  description = "etcd client port (Patroni connects here)."
  type        = number
  default     = 2379
}

variable "etcd_peer_port" {
  description = "etcd peer port (Raft replication)."
  type        = number
  default     = 2380
}

# ─── Locals ───────────────────────────────────────────────────────────────────
locals {
  cluster_name = "lw-patroni-etcd"
  common_tags = {
    Project     = "loreweave"
    Cluster     = local.cluster_name
    Role        = "etcd"
    Environment = var.environment
    ManagedBy   = "terraform"
    Cycle       = "raid-c1-l1e"
    Purpose     = "patroni-dcs"
  }
}

# ─── etcd EC2 nodes ───────────────────────────────────────────────────────────
resource "aws_instance" "etcd" {
  count = var.environment == "prod" ? var.etcd_node_count : 0

  instance_type = var.etcd_instance_type
  # ami, subnet_id (spread across AZs), vpc_security_group_ids resolved by
  # network module (V1+30d)

  ebs_block_device {
    device_name = "/dev/sdf"
    volume_type = "gp3"
    volume_size = var.etcd_data_volume_gb
    iops        = 3000
    throughput  = 125
    encrypted   = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-${count.index}"
  })

  lifecycle {
    ignore_changes = [ami]
  }
}

# ─── Outputs ──────────────────────────────────────────────────────────────────
output "etcd_endpoints" {
  description = "etcd client endpoints for Patroni configuration."
  value       = [for inst in aws_instance.etcd : "${inst.private_dns}:${var.etcd_client_port}"]
}

output "etcd_quorum_size" {
  description = "Raft quorum size (majority needed for write)."
  value       = floor(var.etcd_node_count / 2) + 1
}
