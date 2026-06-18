// Package alerts is the canonical foundation alert taxonomy + envelope
// SDK (cycle 22 / L4.P). It formalizes:
//
//   - The 4-severity ladder (page | warn | info | silence) per SR09 §12AL.
//   - The 4-action-class enumeration (pagerduty | slack | email | log_only)
//     mirroring the SR2 alert routing table.
//   - The wire envelope (versioned, correlation-id-bearing) every
//     alertmanager-fed pipeline emits + every receiver consumes.
//   - The AlertEmitter helper services use at runtime to fire an alert
//     locally (typically into the alertmanager push API or the
//     cycle-7 infra/prometheus/alerts/ rules).
//
// Stable shape NOW so cycle-7's Prometheus alert files (infra/prometheus/
// alerts/*.yaml) can reference the envelope schema by version when the
// cycle-23+ services start auto-generating alert rules from typed Go
// constants instead of hand-maintained YAML.
//
// Q-L4-5: this OpenAPI surface is internal documentation only.
package alerts
