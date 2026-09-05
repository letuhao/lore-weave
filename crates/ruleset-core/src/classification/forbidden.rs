//! Keys **no layer may declare**, and the reason an author is told.
//!
//! Split out of [`super`] at `IMP-D3`'s ceiling when `M2` added the verb-row
//! list. The seam is real: everything left in the parent is the CLASSIFIER — a
//! macro whose totality is a compile error to break — and everything here is
//! DATA, a list of refusals with their reasons. They change for different
//! reasons, and this one changes whenever a field turns out not to be the
//! author's.

/// Top-level keys **no layer may declare**, with the reason an author gets told.
///
/// Both identify the ENCODING and the ENGINE, not the rules. They are refused
/// rather than merged because a layer that could set them could make an
/// artifact assert something untrue about itself:
///
/// * `schema_version` selects which codec reads the bytes (`QTY-A11`
///   version dispatch). An author choosing it chooses how their own file is
///   interpreted.
/// * `law_version` is a claim about **which engine laws produced this ruleset**
///   (`QTY-D13`, added by `Q0a`). An author who could set it could ship an
///   artifact claiming laws it was never built with — and since `Q0a` put it
///   inside the hashed bytes, that claim would travel with the digest.
///
/// Today the absence of these keys from `RulesetPatch` already refuses them, as
/// a side effect of `deny_unknown_fields`. That is an **incidental** guarantee,
/// one refactor from gone, and it answers with *"unknown field"* — wrong twice:
/// the field is not unknown, and the author is not told why they may never set
/// it. `NV-4` is precisely a guard defeated by an adjacent decision, so this one
/// is made explicit and tested.
pub const FORBIDDEN_KEYS: &[(&str, &str)] = &[
    (
        "progression",
        "progression is pinned by DIGEST, and the digest is COMPUTED from the table's bytes rather than authored; a layer writing one would be naming bytes it did not produce (RLS-A4 Forbidden). The authoring form lands with the loader, PGN-R2",
    ),
    (
        "schema_version",
        "schema_version identifies the ENCODING (which codec reads these bytes), not the rules; \
         no layer may declare it (RLS-A4 Forbidden)",
    ),
    (
        "law_version",
        "law_version is the engine's claim about which LAWS produced this ruleset (QTY-D13) and \
         is inside the hashed bytes; no layer may declare it (RLS-A4 Forbidden)",
    ),
];

/// **Keys a `[[verbs]]` row may never carry — `CMD-10`'s V4, as a mechanism.**
///
/// > **V4 · Does every authored field enter the engine as an OPERAND — a value
/// > the engine's own fixed rule then judges — or can a field BE the
/// > judgement?**
///
/// `CMD-10`'s own table marks two fields ❌ with the same sentence: *"the author
/// supplies the verdict of the authorisation rule."* This is the list, and it is
/// separate from [`FORBIDDEN_KEYS`] because that one governs the ruleset's TOP
/// LEVEL, while these are forbidden inside a repeating table — so the refusal
/// must name the VERB as well as the key, or an author with a dozen verbs is
/// left looking.
///
/// **This constant IS `CMD-10`'s owed bite.** §9.4 records it as *"owed to BUILD
/// and recorded as owed, not done"*: for a concern classified vocabulary, author
/// a member that sets an authority-bearing field and assert the build REFUSES
/// it. `deny_unknown_fields` alone would have said *"unknown field"* — true, and
/// no help at all, because the field is not unknown. It is very well known and
/// simply not the author's. That distinction is why this carries a reason, and
/// it is the same call [`FORBIDDEN_KEYS`] makes one level up.
///
/// **Non-vacuity.** These strings are not merely absent from the patch struct —
/// they are refused BY NAME on the permissive parse, before deserialization, so
/// the refusal survives a future edit that adds the field for some other
/// purpose. A check that depended on the field's absence would be defeated by
/// the very edit it exists to catch (`NV-4`).
pub const FORBIDDEN_VERB_KEYS: &[(&str, &str)] = &[
    (
        "submitter_class",
        "who may submit a verb is the AUTHORISATION RULE's verdict, not a value the rule \
         judges (CMD-10 V4). An author writing it would be deciding authority rather than \
         supplying an operand to it. A declared verb is submittable by any actor-driver; \
         engine-only payloads are not declared verbs at all",
    ),
    (
        "may_submit_engine_verbs",
        "the same verdict in its plainest form. The engine's turn boundary is host-only so \
         that no driver can mint itself another action by asking for one (IAS-D6); a row \
         that could grant itself that authority would remove the reason the boundary exists",
    ),
    (
        "pays_spend",
        "redirecting WHOM conservation applies to is the conservation rule, not an operand \
         of it (CMD-10 V4, the `victim` row). The engine owns `you must have it, it is \
         deducted once, it is conserved`; the author supplies the amount and nothing else",
    ),
];
