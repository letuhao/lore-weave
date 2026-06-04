import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { useAuth } from '@/auth';
import { providerApi } from '@/features/settings/api';
import { DimensionOverrideEditor } from './DimensionOverrideEditor';
import type {
  AnachronismMarker,
  BookProfile,
  BookProfileInput,
  DimensionOverrides,
  SuggestedProfile,
} from '../types';

const markersToText = (ms: AnachronismMarker[]) =>
  ms.map((m) => (m.reason ? `${m.term} | ${m.reason}` : m.term)).join('\n');

const textToMarkers = (txt: string): AnachronismMarker[] =>
  txt
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const [term, ...rest] = l.split('|');
      return { term: term.trim(), reason: rest.join('|').trim() };
    })
    .filter((m) => m.term);

/** Drop incomplete `add` rows (a blank `id` the user added but didn't fill — the BE
 *  rejects those with a 400) and trim ids; drop any kind left with no ops. The
 *  sibling ops (remove/relabel/reweight) are preserved. Avoids an avoidable 400. */
const cleanOverrides = (ov: DimensionOverrides): DimensionOverrides => {
  const out: DimensionOverrides = {};
  for (const [kind, ops] of Object.entries(ov)) {
    const next = { ...ops };
    if (next.add) {
      const filtered = next.add.filter((a) => a.id.trim()).map((a) => ({ ...a, id: a.id.trim() }));
      if (filtered.length) next.add = filtered;
      else delete next.add;
    }
    if (Object.keys(next).length) out[kind] = next;
  }
  return out;
};

/** The editable profile form (view). Local state is seeded once from `profile`
 *  (the SettingsPanel keys this component by bookId so it re-seeds per book). Save
 *  sends the FULL profile (BE PUT is a full replace — review #3). Suggest fills the
 *  text fields + overrides from an AI draft (markers are left to the author). */
export function ProfileForm({
  profile,
  onSave,
  onSuggest,
  saving,
  suggesting,
}: {
  profile: BookProfile;
  onSave: (body: BookProfileInput) => void;
  onSuggest: (modelRef: string) => Promise<SuggestedProfile | null>;
  saving: boolean;
  suggesting: boolean;
}) {
  const { t } = useTranslation('enrichment');
  const { accessToken } = useAuth();
  const [worldview, setWorldview] = useState(profile.worldview);
  const [language, setLanguage] = useState(profile.language);
  const [eraPolicy, setEraPolicy] = useState(profile.era_policy ?? '');
  const [voice, setVoice] = useState(profile.voice ?? '');
  const [markersText, setMarkersText] = useState(() => markersToText(profile.anachronism_markers));
  const [overrides, setOverrides] = useState<DimensionOverrides>(profile.dimension_overrides);
  const [modelRef, setModelRef] = useState('');

  const { data: chatModels } = useQuery({
    queryKey: ['user-models', 'chat'],
    queryFn: () => providerApi.listUserModels(accessToken!, { capability: 'chat' }),
    enabled: !!accessToken,
  });
  const models = chatModels?.items ?? [];

  const applyDraft = (d: SuggestedProfile) => {
    setWorldview(d.worldview);
    setLanguage(d.language);
    setEraPolicy(d.era_policy ?? '');
    setVoice(d.voice ?? '');
    setOverrides(d.dimension_overrides);
  };

  const save = () =>
    onSave({
      worldview: worldview.trim(),
      language: language.trim() || 'auto',
      era_policy: eraPolicy.trim() || null,
      voice: voice.trim() || null,
      anachronism_markers: textToMarkers(markersText),
      dimension_overrides: cleanOverrides(overrides),
    });

  const field = 'w-full rounded border bg-background px-2 py-1 text-xs';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2 rounded-lg border bg-card p-3">
        <select
          aria-label={t('settings.suggest_model')}
          value={modelRef}
          onChange={(e) => setModelRef(e.target.value)}
          className="rounded border bg-background px-2 py-1 text-xs"
        >
          <option value="">{t('settings.select_model')}</option>
          {models.map((m) => (
            <option key={m.user_model_id} value={m.user_model_id}>
              {m.alias || m.provider_model_name}
            </option>
          ))}
        </select>
        <button
          type="button"
          data-testid="profile-suggest"
          disabled={!modelRef || suggesting}
          onClick={() => void onSuggest(modelRef).then((d) => d && applyDraft(d))}
          className="inline-flex items-center gap-1.5 rounded-md bg-secondary px-3 py-1.5 text-xs font-medium hover:bg-secondary/80 disabled:opacity-50"
        >
          <Sparkles className="h-3.5 w-3.5" />
          {suggesting ? t('settings.suggesting') : t('settings.suggest')}
        </button>
        <span className="text-[11px] text-muted-foreground">{t('settings.suggest_hint')}</span>
      </div>

      <label className="block space-y-1">
        <span className="text-xs font-medium">{t('settings.worldview')}</span>
        <textarea data-testid="profile-worldview" value={worldview} onChange={(e) => setWorldview(e.target.value)} rows={2} className={field} />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="text-xs font-medium">{t('settings.language')}</span>
          <input data-testid="profile-language" value={language} onChange={(e) => setLanguage(e.target.value)} className={field} />
        </label>
        <label className="block space-y-1">
          <span className="text-xs font-medium">{t('settings.voice')}</span>
          <input value={voice} onChange={(e) => setVoice(e.target.value)} className={field} />
        </label>
      </div>
      <label className="block space-y-1">
        <span className="text-xs font-medium">{t('settings.era_policy')}</span>
        <input value={eraPolicy} onChange={(e) => setEraPolicy(e.target.value)} className={field} />
        <span className="text-[11px] text-muted-foreground">{t('settings.era_hint')}</span>
      </label>
      <label className="block space-y-1">
        <span className="text-xs font-medium">{t('settings.markers')}</span>
        <textarea
          aria-label={t('settings.markers')}
          value={markersText}
          onChange={(e) => setMarkersText(e.target.value)}
          rows={3}
          placeholder={t('settings.markers_placeholder')}
          className={`${field} font-mono`}
        />
        <span className="text-[11px] text-muted-foreground">{t('settings.markers_hint')}</span>
      </label>

      <div className="space-y-1">
        <span className="text-xs font-medium">{t('settings.dimensions')}</span>
        <DimensionOverrideEditor bookId={profile.book_id ?? ''} value={overrides} onChange={setOverrides} />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          data-testid="profile-save"
          disabled={saving}
          onClick={save}
          className="rounded-md bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {saving ? t('settings.saving') : t('actions.save')}
        </button>
        <span className="text-[11px] text-muted-foreground">
          {t('settings.source', { source: t(`settings.source_${profile.profile_source}`) })}
        </span>
      </div>
    </div>
  );
}
