# infra/k8s — L1.L K8s manifests

LOCKED Q-L1L-1 2026-05-29: K8s per CLAUDE.md infra hosting model (AWS EKS).

## Structure

- `hpa/` — HorizontalPodAutoscaler manifests (web + llm-gateway classes; HPA scales on CPU / req/s / queue depth)
- `keda/` — KEDA ScaledObject manifests (worker class; queue-lag triggers)

## Generated from contracts/capacity/budgets.yaml

The manifests in this directory are intentionally hand-written templates that
mirror `contracts/capacity/budgets.yaml` per-service `v1` block. A future cycle
(L7 ops) will ship a generator that derives manifests from budgets.yaml so
drift is impossible.

For cycle 7, we ship the manifests for the THREE foundation services that
already have running code (world-service, migration-orchestrator,
backup-scheduler) + the gateway. Other services get stub manifests as their
service skeletons land in later cycles.

## Apply locally (kind/minikube)

```bash
kubectl apply -f infra/k8s/hpa/
kubectl apply -f infra/k8s/keda/
```

## Validation

```bash
# dry-run validates schema against the K8s API
kubectl apply --dry-run=client -f infra/k8s/hpa/
kubectl apply --dry-run=client -f infra/k8s/keda/
```

The cycle-7 verify script runs this dry-run if `kubectl` is present; otherwise
it logs a WARN and skips (CI runners will have it).
