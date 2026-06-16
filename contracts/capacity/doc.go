// Package capacity — L4.I (RAID cycle 19) — formalizes the canonical
// schema, loader, and admission-control entry-points for the
// budgets.yaml file shipped in cycle 7.
//
// Scope (SR08 §12AK):
//
//   - budgets.yaml — per-service capacity budget (CPU + memory +
//     min/max replicas + scale trigger) for every microservice in the
//     monorepo. Cycle 7 shipped the file + the L1.K.7 lint that
//     ensures every service has an entry; THIS cycle (19) formalizes
//     the typed schema + loader + admission-on-deploy API.
//   - admission.go — RegisterService(name) check called by deploy
//     pipelines (HPA/KEDA manifest builders) to confirm an entry
//     exists before generating cluster manifests.
//   - Override audit hooks via the cycle-7 admin-cli capacity-override
//     command (L1.L.3) — referenced here only, not re-implemented.
//
// Companion lint: `scripts/capacity-budget-lint.sh` (L1.K.7, shipped
// cycle 7) remains the build-time gate. This package adds the RUNTIME
// gate + the typed Go/Rust loader.
//
// Q-L4-1 parity: Rust mirror lives in `crates/dp-kernel/src/capacity.rs`.
// Schema field names + enum wire strings are 1-for-1.
//
// Schema (current authoritative shape — version 1):
//
//	version: 1
//	services:
//	  - name: <service-name>
//	    class: web|llm-gateway|worker|cron|library
//	    v1:
//	      min_replicas: <int>
//	      max_replicas: <int>
//	      cpu_per_replica: <decimal>
//	      memory_per_replica: <suffix-string>      # 512Mi, 2Gi
//	      scale_trigger: <metric-expr-string>
//	    v3:
//	      min_replicas: <int>
//	      max_replicas: <int>
//	      # (v3 fields are sparse — min/max only; other fields inherit v1)
package capacity
