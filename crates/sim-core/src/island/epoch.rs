//! `RLS-D8` / `RLS-I1` — the ruleset epoch switch.
//!
//! A CHILD module of `island`, not a sibling: a child can reach its parent's
//! private items, so `activate_epoch` still reads `in_step`, `rules` and
//! `digest` directly. A sibling module would have forced those fields to
//! `pub(crate)` — widening the kernel's mutable surface across the whole crate
//! to satisfy a line count, which is the wrong trade and the reason `types.rs`
//! carried a "do not split, it changes every import path" allowlist note.
//!
//! Split out on 2026-07-29 when `Q0b B2a` pushed `island.rs` past its recorded
//! ceiling. Nothing here changed in the move.

use std::sync::Arc;

use super::Island;
use crate::domain::Domain;
use crate::ingress::{IngressItem, Lane};
use super::StepStatus;
use crate::types::{DiscardReason, EpochSwitchRefused, Outcome, RulesetDigest, RulesetEpoch, Seq};

impl<D: Domain> Island<D> {
    // ─── RLS-D8 / RLS-I1 — the ruleset epoch switch ───

    /// Swap the island onto a new ruleset epoch.
    ///
    /// > **`RLS-D8`** — *the switch is atomic per island; the new `Arc` is
    /// > applied between two `step()` calls, never inside one.*
    ///
    /// **What actually makes that true, and it is not this signature.** Taking
    /// `&mut self` stops a *host* from calling this mid-step, because `step`
    /// already holds the borrow — but that is the borrow checker doing
    /// bookkeeping, not an invariant. The reachable violation is an edit to
    /// this file that calls `activate_epoch` from inside `step`, and no
    /// signature prevents that. So the guarantee is carried by the two things
    /// below, which are checkable:
    ///
    /// 1. **`in_step` refuses re-entry.** `step` sets it for its duration; a
    ///    switch attempted from inside one is [`EpochSwitchRefused::MidStep`],
    ///    not a silently-half-applied ruleset. This is the arm that can only be
    ///    reached by a future edit — which is exactly why it is a runtime check
    ///    and not a comment.
    /// 2. **The generation bump.** Everything already admitted was validated
    ///    under the OLD rules — its preconditions were checked against a
    ///    ruleset that no longer applies. Those items discard as `Superseded`
    ///    at their pop rather than being applied under rules they were never
    ///    admitted against. `RLS-D8`'s *"atomic"* means no item straddles the
    ///    switch, and dropping the straddlers is the only way to mean it while
    ///    the switch is a host call rather than an ordered ingress item.
    ///
    /// That last clause is the honest limit of this slice: once the switch
    /// arrives as a typed ingress item (`RLS-A14`), the queued items ahead of
    /// it are legitimately old-epoch work and should *process*, not discard.
    /// Superseding them is the conservative answer available today, and it
    /// errs toward "the client re-submits" rather than "the engine applied a
    /// rule the input was never checked against".
    ///
    /// # Refusals
    ///
    /// * **Not monotonic** (`RLS-I1`) — a duplicated or re-ordered switch must
    ///   not move an island backwards onto rules its committed outcomes were
    ///   not produced under. Refused, never clamped: silently ignoring a
    ///   backwards switch makes a redelivery indistinguishable from a
    ///   legitimate no-op, and the caller needs to know which it got.
    /// * **Equal epoch** is also refused, and deliberately so even though it is
    ///   often harmless: at-least-once delivery makes duplicates NORMAL, and a
    ///   silent `Ok` on the second delivery would hide a real double-activation
    ///   with different bytes behind the common case.
    /// * **Poisoned** — `SC-A8` is *poison-not-resume*, and swapping rules is
    ///   work. An island the host must rebuild does not get quietly repaired.
    ///
    /// On refusal **nothing** is mutated: no digest, no epoch, no generation
    /// bump. A partially-applied switch is the one outcome worse than either
    /// answer.
    pub fn activate_epoch(
        &mut self,
        epoch: RulesetEpoch,
        rules: Arc<D::Rules>,
    ) -> Result<RulesetDigest, EpochSwitchRefused> {
        if self.in_step {
            return Err(EpochSwitchRefused::MidStep);
        }
        let digest = self.swap_ruleset(epoch, rules)?;
        // THE BUMP IS ON THIS PATH ONLY, and that asymmetry is the point.
        //
        // An out-of-band switch has no position in the queue, so items already
        // admitted would be stepped under rules that arrived after them with
        // nothing marking the boundary. Superseding them is conservative but
        // correct.
        //
        // The ORDERED path (`IngressItem::EpochSwitch`) does not bump, because
        // it does not need to: admission stamps `Seq` and nothing else, so
        // every precondition is re-validated at STEP time against the rules in
        // force *then*. An item queued before the switch and stepped after it
        // is checked against the new rules, which is exactly right.
        self.bump_island_gen();
        self.metrics.epoch_switches += 1;
        Ok(digest)
    }

