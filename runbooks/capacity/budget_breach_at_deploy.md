# Capacity budget breach at deploy — SRE runbook (L6.G.5)

> **LOCKED:** Q-L6G-1 (K8s admission webhook; ECS variant is V2+).
> **Owner:** SRE primary; service-team author is consulted.
> **Scope:** Pod/Deployment rejections from the `capacity.lw.foundation`
> ValidatingWebhookConfiguration shipped in cycle 30.

## 1. TL;DR

The capacity admission webhook rejects pod/deployment specs that
exceed `contracts/capacity/budgets.yaml` entries OR reference a
service missing from that file. The rejection appears in `kubectl`
output as:

```
Error from server: admission webhook "capacity.lw.foundation" denied the request:
  service=publisher tier=v1 replicas=6 max=4 (no active override)
```

To unblock a legitimate emergency deploy you have **three** options,
in priority order:

1. **Fix budgets.yaml + roll cycle 30+ verify-cycle script.**
   Preferred. PR a budgets.yaml bump → land on main → re-deploy.
2. **Grant a 24h capacity override** (`lw-admin-cli capacity override grant`).
   Use ONLY during incidents when budgets.yaml change cannot land in time.
3. **Bypass the webhook** (`kubectl annotate namespace <ns> lw.capacity-webhook=disabled`).
   Emergency-only; leaves cluster vulnerable to capacity blowouts.

## 2. Triage decision tree

```
deploy rejected
    ↓
read `kubectl describe` status.message
    ↓
┌────────────────────────────────────────────────────────────┐
│ reason=deny_no_budget                                       │
│  → service is not in budgets.yaml                           │
│  → ACTION: PR an entry (see §4); OR grant override if P0    │
├────────────────────────────────────────────────────────────┤
│ reason=deny_over_budget                                     │
│  → replicas > tier max                                      │
│  → ACTION:                                                  │
│      * If load is real → PR a budgets.yaml bump             │
│      * If load is a spike → grant 24h override + monitor    │
│      * If misconfig → fix the replicas/HPA + retry          │
├────────────────────────────────────────────────────────────┤
│ webhook unreachable (apiserver timeout / TLS error)         │
│  → ACTION: §5 webhook fault triage                          │
└────────────────────────────────────────────────────────────┘
```

## 3. Granting a 24h capacity override

Per S5 Tier 2: overrides auto-expire 24h after grant. The override
records who, when, and **why** in the audit trail.

```bash
lw-admin-cli capacity override grant \
  --service=publisher \
  --reason="incident-2024-1234 fanout investigation; budget bump PR open #4567" \
  --granted-by=$USER
# Output: {"id":"abc...","expires_at":"2026-05-30T12:00:00Z"}
```

**Reason field rules (`contracts/capacity/override_handler.go`):**
- Minimum 16 chars (enforced by `Validate()`).
- SHOULD reference an incident ID or open PR.
- Will appear in the post-incident audit pull.

**Override visibility:**
- Cached 60s by the webhook's `capacity.OverrideHandler` — granting an
  override does NOT immediately unblock the next deploy. Wait ≤60s OR
  delete the webhook pod to force cache refresh:
  ```bash
  kubectl -n lw-foundation rollout restart deploy/capacity-webhook
  ```

## 4. PRing a budgets.yaml bump

```
contracts/capacity/budgets.yaml
  - name: publisher
    class: worker
    v1:
      min_replicas: 1
      max_replicas: 4    # ← bump this
      cpu_per_replica: 0.5
      memory_per_replica: 512Mi
      scale_trigger: "outbox_lag>1000"
```

After landing:
- `bash scripts/capacity-budget-lint.sh` validates.
- `bash scripts/raid/verify-cycle-7.sh` confirms all 31 services
  still have entries (cycle-7 acceptance).
- ConfigMap `capacity-budgets` is re-applied by GitOps; webhook pod
  picks up the new file on next read (no restart needed).

## 5. Webhook fault triage

If the webhook itself is failing:

```bash
# Symptom check
kubectl get validatingwebhookconfiguration capacity.lw.foundation -o yaml | grep -A 2 failurePolicy
# failurePolicy: Fail   ← correct posture: cluster blocks deploys

# Webhook pod health
kubectl -n lw-foundation get pods -l app.kubernetes.io/name=capacity-webhook
kubectl -n lw-foundation logs deploy/capacity-webhook --tail=200

# TLS cert validity
kubectl -n lw-foundation get secret capacity-webhook-tls -o yaml | grep expir
```

If the webhook is hard-down:

1. **Last resort bypass:** annotate the target namespace.
   ```bash
   kubectl annotate namespace <target-ns> lw.capacity-webhook=disabled
   # Deploy your service.
   # Remove the annotation:
   kubectl annotate namespace <target-ns> lw.capacity-webhook-
   ```
   *(The cycle-30 ValidatingWebhookConfiguration ships WITHOUT a
   namespaceSelector for this annotation; to use this escape hatch
   you MUST edit the VWC to add the selector. SRE on-call only.)*
2. **Cluster-wide bypass:** delete the ValidatingWebhookConfiguration.
   ```bash
   kubectl delete validatingwebhookconfiguration capacity.lw.foundation
   ```
   ⚠️ Removes capacity protection cluster-wide. File a P0 incident
   and re-apply ASAP via GitOps.

## 6. Post-incident hygiene

- [ ] Every override granted during the incident is documented in
      the incident retrospective (who, when, reason, expiry).
- [ ] Each override either expired naturally (24h) OR was followed by
      a budgets.yaml PR. Standing overrides are a smell.
- [ ] `lw_capacity_admission_decisions_total{decision="allow_via_override"}`
      should be near zero between incidents — alert on > 0 for 1h.

## 7. Q-IDs honored

| Q-ID | Resolution | Where enforced |
|---|---|---|
| Q-L6G-1 | K8s ValidatingWebhookConfiguration (CLAUDE.md infra match); ECS variant V2+ | `infra/k8s/admission-webhook/deployment.yaml` |
| S5 Tier 2 | 24h override TTL (auto-expire) | `contracts/capacity/override_handler.go::overrideTTL` |

## 8. Implementation references

- Admission webhook code: `infra/k8s/admission-webhook/capacity_checker.go`
- Override contract:      `contracts/capacity/override_handler.go`
- Budgets source-of-truth: `contracts/capacity/budgets.yaml`
- Cycle-7 capacity lint:   `scripts/capacity-budget-lint.sh`
- Inventory metrics:        `lw_capacity_admission_decisions_total{decision}`
                            `lw_capacity_admission_latency_seconds`
