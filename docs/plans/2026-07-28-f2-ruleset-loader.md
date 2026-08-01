# F2.1 — `ruleset-loader`: a reality's rules come from a FILE, and the bytes are what the digest addresses

> **Size:** L. **Spec:** [16 §3–§6, §11–§12](../03_planning/LLM_MMO_RPG/16_ruleset_loader_and_registry.md)
> (RLS-A3/A4/A5/A7/A8/A9/A10/A11, RLS-D2/D3/D12/D18) · [26 §6 F2](../03_planning/LLM_MMO_RPG/26_implementation_architecture.md).
> **Exit criterion (26 §6):** *a reality loads its ruleset from a file and the digest lands in a
> committed envelope.* (The second half already holds — `B` stamped it.)

---

## 1. What F2 is for, in one sentence

F1 made the digest real and `B` put it in the log. But **every reality on this engine still runs the
same rules**, because `Ruleset::engine_default()` is a `const fn` compiled into the binary. Two
consequences, both live today:

- there is no way to author a reality with different rules — the platform's entire premise;
- **the digest is a function of the BUILD.** A deploy that changes one constant silently changes the
  rules of every running reality, and the old ruleset exists nowhere to recover to.

F2 is what makes rules *content*.

---

## 2. Scope — and the parts of §3–§6 that would be consumer-less today

The spec describes a five-layer stack with a full merge algebra. Most of that algebra operates on
**collections** — `Vec<RaceDecl>`, `item_defs`, `ability_defs` — and `Ruleset` has none yet: F1
deliberately shipped only the two groups the laws actually read. So:

| Built now | Why it has a consumer |
|---|---|
| The **layer stack** (`engine_default` → `preset` → `book` → `reality` → `forge_override`) with priority order | scalar override is meaningful the moment a second layer exists |
| **`ReplaceWhole` / scalar override** | the only strategy the current field set can exercise |
| **Normalization** to fixed-point (RLS-A7/A8) | the file format admits decimals; the digest must be over the normalized form |
| **Load-time validation** (RLS-A10) | seven refusals are *already owed* — four `TODO(F2)`s in the laws plus DF7-V1's three |
| The **`engine_default` artifact** (RLS-D2) | turns *"the engine default is X"* from prose into an assertion |
| The **immutable store** | RLS-D18 + F3 + `Island::restore` all need to resolve a ruleset BY digest |
| The canonical **decoder** | without it the store can write bytes it cannot read back |

| Deferred, with the reason | |
|---|---|
| Tombstones (RLS-A5), `UnionById*` (RLS-A4) | **no collections in `Ruleset` to merge** — building them now is a mechanism with no consumer, the `Manifest` mistake again |
| Presets as a 3-tier scoped DB resource (RLS-D19) | needs a table + tenancy, and there is nothing to preset yet |
| The `(RealityId, Epoch)` registry + interning (RLS-A11) | needs multi-reality hosting; the island manager is not wired for it |
| `forge_override` as an ordered event (§9) | needs epoch-switch-as-ingress, which needs sim-core S-tier |
| Topological field order (RLS-A9) | no cross-field references exist yet |

---

## 3. IMP-Q1 — the file format, RESOLVED: **TOML**

Doc 26 leaves this open and says to weight **reviewability of a diff** over authoring comfort.

| | Verdict |
|---|---|
| **YAML** | What the prior project *"drowned in"*. Its scalar coercion is a determinism hazard in an artifact whose whole job is to be hashed: `no` → boolean, sexagesimals, `1.0` vs `1`. A ruleset that means something different depending on the parser version is exactly RLS-D5's *fails loudly and wrongly*. |
| **JSON** | **No comments.** A rules file's most valuable content is *why this number* — that has been the whole argument of F1. A format that cannot hold the reason will lose it. |
| **RON** | Rust-native and precise; unreadable to anyone who does not already write Rust, and rulesets are meant to be authored by non-engineers. |
| **TOML** ⭐ | Comments; unambiguous scalars; no significant whitespace; **line-oriented diffs** (the stated criterion); already a pinned workspace dependency. |

> **IMP-D10 — the ruleset artifact is TOML.** Its weakness is deep nesting, which is a real cost the
> day `Ruleset` grows collections — and a cheaper one to pay than any of the three failure modes above.

---

## 4. Layers are PARTIAL; the resolved ruleset is TOTAL

A layer file declares only what it overrides:

