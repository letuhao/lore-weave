//! Sides and the encounter end condition.

/// Which side an actor fights for. Capped at 2 for V1 (COMB_001 Q5 / COMB-Q2):
/// three-sided combat is *unreachable by construction* in V1, so there is no
/// undefined behaviour to guard — V1+ multi-side is a relaxation, not a
/// redesign.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Side {
    A,
    B,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EncounterOutcome {
    /// All of side B at 0 HP.
    Victory,
    /// All of side A at 0 HP.
    Defeat,
    /// Everyone still standing has fled.
    Disengaged,
}

/// Evaluate the end condition (COMB_001 §4).
///
/// A **fled** actor counts as neither alive-for-victory nor dead: fleeing
/// removes you from the fight without handing the other side a kill. Treating
/// flight as death would make running away a loss condition for your own team;
/// treating it as presence would leave the encounter unable to end.
pub fn evaluate_outcome(
    actors: impl Iterator<Item = (Side, i64, bool)> + Clone,
) -> Option<EncounterOutcome> {
    let standing = |side: Side| {
        actors.clone().any(|(s, hp, fled)| s == side && hp > 0 && !fled)
    };
    let any_present = |side: Side| actors.clone().any(|(s, _, _)| s == side);

    let a_standing = standing(Side::A);
    let b_standing = standing(Side::B);

    // Everyone who survived has fled — nobody was defeated.
    let anyone_alive = actors.clone().any(|(_, hp, _)| hp > 0);
    if anyone_alive && !a_standing && !b_standing {
        return Some(EncounterOutcome::Disengaged);
    }
    if any_present(Side::B) && !b_standing {
        return Some(EncounterOutcome::Victory);
    }
    if any_present(Side::A) && !a_standing {
        return Some(EncounterOutcome::Defeat);
    }
    None
}
