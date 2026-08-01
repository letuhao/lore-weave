//! `PGN-R2b` — the one loader entry point that has a store, and therefore the
//! only one that can pin progression.
//!
//! Split from `lib.rs` at `IMP-D3`'s 400-line ceiling. The seam is honest
//! rather than arithmetic: everything in `lib.rs` folds layers into a `Ruleset`
//! **in memory**, and this is the one call that performs I/O to complete one.

use ruleset_core::{validate_progression, Floor, ProgressionTable, Ruleset};

use crate::patch_progression::{ProgressionKindPatch, ProgressionPatchError};
use crate::labels::{LabelStore, ProgressionLabels};
use crate::progression_store::ProgressionStore;
use crate::{resolve, Layer, LayerSource, LoadError};

/// Resolve a stack that may declare progression, pinning its table into `store`.
///
/// `resolve` and this differ in exactly one thing: a store. Everything
/// `resolve` does happens here first, with the progression refusal lifted —
/// then the authored `[[progression_kinds]]` rows are folded, admitted by
/// `ProgressionSchemaValidator`, stored, and the digest set on the ruleset.
///
/// ## Why the fold cannot union DIGESTS
///
/// `quantities` and `resources` are `AdditiveOnly`/`Union`: a higher layer may
/// declare what a lower one did not, and the fold appends. Progression looks
/// like it should follow, and it cannot — **a digest is not a set.** Two layers
/// each carrying a 32-byte content address have nothing to union; the union has
/// to happen over the TABLES those addresses name. So the rows are folded while
/// they are still rows, and exactly one table is stored at the end. That is
/// also why the pin is `Forbidden` in the classification table: what an author
/// declares is a row, and the digest is derived from all of them together.
///
/// A row for a quantity a higher layer redeclares REPLACES the lower one — the
/// same shape `ResourceTable::declare` refuses as a duplicate *within* a layer
/// but which is the whole point of layering *between* them.
pub fn resolve_and_pin(
    layers: &[LayerSource],
    store: &ProgressionStore,
    labels: &LabelStore,
) -> Result<Ruleset, LoadError> {
    let mut ordered: Vec<&LayerSource> = layers.iter().collect();
    ordered.sort_by_key(|l| l.layer.priority());

    let mut stripped: Vec<LayerSource> = Vec::with_capacity(ordered.len());
    // name -> (declaring layer, row). Later layers overwrite, which IS the fold.
    let mut kinds: Vec<(String, Layer, ProgressionKindPatch)> = Vec::new();
    for l in &ordered {
        if !l.patch.progression_kinds.is_empty()
            && l.layer.priority() < Layer::Preset.priority()
        {
            return Err(LoadError::BelowFloor {
                layer: l.layer,
                field: "progression_kinds",
                floor: Floor::Preset,
            });
        }
        for row in &l.patch.progression_kinds {
            match kinds.iter_mut().find(|(n, _, _)| *n == row.quantity) {
                Some(slot) => *slot = (row.quantity.clone(), l.layer, row.clone()),
                None => kinds.push((row.quantity.clone(), l.layer, row.clone())),
            }
        }
        let mut copy = (*l).clone();
        copy.patch.progression_kinds.clear();
        stripped.push(copy);
    }

    let mut out = resolve(&stripped)?;
    if kinds.is_empty() {
        return Ok(out);
    }

    let ordinal = |name: &str| out.quantities.ordinal_of(name);
    let mut decls = Vec::with_capacity(kinds.len());
    for (name, layer, row) in &kinds {
        let Some(q) = ordinal(name) else {
            return Err(LoadError::Progression {
                layer: *layer,
                source: ProgressionPatchError {
                    kind: name.clone(),
                    reason: "names a quantity this ruleset does not declare. A kind whose                              identity does not exist can never be trained, displayed or                              referenced"
                        .into(),
                },
            });
        };
        let src = row.derives_from.as_deref().and_then(ordinal);
        decls.push(
            row.to_decl(q, src)
                .map_err(|source| LoadError::Progression { layer: *layer, source })?,
        );
    }

    let table = ProgressionTable::declare(decls).map_err(|e| LoadError::Progression {
        layer: Layer::Reality,
        source: ProgressionPatchError { kind: "(table)".into(), reason: e.to_string() },
    })?;
    // CPL-A2 / PGN-A7 — admitted by the ENGINE'S validator before it is stored,
    // so a table that could never load never gets a content address.
    validate_progression(&table, &out.quantities).map_err(LoadError::ProgressionInvalid)?;
    let digest = store.put(&table).map_err(LoadError::ProgressionStore)?;

    // PGN-A18 — the names the author wrote, routed OUT of the hashed bytes and
    // into the sidecar. This is where the split actually happens: one TOML row
    // becomes a mechanical declaration that is hashed and a name that is not, so
    // correcting a translation later moves no digest and strands no world.
    let label_rows = kinds
        .iter()
        .filter_map(|(name, _, row)| {
            let q = out.quantities.ordinal_of(name)?;
            Some((
                q,
                row.name.clone(),
                row.description.clone(),
                row.tiers
                    .iter()
                    .enumerate()
                    .map(|(i, t)| (i as u8, t.name.clone()))
                    .collect(),
            ))
        })
        .collect();
    let built = ProgressionLabels::from_rows(label_rows);
    built.covers(&table).map_err(LoadError::Labels)?;
    labels.put(&digest, &built).map_err(LoadError::Labels)?;

    out.progression = Some(digest);
    Ok(out)
}
