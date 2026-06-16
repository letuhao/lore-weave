# Foundation-staging Terraform skeleton — B5
# Per RAID_WORKFLOW.md §13.5
#
# Skeleton only; full IaC apply happens at C38 acceptance.
# Foundation staging = AWS account dedicated to foundation (separate from existing prod).
#
# C38 will:
#   - terraform init && terraform plan
#   - Cycle 38 (L7 deploy pipeline) applies this to staging AWS account
#   - E2E smoke runs in foundation-staging (NOT existing prod)
#
# Per PRE_FLIGHT D1: AWS staging account deferred to V1+30d.
# This file ships as PLACEHOLDER ready for that follow-up.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # backend config added at C38 (S3 + DynamoDB lock)
}

provider "aws" {
  region = var.aws_region
  # Profile / assume_role configured by operator at C38; do not hard-code.
}

variable "aws_region" {
  description = "AWS region for foundation-staging (NOT existing prod)"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment label — locked to staging for this skeleton"
  type        = string
  default     = "foundation-staging"
  validation {
    condition     = var.environment == "foundation-staging"
    error_message = "This skeleton is locked to foundation-staging; do NOT apply to prod."
  }
}

# Module skeletons (populated in C38)
# module "patroni_ha"       { source = "./modules/patroni" }      # C1 ports L1.E
# module "redis_sentinel"   { source = "./modules/redis-sentinel" }
# module "minio"            { source = "./modules/minio" }
# module "pgbouncer"        { source = "./modules/pgbouncer" }    # C5
# module "prometheus_thanos" { source = "./modules/observability" }  # C33

# Outputs added at C38
output "environment" {
  value = var.environment
}