    /// One step whose entire work is a `RLS-A14` epoch switch.
        // RLS-A14 — the switch IS this step's entire work. No `D::apply` runs,
        // so the new `Arc` still lands BETWEEN two applications of domain
        // rules, which is what RLS-D8 means by "between two steps". The
        // out-of-band `activate_epoch` refuses `MidStep`; this path is the
        // ordered one and is exactly where a switch is supposed to happen.
        //
        // Not routed through the seen-set: a switch has no `InputId`, and I2
        // idempotency is a property of domain inputs. Its duplicate protection
        // is RLS-I1 monotonicity, which is strictly stronger — a redelivered
        // switch is refused by its epoch, not by a remembered key that expires
        // out of a TTL window.
                        // `Applied` with no events: the switch HAPPENED, and it
                        // emits nothing the domain produced. The player-facing
                        // announcement is RLS-D17's broadcast, which is the
                        // host's, not the kernel's.
                    // The only refusal reachable here is NotMonotonic — a
                    // poisoned island returned `Poisoned` from `step` before
                    // the pop, and `MidStep` is not checked on the ordered
                    // path. `Superseded` is the honest word for it: a newer
                    // epoch already applied, so this delivery is stale. No new
                    // DiscardReason variant, because there is no new REASON.
    pub(super) fn step_epoch_switch(
        &mut self,
        seq: Seq,
        epoch: RulesetEpoch,
        rules: Arc<D::Rules>,
    ) -> StepStatus {
        let outcome = match self.swap_ruleset(epoch, rules) {
            Ok(_) => {
                self.metrics.epoch_switches += 1;
                // `Applied` with no events: the switch HAPPENED, and it emits
                // nothing the domain produced. The player-facing announcement
                // is RLS-D17's broadcast, which is the host's, not the
                // kernel's.
                Outcome::Applied { events: Vec::new() }
            }
            // The only refusal reachable here is NotMonotonic — a poisoned
            // island returned `Poisoned` from `step` before the pop, and
            // `MidStep` is not checked on the ordered path. `Superseded` is the
            // honest word: a newer epoch already applied, so this delivery is
            // stale. No new DiscardReason variant, because there is no new
            // REASON.
            Err(_) => Outcome::Discarded { reason: DiscardReason::Superseded },
        };
        self.record(seq, outcome);
        StepStatus::Processed(seq)
    }

    /// `RLS-A14` — submit the switch as an **ordinary ingress item**, taking
    /// its place in the queue.
    ///
    /// This is the shape doc 16 §9 specifies and the one a host should reach
    /// for. [`Island::activate_epoch`] stays because an out-of-band swap is
    /// what a rebuild path needs (no queue exists yet), but it pays for the
    /// lack of ordering by superseding everything already admitted; this does
    /// not.
    ///
    /// **`Lane::Live` is not a default, it is a decision.** A switch on
    /// `Background` would drain strictly after every live item, so a busy
    /// island could hold an epoch switch behind player work indefinitely —
    /// and `RLS-D17` forbids a reality-wide barrier precisely so that the
    /// switch can proceed per-island without waiting. Making the caller choose
    /// would let that mistake be made silently.
    pub fn submit_epoch_switch(
        &mut self,
        epoch: RulesetEpoch,
        rules: Arc<D::Rules>,
    ) -> Seq {
        self.ingress.push(
            Lane::Live,
            IngressItem::EpochSwitch {
                // Overwritten by `push`; a placeholder here rather than an
                // `Option` because every other item type has the same contract.
                seq: Seq(0),
                epoch,
                rules,
                // Stamped at admission like any input, so the S1b cascade and
                // dissolution cancel a pending switch the same way they cancel
                // pending work.
                admitted_gen: self.island_gen,
            },
        )
    }

    /// The swap itself: `RLS-I1` monotonicity, `SC-A8` poison, and the three
    /// fields that must move together.
    ///
    /// Shared by the out-of-band host call above and the ordered
    /// `IngressItem::EpochSwitch` arm in `step`, and it deliberately does NOT
    /// check `in_step` — the ordered path runs *inside* a step by construction,
    /// which is not a violation of `RLS-D8` but its intended shape: that step's
    /// entire work IS the switch, so no `D::apply` straddles it.
    pub(super) fn swap_ruleset(
        &mut self,
        epoch: RulesetEpoch,
        rules: Arc<D::Rules>,
    ) -> Result<RulesetDigest, EpochSwitchRefused> {
        if self.poisoned {
            return Err(EpochSwitchRefused::Poisoned);
        }
        if epoch <= self.epoch {
            return Err(EpochSwitchRefused::NotMonotonic {
                current: self.epoch,
                offered: epoch,
            });
        }
        // DERIVED, never supplied — the same RLS-A13 rule `new` follows. A
        // digest passed in beside the rules is a pair nothing forces to agree,
        // and this is the one place where disagreeing would mis-stamp every
        // event emitted after the switch.
        let digest = D::rules_digest(&rules);
        self.rules = rules;
        self.digest = digest;
        self.epoch = epoch;
        Ok(digest)
    }

    /// Force the mid-step flag, so `EpochSwitchRefused::MidStep` can be
    /// *observed* rather than asserted.
    ///
    /// **Without this the `MidStep` arm is a vacuous check.** It is unreachable
    /// from a host — `step` holds `&mut self`, so no caller can be inside one —
    /// which means no test could ever redden it, which means nothing would
    /// notice if a refactor deleted the guard. That is exactly `NV-2`: the
    /// subject cannot vary, so the assertion passes for every input that can
    /// exist. The seam exists to make the arm falsifiable, and it rides the
    /// same `test-util` feature as `Admitted::unchecked` — absent from a
    /// service build, so reaching for it there is a compile error rather than
    /// a review comment.
    #[cfg(feature = "test-util")]
    pub fn set_in_step_for_test(&mut self, on: bool) {
        self.in_step = on;
    }

}
