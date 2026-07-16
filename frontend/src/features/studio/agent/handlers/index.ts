// #09 Lane B — the registration BARREL. ONE place that knows the full set of §8.0b handler files.
//
// Why a barrel: the coverage ledger (`__tests__/effectCoverage.contract.test.ts`) must test what the
// APP actually registers. If the ledger built its own list of register*() calls, it would prove only
// that the handlers CAN be registered — not that the reconciler registers them (memory:
// test-injecting-a-fake-at-the-chokepoint-cannot-prove-the-chokepoint-is-wired). The reconciler and
// the ledger now call the SAME function, so a new handler file that is not added here is DEAD IN THE
// APP and the ledger reds.
//
// 🔴 ADDING A HANDLER FILE (waves 1-8): add its register*/_reset* pair below AND delete its rows from
// PENDING in effectCoverage.contract.test.ts. The test reds until you do.
import { registerDefaultEffectHandlers, _resetDefaultEffectHandlers } from './bookEffects';
import { registerGlossaryEffectHandlers, _resetGlossaryEffectHandlers } from './glossaryEffects';
import { registerKnowledgeEffectHandlers, _resetKnowledgeEffectHandlers } from './knowledgeEffects';
import { registerTranslationEffectHandlers, _resetTranslationEffectHandlers } from './translationEffects';
import { registerAuthoringRunEffectHandlers, _resetAuthoringRunEffectHandlers } from './authoringRunEffects';
import { registerWorldEffectHandlers, _resetWorldEffectHandlers } from './worldEffects';
import { registerArcEffectHandlers, _resetArcEffectHandlers } from './arcEffects';
import { registerCompositionEffectHandlers, _resetCompositionEffectHandlers } from './compositionEffects';

/** Register every Lane-B domain handler. Idempotent (each file guards itself). */
export function registerAllStudioEffectHandlers(): void {
  registerDefaultEffectHandlers();
  registerGlossaryEffectHandlers();
  registerKnowledgeEffectHandlers();
  registerTranslationEffectHandlers();
  registerAuthoringRunEffectHandlers();
  registerWorldEffectHandlers();
  registerArcEffectHandlers();
  registerCompositionEffectHandlers();
}

/** Test-only: undo every idempotency guard so a test can re-register after clearEffectHandlers(). */
export function _resetAllStudioEffectHandlers(): void {
  _resetDefaultEffectHandlers();
  _resetGlossaryEffectHandlers();
  _resetKnowledgeEffectHandlers();
  _resetTranslationEffectHandlers();
  _resetAuthoringRunEffectHandlers();
  _resetWorldEffectHandlers();
  _resetArcEffectHandlers();
  _resetCompositionEffectHandlers();
}
