# Conflict resolution — a mechanism, not a policy choice

**Status:** PROPOSAL to the 2026-08-02 command round. **Deliberately unnumbered** —
allocating a decision id here is what produced the `CMD-D1`..`CMD-D7` collision. An
id is assigned when this is folded into that round.

---

## §1 · The question was posed as a binary and it is not one

The reconciliation left one conflict open: *merge-with-priority (Caves of Qud,
Evennia — shipped twice) or build-failure on collision (only available to us because
we pre-compose)?*

**Both, and neither is the design.** Merge is the *default*, failure is the
*fallback*, and what actually resolves conflict is a third thing that neither name
mentions: **a declared resolution**. Systems that solve this well all have the same
four parts, and picking one of the two policies is what you do when you have not
built them.

## §2 · What the 08-02 round already has, and the exact gap

The command dataflow's S1 is a layered fold, inherited from the actor round:

```
engine_default (0) → preset (10) → book (20) → reality (30) → forge_override (40)
```

**That resolves VERTICAL conflict** — a reality overrides a book, deterministically,
by declared precedence. It is sealed and this proposal does not touch it.

**It says nothing about HORIZONTAL conflict**: two bundles *at the same layer*. And
this is where the Skyrim comparison misleads, in a way worth naming — their load
order is a **total** order, every plugin gets a distinct index, so horizontal
conflict does not exist for them; every conflict is vertical by construction. Ours
has five layers and **N bundles per layer**. Horizontal conflict is real, reachable
today, and unaddressed.

The dataflow says S1 is *"folded by merge strategy"* and never defines what a merge
strategy is. That phrase is the hole.

## §3 · The four parts, taken from systems that ship this

### 3.1 A MATCH KEY — "are these the same thing?"

Nothing can merge until it can tell whether two declarations describe one thing.

- Kubernetes: `patchMergeKey` names the field that identifies a list element, *"so
  that elements can be matched irrespective of their array positions"*.
- Android: a unique attribute (`android:name`) or *"the natural uniqueness of the
  tag itself"*.

