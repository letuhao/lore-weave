# infra/pagerduty/main.tf — L7.C.1 (RAID cycle 35)
#
# Terraform skeleton for the 5 PagerDuty services + escalation policies +
# rotation schedules. V1 manual `terraform apply` per environment; outputs
# emit the 5 integration keys for env-var provisioning into alertmanager +
# slack-bot + incident-bot deployments.
#
# Q-L7C-1 LOCKED: PagerDuty V1.
# Q-L7C-2 LOCKED: Internal SLA only (docs/governance/oncall-sla.md).
#
# NOTE: provider credentials are loaded via env-vars + the founder's Okta
# session. NEVER commit a PagerDuty API token to this repo. The cycle-35
# verify step (secret-scan-cycle.sh) blocks 32-hex strings.

terraform {
  required_version = ">= 1.6"
  required_providers {
    pagerduty = {
      source  = "PagerDuty/pagerduty"
      version = "~> 3.0"
    }
  }
}

provider "pagerduty" {
  # token = var.pagerduty_api_token   # set via PAGERDUTY_TOKEN env-var
}

# ────────────────────────────────────────────────────────────────────
# Variables
# ────────────────────────────────────────────────────────────────────
variable "founder_user_id" {
  description = "PagerDuty user id for the founder (created manually in UI on first apply)"
  type        = string
  default     = ""
}

variable "tech_lead_user_id" {
  description = "PagerDuty user id for tech-lead (placeholder V1 — uses founder)"
  type        = string
  default     = ""
}

variable "dpo_user_id" {
  description = "PagerDuty user id for DPO contact (Q-L7C-2 GDPR escalation)"
  type        = string
  default     = ""
}

# ────────────────────────────────────────────────────────────────────
# V1 — solo-dev schedule (founder 24/7)
# ────────────────────────────────────────────────────────────────────
resource "pagerduty_schedule" "solo_dev_247" {
  name      = "Solo-dev 24/7 (V1)"
  time_zone = "Asia/Bangkok"

  layer {
    name                         = "primary"
    start                        = "2026-06-01T00:00:00+07:00"
    rotation_virtual_start       = "2026-06-01T00:00:00+07:00"
    rotation_turn_length_seconds = 604800   # 7 days
    users                        = [var.founder_user_id]
  }

  # V1 solo-dev — Q-L7C-1 explicit
  description = "Per Q-L7C-1 + rotation_schedule.yaml phase=v1"
}

# ────────────────────────────────────────────────────────────────────
# Escalation policies (5 — one per service)
# ────────────────────────────────────────────────────────────────────
resource "pagerduty_escalation_policy" "sev0_immediate" {
  name      = "SEV0 — immediate page (5 min TTA)"
  num_loops = 2

  rule {
    escalation_delay_in_minutes = 0
    target {
      type = "schedule_reference"
      id   = pagerduty_schedule.solo_dev_247.id
    }
  }

  rule {
    escalation_delay_in_minutes = 5
    target {
      type = "user_reference"
      id   = var.tech_lead_user_id
    }
  }

  rule {
    escalation_delay_in_minutes = 15
    target {
      type = "user_reference"
      id   = var.founder_user_id
    }
  }

  description = "SLO breach / data integrity / security incident. Per oncall-sla.md SEV0 TTA=5min."
}

resource "pagerduty_escalation_policy" "sev1_15min" {
  name      = "SEV1 — 15 min TTA"
  num_loops = 1

  rule {
    escalation_delay_in_minutes = 0
    target {
      type = "schedule_reference"
      id   = pagerduty_schedule.solo_dev_247.id
    }
  }

  rule {
    escalation_delay_in_minutes = 15
    target {
      type = "user_reference"
      id   = var.tech_lead_user_id
    }
  }

  rule {
    escalation_delay_in_minutes = 30
    target {
      type = "user_reference"
      id   = var.founder_user_id
    }
  }

  description = "Feature freeze, partial outage. Per oncall-sla.md SEV1 TTA=15min."
}

resource "pagerduty_escalation_policy" "sre_primary" {
  name      = "SRE primary rotation (default — 30 min TTA)"
  num_loops = 1

  rule {
    escalation_delay_in_minutes = 0
    target {
      type = "schedule_reference"
      id   = pagerduty_schedule.solo_dev_247.id
    }
  }

  rule {
    escalation_delay_in_minutes = 30
    target {
      type = "user_reference"
      id   = var.tech_lead_user_id
    }
  }

  rule {
    escalation_delay_in_minutes = 60
    target {
      type = "user_reference"
      id   = var.founder_user_id
    }
  }

  description = "Default SR2 routing. Per oncall-sla.md SEV2 TTA=30min."
}

resource "pagerduty_escalation_policy" "security_oncall" {
  name      = "Security on-call (5 min TTA)"
  num_loops = 2

  rule {
    escalation_delay_in_minutes = 0
    target {
      type = "schedule_reference"
      id   = pagerduty_schedule.solo_dev_247.id
    }
  }

  rule {
    escalation_delay_in_minutes = 5
    target {
      type = "user_reference"
      id   = var.tech_lead_user_id
    }
  }

  rule {
    escalation_delay_in_minutes = 15
    target {
      type = "user_reference"
      id   = var.founder_user_id
    }
  }

  rule {
    escalation_delay_in_minutes = 30
    target {
      type = "user_reference"
      id   = var.dpo_user_id
    }
  }

  description = "auth + canon-injection + audit-hash + GDPR Art.33 72h timer chain."
}

