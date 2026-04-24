# Read This First

> Orientation for every agent picking up a feature-design task in the LLM MMO RPG track.
> **Read this file, then read files 02..07 in this folder. Then go to your feature's target subfolder.**

---

## Why this folder exists

Loading all of `02_storage/` (36 chunks, 476 KB) and `03_multiverse/` (10 chunks, 56 KB) into every feature-design session is impossible and wasteful. The foundation folder distills everything downstream features MUST respect into 7 short files, ~30 KB total.

**Rule:** after reading `00_foundation/`, you MUST NOT need to re-read `02_storage/` or `03_multiverse/` unless your feature actually modifies storage or canon logic. Read only the specific chunk(s) your feature directly touches.

---

## Kernel vs features

```
                      LLM MMO RPG
                           |
              +------------+-------------+
              |                          |
           kernel                     features
              |                          |
      02_storage/                every other subfolder
      03_multiverse/             (and every new subfolder you
                                  create for a feature)
```

- **Kernel** = the authoritative source of storage, reality lifecycle, canon, security, SRE, deploy safety, PII. The kernel OWNS its contracts; nothing overrides them.
- **Features** = chat, roleplay, social, onboarding, quests, etc. Features CONSUME kernel contracts — they do NOT redefine, bypass, or relax them.

Foundation is a cheat sheet for the kernel. It's what lets you do feature work without memorizing 476 KB of storage design.

---

## The 7 foundation files

| # | File | One-line |
|---:|---|---|
| 1 | `01_READ_THIS_FIRST.md` (this file) | Orientation |
| 2 | `02_invariants.md` | 15 non-negotiable rules |
| 3 | `03_service_map.md` | 19 services with responsibilities + events in/out |
| 4 | `04_kernel_api.md` | Canonical functions you must call |
| 5 | `05_vocabulary.md` | Shared enums and concepts |
| 6 | `06_id_catalog.md` | Stable IDs + owning subfolder |
| 7 | `07_feature_workflow.md` | Step-by-step agent workflow |

---

## What NOT to do

- **Do not bypass an invariant.** If your feature appears to need a bypass, escalate — don't quietly route around it. Every invariant in `02_invariants.md` has a concrete enforcement point (CI lint, runtime check, code review gate). Bypasses fail those gates.
- **Do not invent status vocabulary, canon layers, lifecycle states, or gone-states.** Use `05_vocabulary.md`. New enums require foundation + kernel-chunk updates.
- **Do not renumber stable IDs.** Your feature gets NEW IDs in its own namespace (or extends an existing namespace's next free number). Retired IDs get `~~strikethrough~~`, not reuse.
- **Do not call LLM providers directly.** Go through the prompt library (`contracts/prompt/` per `04_kernel_api.md`).
- **Do not write to meta-registry tables directly.** Use `MetaWrite()` helper.
- **Do not cross reality-DB boundaries in a single query.** Use event-driven propagation (R5 anti-pattern; `contracts/events/xreality.*`).
- **Do not add a new inter-service RPC without a matching ACL entry.** Declare it in `contracts/service_acl/matrix.yaml` or CI fails.
- **Do not store sensitive data without a PII classification tag** (`@pii_sensitivity` / `@retention_class` / `@erasure_method` / `@legal_basis`). CI lint `scripts/pii-classify-lint.sh` enforces.

---

## When you think the kernel is wrong

If a feature you're designing can't be built without violating a kernel contract:

1. **Do not work around it.** A workaround becomes tech debt and an integration-blocker.
2. **Write the objection in a new row of SESSION_HANDOFF.md** with: feature, conflicting invariant, why the invariant seems wrong for this feature, proposed fix.
3. **Stop work on the feature** until the architect role resolves — either confirm the invariant (feature must adapt) or amend the kernel chunk + foundation (invariant was incomplete).

Bypassing is the failure mode this folder is designed to prevent. If you're tempted, stop and escalate.
