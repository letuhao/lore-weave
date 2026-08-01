//! `Q2` — the AUTHORED form of a pool, and its resolution into the hashed row.
//!
//! Split from `patch.rs` when that file crossed its `IMP-D3` ceiling. The seam:
//! `patch.rs` folds LAYERS, this file translates one authored table into one
//! `ResourceDecl` — which is where every closed-set string is validated, and
//! therefore where every "you wrote X, the legal values are Y" message lives.

use ruleset_core::{
    CeilingBinding, RegenType, ResourceDecl, ResourceError, StatSlot, ZeroBehaviour,
};

/// One authored pool declaration.
///
/// **`quantity` is a NAME, not an ordinal.** Authors never write ordinals —
/// `QTY-A5` says ordinals are assigned, never authored, and a TOML file that
/// contained one would bake an engine-assigned number into content that a
/// different layer stack would renumber.
#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResourcePatch {
    /// The declared quantity this pool is. Must appear in `quantities` —
    /// in THIS layer or a lower one, since the fold is a union.
    pub quantity: String,
    #[serde(default)]
    pub min: i32,
    #[serde(default)]
    pub base: i32,
    /// The stat slot supplying the ceiling, snake_case (`max_hp`).
    ///
    /// Exactly one of `ceiling_slot` / `ceiling_fixed`. Two optional fields
    /// rather than a tagged enum because TOML's inline-table syntax for an
    /// externally-tagged enum is `ceiling = { slot = "max_hp" }`, which serde
    /// reports on failure as *"expected one of ..."* against the WHOLE table —
    /// an error an author cannot act on. Two flat keys give a message that
    /// names the mistake.
    #[serde(default)]
    pub ceiling_slot: Option<String>,
    #[serde(default)]
    pub ceiling_fixed: Option<i32>,
    #[serde(default)]
    pub regen_rate: i32,
    /// `none` | `flat` | `per_mille`. Absent = `none`.
    #[serde(default)]
    pub regen_type: Option<String>,
    /// `clamp` | `block_costs`. Absent = `clamp`.
    ///
    /// There is deliberately no value that means "this pool hitting zero
    /// defeats the actor" — see `ZeroBehaviour`'s doc. Defeat is a law reading
    /// `hp`, and `Q2` leaves it exactly as it is.
    #[serde(default)]
    pub zero_behaviour: Option<String>,
}


impl ResourcePatch {
    /// Resolve the authored row into the hashed [`ResourceDecl`].
    ///
    /// Every closed-set string is validated HERE and refused with the legal
    /// values in the message. A free string that fell through to a default
    /// would be the exact shape the Frontend-Tool Contract forbids: an author
    /// writes `regen_type = "linear"`, gets `none`, and spends an afternoon
    /// wondering why their pool never refills.
    pub fn to_decl(&self, quantity: u16) -> Result<ResourceDecl, ResourceError> {
        let ceiling = match (&self.ceiling_slot, self.ceiling_fixed) {
            (Some(name), None) => CeilingBinding::Slot(slot_by_name(name).ok_or(
                ResourceError::BadBounds {
                    ordinal: quantity,
                    reason: "ceiling_slot is not a stat slot (max_hp, max_stamina, strike_power, armor, accuracy, dodge, crit_chance, crit_mult, speed, move_range)",
                },
            )?),
            (None, Some(v)) => CeilingBinding::Fixed(v),
            (Some(_), Some(_)) => {
                return Err(ResourceError::BadBounds {
                    ordinal: quantity,
                    reason: "ceiling_slot and ceiling_fixed are both set; a pool has ONE ceiling, and picking one for you would silently discard the other",
                })
            }
            (None, None) => {
                return Err(ResourceError::BadBounds {
                    ordinal: quantity,
                    reason: "no ceiling: set ceiling_slot (the ceiling is a derived stat a realm can RAISE - QTY-A8) or ceiling_fixed (a constant). There is no default, because an unbounded pool and a zero-capped one are both plausible and both wrong to guess",
                })
            }
        };
        let regen_type = match self.regen_type.as_deref() {
            None | Some("none") => RegenType::None,
            Some("flat") => RegenType::Flat,
            Some("per_mille") => RegenType::PerMille,
            Some(_) => {
                return Err(ResourceError::BadBounds {
                    ordinal: quantity,
                    reason: "regen_type must be none, flat or per_mille",
                })
            }
        };
        let zero_behaviour = match self.zero_behaviour.as_deref() {
            None | Some("clamp") => ZeroBehaviour::Clamp,
            Some("block_costs") => ZeroBehaviour::BlockCosts,
            Some(_) => {
                return Err(ResourceError::BadBounds {
                    ordinal: quantity,
                    // Named explicitly: "defeat" is the value an author will
                    // reach for first, and the refusal has to say why it is not
                    // there rather than just listing what is.
                    reason: "zero_behaviour must be clamp or block_costs. There is no `defeat`: defeat is an engine law reading hp, and a declared pool cannot change which value ends an encounter",
                })
            }
        };
        Ok(ResourceDecl {
            quantity,
            min: self.min,
            base: self.base,
            ceiling,
            regen_rate: self.regen_rate,
            regen_type,
            zero_behaviour,
        })
    }
}

/// `max_hp` -> [`StatSlot::MaxHp`]. Derived from the enum by walking `ALL`, so
/// a slot added tomorrow is nameable without editing a second list.
fn slot_by_name(name: &str) -> Option<StatSlot> {
    StatSlot::ALL.into_iter().find(|s| snake(&format!("{s:?}")) == name)
}

/// `MaxHp` -> `max_hp`.
fn snake(camel: &str) -> String {
    let mut out = String::with_capacity(camel.len() + 4);
    for (i, ch) in camel.chars().enumerate() {
        if ch.is_ascii_uppercase() {
            if i > 0 {
                out.push('_');
            }
            out.push(ch.to_ascii_lowercase());
        } else {
            out.push(ch);
        }
    }
    out
}
