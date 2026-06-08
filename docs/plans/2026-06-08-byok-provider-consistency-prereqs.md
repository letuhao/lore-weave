# BYOK / provider-invariant consistency — prerequisites for Auto-Draft Factory

> **Status:** PLAN (PO-prioritized 2026-06-08). **Blocks:** Auto-Draft Factory feature (the wizard's "Model Matrix" requires every model role to be user-configurable BYOK).
> **Why now:** an audit of model roles for the Auto-Draft Factory (`docs/specs/…-auto-draft-factory.md`, TBD) found roles that deviate from the project's two invariants:
> - **Provider gateway invariant** — NO direct provider SDK calls; all AI through the adapter layer.
> - **No hardcoded model names** — model names resolved from provider-registry (the user's registered BYOK config).

The system pushes **all** LLM/model config to the user (BYOK via provider-registry). Any role that hardcodes a model or is operator-only is inconsistent and must be reconciled **before** the factory exposes a per-run model matrix.

---

## 🔴 BUG-1 (HIGH, fix FIRST — before the factory) — Reranker is not BYOK

**`D-RERANK-NOT-BYOK`**

The cross-encoder reranker (raw-search, E5B — shipped 2026-06-08 with the rawsearch feature) deviates from BYOK on three counts:

| Aspect | Every other role | Reranker |
|---|---|---|
| Model resolution | `(user_id, model_source, model_ref=UUID)` resolved from provider-registry | **hardcoded model NAME** from env `RERANK_MODEL` (default `bge-reranker-v2-m3`) |
| Dispatch | adapter-dispatched (OpenAI/Anthropic/Ollama/LM Studio/…) | **NOT adapter-dispatched** — single fixed Cohere-compatible shape |
| Provider | the user's registered provider | **platform service**, URL+token from config |

**Evidence:**
- `services/knowledge-service/app/clients/reranker_client.py:28,52,70-73` — passes `model=settings.rerank_model` (env string) to `/internal/rerank`.
- `services/knowledge-service/app/config.py:88` — `rerank_model` = env `RERANK_MODEL`, hardcoded default.
- `services/provider-registry-service/internal/provider/rerank.go:18-22` — comment admits *"NOT adapter-dispatched … platform service … not a per-user BYOK provider."*
- Gateway invariant itself is **OK** — the call does go through provider-registry; the violation is *hardcoded name + not adapter-dispatched + not per-user*.

**Counter-evidence that this is a shortcut, not a valid exception:** `embedding` — the same class of "simple, known-shape" model — was fully done as BYOK + adapter-dispatched. The "single known API shape" rationale therefore doesn't hold; rerank was simply not finished to BYOK parity when shipped fast for rawsearch.

**Fix — bring rerank to embedding parity:**
1. provider-registry: make Rerank **adapter-dispatched** + resolve `(user_id, model_source, model_ref)` like Embed (a rerank adapter per provider kind, or at least per-user URL+token+model from the registered credential).
2. knowledge-service: `reranker_client` passes a resolved `model_ref` (+ user) instead of the `RERANK_MODEL` env string; drop the env default.
3. FE: rerank becomes a normal entry in the model picker (no "platform" special-case).
4. Migration/back-compat: keep a platform fallback only if a user has no rerank provider registered (degrade-to-platform), but never a hardcoded name in the request path.

**Cross-service:** knowledge-service + provider-registry-service + frontend (model picker). Size ~M/L. **Do this as its own `/loom` before any Auto-Draft Factory build.**

---

## 🟡 GAP-2 (MED — fold into Auto-Draft Factory S2) — Eval judges are operator-only + single-owner-billed

**`D-EVAL-JUDGE-PER-USER`**

The eval/judge models are **correctly BYOK-resolved** (real provider-registry UUIDs — NOT the reranker bug), but are configurable **only at deployment ENV level**, never per-user or per-run, and bill a **single BYOK owner** for the whole deployment.

Affected roles (all OFF by default):
- **online translation fidelity judge** (M7d) — `learning-service/app/config.py:23-29` (`online_judge_model_ref` = "BYOK user_model UUID", `online_judge_user_id` = single owner, `online_translation_judge_enabled=False`).
- **online extraction quality judge** (Q4b) — same learning-service env block.
- **coref merge judge** — `knowledge-service/app/config.py:150-152` (`coref_judge_model` / `coref_judge_user` / source `platform_model`; off when unset).

**What's actually wrong (≠ hardcoded-name):**
1. **No per-user / per-run path** — a user can't choose their own eval model; only the operator can, via ENV.
2. **Single-owner billing (latent multi-tenant bug)** — when enabled, every user's eval-judge call bills the one `*_user_id`/`coref_judge_user`. In a multi-user BYOK product this mis-attributes cost. Currently latent only because the judges ship OFF.

**Fix (within Auto-Draft Factory S2 — per-run model plumbing):**
- Thread judge `model_ref` (+ owner) as a **per-campaign / per-job** param (mirror translation's `verifier_model_ref`), so the wizard's Model Matrix can set the eval model and it bills the campaign owner.
- Keep the ENV settings as the deployment default / off-switch.
- Also resolves the existing **`D-TRANSL-M7D-INLINE-JUDGE`** constraint context (the fidelity judge already needs out-of-band + governed execution before enabling).

---

## Priority ordering (PO 2026-06-08)

1. **BUG-1 reranker → BYOK** — standalone `/loom`, **before** the Auto-Draft Factory feature.
2. **Auto-Draft Factory** — and inside it, **GAP-2** is part of S2 (per-run model plumbing), so the Model Matrix is consistent for every role including eval judges.
3. (Carry) `D-TRANSL-M7D-INLINE-JUDGE` — out-of-band + cost-governed judge execution before turning the fidelity judge ON in production.