resource "pagerduty_escalation_policy" "data_oncall" {
  name      = "Data on-call (5 min TTA — data integrity)"
  num_loops = 2

  rule {
    escalation_delay_in_minutes = 0
    target {
      type = "schedule_reference"
      id   = pagerduty_schedule.solo_dev_247.id
    }
  }

  rule {
    escalation_delay_in_minutes = 5
    target {
      type = "user_reference"
      id   = var.tech_lead_user_id
    }
  }

  rule {
    escalation_delay_in_minutes = 15
    target {
      type = "user_reference"
      id   = var.founder_user_id
    }
  }

  description = "meta-postgres + projection-runner + outbox. SEV0-equivalent timing."
}

# ────────────────────────────────────────────────────────────────────
# Services (5 — match alertmanager channels.yaml 1:1)
# ────────────────────────────────────────────────────────────────────
resource "pagerduty_service" "sev0" {
  name                    = "lw-sev0"
  description             = "SLO breach (budget exhausted) — wake everyone"
  auto_resolve_timeout    = "null"
  acknowledgement_timeout = "300"   # 5 min
  escalation_policy       = pagerduty_escalation_policy.sev0_immediate.id
  alert_creation          = "create_alerts_and_incidents"
}

resource "pagerduty_service" "sev1" {
  name                    = "lw-sev1"
  description             = "Feature freeze (>= 90% burn) — primary + secondary"
  auto_resolve_timeout    = "null"
  acknowledgement_timeout = "900"   # 15 min
  escalation_policy       = pagerduty_escalation_policy.sev1_15min.id
  alert_creation          = "create_alerts_and_incidents"
}

resource "pagerduty_service" "sre" {
  name                    = "lw-sre"
  description             = "SR2 default — meta + ws + service alerts"
  auto_resolve_timeout    = "86400"   # 24h auto-resolve safety net
  acknowledgement_timeout = "1800"    # 30 min
  escalation_policy       = pagerduty_escalation_policy.sre_primary.id
  alert_creation          = "create_alerts_and_incidents"
}

resource "pagerduty_service" "security" {
  name                    = "lw-security"
  description             = "auth + canon-injection + audit-hash-mismatch"
  auto_resolve_timeout    = "null"
  acknowledgement_timeout = "300"   # 5 min
  escalation_policy       = pagerduty_escalation_policy.security_oncall.id
  alert_creation          = "create_alerts_and_incidents"
}

resource "pagerduty_service" "data" {
  name                    = "lw-data"
  description             = "meta-postgres + projection-runner + outbox alerts"
  auto_resolve_timeout    = "null"
  acknowledgement_timeout = "300"   # 5 min
  escalation_policy       = pagerduty_escalation_policy.data_oncall.id
  alert_creation          = "create_alerts_and_incidents"
}

# ────────────────────────────────────────────────────────────────────
# Integration keys (one per service for alertmanager webhook integration)
# ────────────────────────────────────────────────────────────────────
resource "pagerduty_service_integration" "sev0_alertmanager" {
  name    = "alertmanager"
  service = pagerduty_service.sev0.id
  vendor  = "PXPSF"   # PagerDuty's Prometheus alertmanager vendor id
}

resource "pagerduty_service_integration" "sev1_alertmanager" {
  name    = "alertmanager"
  service = pagerduty_service.sev1.id
  vendor  = "PXPSF"
}

resource "pagerduty_service_integration" "sre_alertmanager" {
  name    = "alertmanager"
  service = pagerduty_service.sre.id
  vendor  = "PXPSF"
}

resource "pagerduty_service_integration" "security_alertmanager" {
  name    = "alertmanager"
  service = pagerduty_service.security.id
  vendor  = "PXPSF"
}

resource "pagerduty_service_integration" "data_alertmanager" {
  name    = "alertmanager"
  service = pagerduty_service.data.id
  vendor  = "PXPSF"
}

# ────────────────────────────────────────────────────────────────────
# Outputs — 5 integration keys (must go into env-vars, NOT git)
# ────────────────────────────────────────────────────────────────────
output "pagerduty_integration_key_sev0" {
  value     = pagerduty_service_integration.sev0_alertmanager.integration_key
  sensitive = true
}

output "pagerduty_integration_key_sev1" {
  value     = pagerduty_service_integration.sev1_alertmanager.integration_key
  sensitive = true
}

output "pagerduty_integration_key_sre" {
  value     = pagerduty_service_integration.sre_alertmanager.integration_key
  sensitive = true
}

output "pagerduty_integration_key_security" {
  value     = pagerduty_service_integration.security_alertmanager.integration_key
  sensitive = true
}

output "pagerduty_integration_key_data" {
  value     = pagerduty_service_integration.data_alertmanager.integration_key
  sensitive = true
}
