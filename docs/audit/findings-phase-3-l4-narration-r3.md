# Adversary findings — Phase 3 L4 regional-narration pipeline (round 3)

**Task:** phase-3-l4-narration · **Phase:** REVIEW (code) · **Branch:** `mmo-rpg/zone-map-amaw`
**Scope reviewed:** `l4_retry.rs`, `l4_validate.rs`, `l4_prompt.rs`, `keyphrase.rs`, `style.rs`, `bootstrap.rs`, `tests/l4_mock.rs`
**Build state:** `cargo test -p tilemap-service` green (6 L4 mock + 8 retry + 5 smoke + lib unit tests); `cargo clippy -p tilemap-service` clean.

The retry loop, `partition_l4_response`, the §6 fallback, and the duplicate/exactly-once
invariant were traced against the three ContextHub retry-loop holes and AC-1..AC-11.
No current correctness BLOCK was found — the loop is sound. Three WARN-level issues below.

---

## WARN 1 — `bootstrap.rs:102` derives `terrain` from `{:?}` Debug, not the canonical serde tag

`bootstrap.rs:102`: `terrain: format!("{:?}", z.terrain_type).to_lowercase(),`

`TerrainKind` (`src/types/tile.rs:26-40`) is a `#[serde(rename_all = "snake_case")]`
enum. Every domain-facing string for that enum elsewhere comes from serde. Here the
terrain string is derived from the `Debug` impl instead. It is correct **today** only
because all 10 current variants are single-word (`Forest` → `"forest"` == serde tag).
The moment a multi-word variant is added (e.g. `DeepWater`), `{:?}.to_lowercase()`
yields `"deepwater"` while the serde tag is `"deep_water"` — the L4 prompt's `terrain`
slot and the canonical-default template silently diverge from every other
representation of the same enum, with no compile error and no failing test.

**Why it matters:** spec D7 pins `terrain` as "the lowercased `TerrainKind`" and
guarantees it is always populated; a latent representation split is a maintenance
trap on the closed-enum contract (§11 / TMP-A8 schema-additive).

**Fix:** derive the tag from serde — `serde_json::to_value(z.terrain_type)` → `.as_str()`,
or add a `TerrainKind::tag(self) -> &'static str` method mirroring `NarrationLanguage::tag()`.
Add a test asserting tag == serde rename for every variant.

---

## WARN 2 — the Hole-3 accept-side out-of-subset guard has zero test coverage

`l4_validate.rs:199-201` — `partition_l4_response` accepts a narration iff
`subset_ids.contains(zone_id) && !failed.contains(zone_id)`. The captured ContextHub
lesson is explicit: "the accept side must reject out-of-subset items so they cannot
overwrite saved work" and "verify it does not re-open these."

The L3 sibling has a dedicated test — `validate.rs:462`
`partition_response_ignores_out_of_subset_entries` (subset = `obj_1`, response also
contains `obj_99`). The L4 suite has **no equivalent**. The only L4 partition test,
`partition_narrows_to_the_failing_subset` (`l4_validate.rs:302`), feeds a response
whose zones (`a`, `b`) are *all in subset*, so the `subset_ids.contains(...)` accept
clause is never exercised. `l4_mock.rs` likewise never scripts a retry where the LLM
re-emits an already-accepted zone.

**Why it matters:** the accept-side guard is currently belt-and-suspenders with the
R1 `UnknownZoneId` path (an out-of-subset zone is also flagged `UnknownZoneId` →
`failed`), so it works today — but an untested redundant guard is one refactor away
from silently regressing the exactly-once / no-overwrite invariant the lesson warns
about. AC-8 ("mock-gateway L4 tests cover ... retry") is not fully satisfied.

**Fix:** add a unit test mirroring `partition_response_ignores_out_of_subset_entries`
(subset = `[zone_a]`, response = `[zone_a, zone_z]`, assert only `zone_a` accepted),
and an `l4_mock.rs` test where attempt 2 re-emits a previously-accepted zone, asserting
no double-count and the saved narration unchanged.

---

## WARN 3 — `extract_key_phrases` silently mangles Vietnamese (`Vi`) narration; only CJK is documented

`keyphrase.rs:28` splits on `|c: char| !c.is_ascii_alphanumeric()`. Spec D6 documents
only the **CJK** limitation ("Phase-3 tests use Latin-script text"). But Vietnamese is
a first-class `NarrationLanguage::Vi` variant (`style.rs:42`), is exercised in
`l4_prompt.rs:110`, and is the user's documented default-context language — yet
Vietnamese is **Latin-script with diacritics**. Characters such as `ơ ư ă ê ô đ` and
tone marks are not `is_ascii_alphanumeric()`, so a word like `nương` splits into
`n` / `ng` — every fragment dropped by the `<3` rule. Vietnamese narration therefore
yields near-empty/garbage key phrases, not covered by the documented "CJK is V2" cut.

**Why it matters:** §10 key-phrase extraction is the sole declared consumer of
`L4Result.narrations` (spec D4); for a `Vi` reality it produces wrong output with no
warning. The cut is real but the spec scopes it too narrowly — "Latin-script" is
asserted safe when accented Latin is not.

**Fix:** widen the split predicate to `!c.is_alphanumeric()` (Unicode-aware — keeps
accented letters together; ASCII lowercasing at line 32 still works for the ranking
key) and re-test; or explicitly extend the D6 note to cover accented-Latin (`Vi`) and
add a test pinning the known-degraded behaviour.

---

Captured rules: read pre-loaded; Guardrails relevant: none
