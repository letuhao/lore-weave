// Package admin declares the contracts/admin/registry/*.yaml schema as a
// machine-readable surface (loaded by services/admin-cli/internal/framework).
//
// LOCKED Q-IDs honored (RAID cycle 36):
//   - Q-L7A-1: per-domain split YAML files (reality.yaml, erasure.yaml, …).
//   - Q-L7A-2: single binary distribution (`admin <domain> <verb>`).
//
// This package is intentionally minimal — it exists only so contracts/admin/
// is a Go-loadable path and so the registry directory is checked into the
// build tree even when no Go consumer imports it yet.
package admin
