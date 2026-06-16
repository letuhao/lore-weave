# infra/statuspage/main.tf — L7.L.1 (RAID cycle 37)
#
# Declarative Statuspage.io page + components. Q-L7L-1 LOCKED: Statuspage.io
# V1. This is `terraform validate`-clean and applied OUT-OF-BAND by an
# operator with the live account; CI does NOT need credentials (the
# statuspage-updater abstracts the provider behind an interface so tests run
# without a live page).
#
# NOTE: provider credentials are env-var indirected (TF_VAR_statuspage_api_key,
# TF_VAR_statuspage_page_id). NEVER commit a Statuspage.io API key. The cycle
# verify step blocks credential-shaped strings.
#
# The component list MUST stay in sync with infra/statuspage/components.yaml
# (the updater + this Terraform both treat components.yaml as the source of
# truth). verify-cycle-37.sh asserts every component id in components.yaml has
# a matching statuspage_component resource here.

terraform {
  required_version = ">= 1.6"
  required_providers {
    statuspage = {
      source  = "yannh/statuspage"
      version = "~> 0.3"
    }
  }
}

variable "statuspage_api_key" {
  description = "Statuspage.io API key (set via STATUSPAGE_API_KEY env → TF_VAR_statuspage_api_key)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "statuspage_page_id" {
  description = "Statuspage.io page id (set via STATUSPAGE_PAGE_ID env → TF_VAR_statuspage_page_id)"
  type        = string
  default     = ""
}

provider "statuspage" {
  # token = var.statuspage_api_key   # set via STATUSPAGE_API_KEY env-var
}

# ────────────────────────────────────────────────────────────────────
# Components — one per service-catalog entry (kept in sync with
# components.yaml). Each maps to a user-visible status row.
# ────────────────────────────────────────────────────────────────────
resource "statuspage_component" "gateway" {
  page_id     = var.statuspage_page_id
  name        = "API Gateway"
  description = "External traffic entry point"
}

resource "statuspage_component" "auth" {
  page_id     = var.statuspage_page_id
  name        = "Authentication"
  description = "Login + identity"
}

resource "statuspage_component" "world" {
  page_id     = var.statuspage_page_id
  name        = "World"
  description = "World / zone state"
}

resource "statuspage_component" "roleplay" {
  page_id     = var.statuspage_page_id
  name        = "Roleplay"
  description = "Chat / turn engine"
}

resource "statuspage_component" "realtime" {
  page_id     = var.statuspage_page_id
  name        = "Realtime"
  description = "WebSocket / live updates"
}

output "managed_components" {
  description = "Component resource names managed by this config."
  value = [
    statuspage_component.gateway.name,
    statuspage_component.auth.name,
    statuspage_component.world.name,
    statuspage_component.roleplay.name,
    statuspage_component.realtime.name,
  ]
}