```toml
# reality layer
[combat]
max_hit = 250_000        # this reality is grittier
```

So the layer type is `RulesetPatch` — every field `Option<T>` — and resolution folds patches over
`Ruleset::engine_default()` in priority order. Two properties fall out and both are tested:

- **fold order is the priority order**, so a later layer wins and a fold of *no* layers is exactly the
  engine default;
- **an empty patch is an identity**, so `digest(resolve([])) == digest(engine_default())` — which is
  what makes the artifact in §5 verifiable against the code.

`RulesetPatch` gets the same **exhaustive-destructuring** treatment as `canon`: adding a field to
`CombatRules` without teaching the patch about it is a compile error, not a silently unoverridable
field.

---

## 5. `engine_default.toml` — RLS-D2's *"an artifact, not prose"*

Today every feature doc states its own defaults, which makes *"omit → default"* unverifiable. The
artifact ships next to the loader, and a test asserts it resolves **exactly** to
`Ruleset::engine_default()` — same digest. The `const fn` stays as the bootstrap floor (a node must
be able to run with no filesystem), but the two can no longer disagree silently.

---

## 6. The store — content-addressed, self-verifying, never pruned

```
put(&Ruleset) -> RulesetDigest     writes canon_bytes to <root>/<digest>.canon; idempotent
get(digest)   -> Option<Ruleset>   reads, RE-DIGESTS what it read, refuses on mismatch
```

**It re-digests on read** rather than trusting the filename. A store addressed by content that does
not check the content is a store that will happily hand back a corrupted or swapped ruleset under the
right name — and the digest exists precisely so that class of substitution is detectable. Append-only,
never GC'd while any event references a digest (RLS-D6).

This is what `Island::restore`'s refusal and F3's replay check both need: a way to resolve the
*historical* rules from a digest, instead of being handed whatever the current binary compiled in.

## 7. The decoder, and why it is the risky half

`canon_bytes` is write-only today. The store must read back, so `from_canon_bytes` has to mirror the
encoder's field order and widths exactly — a mirror hazard inside one language.

The mechanism is a **round-trip property test over randomised rulesets**: encode → decode → compare,
plus digest equality. Any asymmetry surfaces on the first field that disagrees. The decoder also
**refuses trailing bytes** and an unknown `schema_version`, so a truncated or future artifact fails
loudly rather than decoding into something plausible.

---

## 8. Validation — the seven refusals already owed

Load-time, per RLS-A10 (blast radius: the reality is **Unloadable**, never the process — RLS-D12).

| Refusal | Owed by |
|---|---|
| `hit_floor_pm > hit_ceiling_pm` | `TODO(F2)` in `hit_chance_pm` |
| `roll_band_hi_pm < roll_band_lo_pm` | `TODO(F2)` in `roll_band_width` |
| `defend_divisor < 1` | `TODO(F2)` in the damage chain |
| empty clamp intersection | `TODO(F2)` in `intersect_clamps` — **deferred**: clamps are per-actor content, not ruleset fields yet |
| `move_max < 1`, `move_speed_per_tile < 1`, `move_base > move_max` | **DF7-V1**, already specified → `stat.tuning_invalid` |

Each runtime fallback stays where it is. They exist so a bad ruleset **degrades predictably**; the
loader is what stops one being *stored* in the first place. Belt and braces on purpose: the runtime
floor also covers rulesets written before the validator existed.

---

## 9. Verification plan

| # | Check | Bites when |
|---|---|---|
| V1 | `engine_default.toml` resolves to the same digest as `Ruleset::engine_default()` | the artifact and the code disagree |
| V2 | round-trip: `from_canon_bytes(canon_bytes(r)) == r` over randomised rulesets | encoder/decoder asymmetry |
| V3 | decoder refuses trailing bytes, a bad tag, an unknown schema version | a truncated artifact decodes into something plausible |
| V4 | store `get` after `put` returns the same ruleset; a **tampered file** is REFUSED | the store trusts the filename over the content |
| V5 | layer fold: later layer wins; empty fold == engine default; two layers compose | priority order is wrong |
| V6 | each of the 6 validations refuses its bad ruleset, and a good one passes | a validator is vacuous |
| V7 | commit-service loads a real file and its islands carry that file's digest | the wiring is decorative |
| V8 | a malformed file makes ONE reality unloadable, not a process failure (RLS-D12) | failure blast radius |