**Here:** a verb's `MachineKey`, a role's ordinal, a requirement's `(kind, subject,
ref)`. Every mergeable row needs a declared key, and rows with no key **cannot
merge — they can only append**.

### 3.2 The merge STRATEGY is declared in the SCHEMA, not by the authors

This is the part that makes the mechanism work, and it is the part a policy choice
misses. In Kubernetes the strategy is a **struct tag on the API type**, exposed as
an OpenAPI annotation — the *field* says how it merges, and **a list with no
strategy is replaced entirely**.

Neither bundle author negotiates. Neither needs to know the other exists. The schema
already answered.

Applied to `verb_declarations`:

| field | strategy | why |
|---|---|---|
| `key` | **identity** | it *is* the match key |
| `roles[]` | **merge by `role` ordinal** | two bundles may constrain different roles |
| `requires[]` | **append** | this is `CMD-D2`'s only correct instinct: a constraint added is a constraint, and additive here means nobody's guard silently vanishes |
| `costs[]` / `spend[]` | **append** | same |
| `effects[]` | **append, ORDER DECLARED** | the determinism lens found this: effects are not a set. Order must be pinned, not emergent — see §5 |
| `cue` | **exclusive** | one verb, one cue |
| `submitter_class` | **exclusive, narrowing only** | a bundle may restrict who submits, never widen it |
| resolution binding | **exclusive** | a verb has one implementation |

`exclusive` is where conflict becomes possible at all. Everything else composes.

### 3.3 An explicit RESOLUTION artifact

When two bundles set one `exclusive` field, something must say which wins — and
**that something is authored, not inferred from order.**

Android's markers are the clearest shipped form: `tools:node="merge"` ·
`tools:node="strict"` (build failure unless the lower-priority element matches
exactly) · `tools:node="remove"` · `tools:replace="attr"`, which *"targets
attributes, not elements"*. Cargo's `[patch]` and npm's `overrides` are the same
idea in a dependency resolver.

**Here it is a declared row naming both sides:**

```
conflict_resolutions [
  subject:  (verb_key, field)      // what is contested
  between:  [bundle_a, bundle_b]   // WHO — named, not implied by order
  verdict:  TakeA | TakeB | Value(…)
  reason:   ReasonOrdinal          // reuses CMD-5's refusal vocabulary
]
```

### 3.4 UNRESOLVED conflict fails the build, and the diagnostic names both sides

Android: conflicts *"appear under Merging Errors **with a recommendation for how to
resolve the conflict** using merge rule markers."* That recommendation is the whole
usability of the mechanism — a build failure that only says *"conflict"* trains
people to reach for the biggest hammer.

Ours can do this because we pre-compose. A ruleset build has a place to fail; a
launch does not.

## §4 · Why this is strictly better than the patch economy

Skyrim's ecosystem **invented** the compatibility patch because the system had no
place to put one. A patch there is a third plugin with **no declared relationship**
to the two it reconciles — nothing records what it patches, nothing notices when one
side changes, and nothing detects that it is now wrong.

A `conflict_resolutions` row names both sides, so it is **verifiable**:

- does each named bundle still exist in this ruleset?
- do both still set the contested field?
- if not, the resolution is **stale** and the build says so

That is the same shrink-from-both-ends rule `orphan-model-gate`'s registry already
uses — a resolution that has outlived its conflict is a finding, not a leftover. The
patch stops being folklore and becomes a checkable artifact **inside the digest**,
which also means replay is unaffected: the composed ruleset is pinned, and the
resolutions that produced it are part of what was pinned.

## §5 · What this fixes in `CMD-D2`, which was wrong twice

**`CMD-D2` said amendments may never remove.** That was over-correction. Removal
is not the danger — *silent* removal is. Android has `tools:node="remove"` and it is
safe because it is **written down and attributable**. With a resolution artifact,
removal becomes possible, named, and reviewable. Forbidding it just pushes authors
into declaring a near-duplicate verb, which is worse: now there are two.

**`CMD-D2` said "lists add" and stopped there.** The determinism lens found the hole:
addition is commutative, effect application is not. Bundle A writes `heat += 1`;
bundle B's precondition reads `ValueAtLeast(heat, 1)`. Whether B sees A's write is an
ordering question, and *"lists add"* does not answer it. So `effects[]` merges with a
**declared order**, and the resolution artifact is where a contested order is settled
— not the filesystem, not discovery order, not bundle name.

## §6 · What this does NOT decide

- **The strategy set itself** is engine-closed and this proposal names five members
  (`identity · merge-by-key · append · append-ordered · exclusive`). Whether that set
  is complete is exactly the `§27.1` question the 08-02 round applies to every other
  closed set, and it should be applied to this one before sealing.
- **Where resolutions are authored.** A resolution is content, so it lives in a
  bundle — but *whose*? A third reconciling bundle (Skyrim's patch, made
  first-class), or the reality layer that assembled the conflicting pair? The second
  is more likely right, because the reality is what chose to include both.
- **Whether `strict` is worth having.** Android's `tools:node="strict"` fails on any
  difference at all, which is a useful thing to be able to demand of a dependency.
  Unclear whether it earns a member of the closed set here.

---

**Sources:**
[Manage manifest files — Android Developers](https://developer.android.com/build/manage-manifests) ·
[Manifest Merging — Android](https://minimum-viable-product.github.io/marshmallow-docs/tools/building/manifest-merge.html) ·
[Strategic Merge Patch — kubernetes/community](https://github.com/kubernetes/community/blob/main/contributors/devel/sig-api-machinery/strategic-merge-patch.md) ·
[Strategic Merge Patch — kubernetes/apimachinery](https://deepwiki.com/kubernetes/apimachinery/6.1-strategic-merge-patch) ·
[Kustomize patches](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/patches)
