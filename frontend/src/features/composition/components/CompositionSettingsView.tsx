// LOOM Composition — "Settings" sub-tab (view).
//
// Surfaces the per-Work settings an author should control (FD-1/eval follow-up):
// the narrative_thread ledger toggle (previously UNexposed — the ledger could
// only be enabled by an API call), the default assembly_mode, and a persisted
// DEFAULT drafter model (the #1 prose-quality lever per the model-vs-architecture
// diagnostic). All three are merge-patched into work.settings (the server replaces
// the whole blob, so useSetWorkSettings merges) — the BE already consumes each.
// Render-only; the merge-patch logic lives in useSetWorkSettings.
import { useTranslation } from 'react-i18next';
import { patchForRole, roleRef } from '../modelRoles';
import { useSetWorkSettings } from '../hooks/useWork';
import type { AssemblyMode } from '../types';

type ModelOpt = { user_model_id: string; alias?: string | null; provider_model_name: string };

type Props = {
  projectId: string;
  bookId: string;
  settings: Record<string, unknown>;
  models: ModelOpt[];
  token: string | null;
};

export function CompositionSettingsView({ projectId, bookId, settings, models, token }: Props) {
  const { t } = useTranslation('composition');
  const setSettings = useSetWorkSettings(bookId, token);

  const ntEnabled = settings.narrative_thread_enabled === true;
  const assemblyMode = (settings.assembly_mode as AssemblyMode) || 'per_scene';
  // Read through `modelRoles`, which prefers `settings.model_roles` and falls back to the
  // legacy scalar — so a book saved before the map still shows its model, and one saved after
  // it shows the same value from the new key. Reading only the scalar here would make a
  // freshly saved setting render as empty.
  const defaultModel = roleRef(settings, 'chat');
  const criticModel = roleRef(settings, 'critic');
  // The state the server refuses, mirrored here so the author sees it BEFORE a generation
  // silently runs ungraded. The backend's `critic_policy` is the authority — this is the
  // affordance that lets the warning it returns be acted on.
  const criticIsDrafter = criticModel !== '' && criticModel === defaultModel;
  // Default TRUE, matching the server: `critic_enabled(settings, params)` treats an absent
  // value as on. `!== false` rather than `?? true` because a book saved before this control
  // existed has no key at all, and those two must read the same.
  const criticEnabled = settings.critic_enabled !== false;
  const criticVerifier = roleRef(settings, 'critic_verifier');
  const patch = (p: Record<string, unknown>) =>
    setSettings.mutate({ projectId, currentSettings: settings, patch: p });

  return (
    <div className="flex flex-col gap-4 p-4 text-sm">
      {/* default drafter model — initializes the panel's model selector */}
      <label className="flex flex-col gap-1">
        <span className="font-medium">{t('workSettings.defaultModel', { defaultValue: 'Default drafter model' })}</span>
        <span className="text-xs text-neutral-500">
          {t('workSettings.defaultModelHint', { defaultValue: 'Used as the starting model for this book. A stronger model is the biggest prose-quality lever.' })}
        </span>
        <select
          data-testid="composition-settings-default-model"
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
          value={defaultModel}
          disabled={setSettings.isPending}
          onChange={(e) => patch(patchForRole(settings, 'chat', e.target.value))}
        >
          <option value="">{t('workSettings.noDefaultModel', { defaultValue: 'No default (pick per session)' })}</option>
          {models.map((m) => (
            <option key={m.user_model_id} value={m.user_model_id}>{m.alias || m.provider_model_name}</option>
          ))}
        </select>
      </label>

      {/* critic model — S6. Until this row existed the ONLY way to configure a critic was to
          hand-edit work.settings JSONB, so every book shipped with the blocking tier off and
          nothing said so. `critic_model_source` is written alongside the ref because the
          server treats a ref without its source as INCOMPLETE, not as configured. */}
      <label className="flex flex-col gap-1">
        <span className="font-medium">{t('workSettings.criticModel', { defaultValue: 'Critic model (independent judge)' })}</span>
        <span className="text-xs text-neutral-500">
          {t('workSettings.criticModelHint', { defaultValue: 'A DIFFERENT model grades each draft against your canon, and can block a chapter that contradicts it. Without one, nothing independently checks the prose — a model cannot grade its own work.' })}
        </span>
        <select
          data-testid="composition-settings-critic-model"
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
          value={criticModel}
          disabled={setSettings.isPending}
          // Clearing must remove BOTH forms — the map entry AND the legacy pair. The reader
          // falls back to the scalar, so dropping only the map entry would make the setting
          // appear to un-clear itself on the next read. `patchForRole` owns that, once, for
          // both sides.
          onChange={(e) => patch(patchForRole(settings, 'critic', e.target.value))}
        >
          <option value="">{t('workSettings.noCritic', { defaultValue: 'No critic — drafts are not independently graded' })}</option>
          {models.map((m) => (
            <option key={m.user_model_id} value={m.user_model_id}>{m.alias || m.provider_model_name}</option>
          ))}
        </select>
        {criticIsDrafter && (
          <span data-testid="composition-settings-critic-same-as-drafter" className="text-xs text-amber-600">
            {t('workSettings.criticSameAsDrafter', { defaultValue: 'This is the same model that writes the prose, so it would be grading its own work — the server will refuse it and skip the critique. Pick a different model.' })}
          </span>
        )}
      </label>

      {/* critic VERIFIER model — QC-5 C33, `ModelRole.CRITIC_VERIFIER`. A seventh role rather
          than reuse of the critic, because C31 measured the two jobs apart: one model kept 4/4
          planted violations and 0/3 false ones when auditing its OWN output, so breadth and
          precision can want different models. Empty = audit with the critic itself, which is
          what every book did before this control existed. */}
      <label className="flex flex-col gap-1">
        <span className="font-medium">{t('workSettings.criticVerifier', { defaultValue: 'Verifier model (checks the critic)' })}</span>
        <span className="text-xs text-neutral-500">
          {t('workSettings.criticVerifierHint', { defaultValue: 'Before a canon violation reaches you it is re-checked against the rule it cites, and dropped if the prose does not actually contradict it. Leave empty to re-check with the critic itself; a stronger model here removes more false alarms.' })}
        </span>
        <select
          data-testid="composition-settings-critic-verifier"
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
          value={criticVerifier}
          disabled={setSettings.isPending}
          onChange={(e) => patch(patchForRole(settings, 'critic_verifier', e.target.value))}
        >
          <option value="">{t('workSettings.noCriticVerifier', { defaultValue: 'Use the critic model to re-check its own findings' })}</option>
          {models.map((m) => (
            <option key={m.user_model_id} value={m.user_model_id}>{m.alias || m.provider_model_name}</option>
          ))}
        </select>
      </label>

      {/* critic ON/OFF — QC-5 C32. The toggle EXISTED and no user could reach it:
          `run.params.critic_enabled` has defaulted TRUE since D5 and was written by nothing in
          `frontend/src`, so an author could choose the critic's MODEL above and could not turn
          the critic off. C31 measured why that matters — on a small critic the judge flags prose
          that CONFORMS, citing a rule the quoted span agrees with, and it is on by default.
          Written as a Work setting (the same tier as the model above); run params still override
          it for a single run. Unchecked only when explicitly false, so today's default is kept. */}
      <label className="flex cursor-pointer items-start gap-2">
        <input
          type="checkbox"
          data-testid="composition-settings-critic-enabled"
          className="mt-0.5"
          checked={criticEnabled}
          disabled={setSettings.isPending}
          onChange={(e) => patch({ critic_enabled: e.target.checked })}
        />
        <span className="flex flex-col gap-0.5">
          <span className="font-medium">{t('workSettings.criticEnabled', { defaultValue: 'Grade each draft against canon' })}</span>
          <span className="text-xs text-neutral-500">
            {t('workSettings.criticEnabledHint', { defaultValue: 'On by default. The critic can pause a run on a severe verdict. A small critic model reports contradictions that are not there, so turn this off if the notes are noise — the drafts are unaffected either way.' })}
          </span>
        </span>
      </label>

      {/* assembly mode — per_scene (granular) vs chapter (single-pass, more coherent long-form) */}
      <label className="flex flex-col gap-1">
        <span className="font-medium">{t('workSettings.assemblyMode', { defaultValue: 'Assembly mode' })}</span>
        <span className="text-xs text-neutral-500">
          {t('workSettings.assemblyModeHint', { defaultValue: 'chapter = one coherent pass per chapter (better long-form continuity); per_scene = granular scene-by-scene.' })}
        </span>
        <select
          data-testid="composition-settings-assembly-mode"
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
          value={assemblyMode}
          disabled={setSettings.isPending}
          onChange={(e) => patch({ assembly_mode: e.target.value as AssemblyMode })}
        >
          <option value="per_scene">{t('workSettings.perScene', { defaultValue: 'Per scene' })}</option>
          <option value="chapter">{t('workSettings.chapter', { defaultValue: 'Chapter (single pass)' })}</option>
        </select>
      </label>

      {/* narrative_thread ledger — the promise/foreshadow tracker (advisory) */}
      <label className="flex cursor-pointer items-start gap-2">
        <input
          type="checkbox"
          data-testid="composition-settings-narrative-thread"
          className="mt-0.5"
          checked={ntEnabled}
          disabled={setSettings.isPending}
          onChange={(e) => patch({ narrative_thread_enabled: e.target.checked })}
        />
        <span className="flex flex-col gap-0.5">
          <span className="font-medium">{t('workSettings.narrativeThread', { defaultValue: 'Track narrative threads (promises & foreshadowing)' })}</span>
          <span className="text-xs text-neutral-500">
            {t('workSettings.narrativeThreadHint', { defaultValue: 'Advisory: detects open promises and re-injects them so generation honors/pays them; surfaces unpaid promises as a debt view. Opt-in.' })}
          </span>
        </span>
      </label>

      {setSettings.isError && (
        <p data-testid="composition-settings-error" className="text-xs text-rose-600">
          {t('workSettings.saveError', { defaultValue: 'Could not save settings — try again.' })}
        </p>
      )}
    </div>
  );
}
