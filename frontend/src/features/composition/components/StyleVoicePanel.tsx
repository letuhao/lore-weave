// LOOM Composition (T3.5) — Style & Voice steering panel.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useCast } from '../hooks/useCast';
import {
  useDeleteVoiceProfile, useSetStyleProfile, useSetVoiceProfile, useStyleProfiles, useVoiceProfiles,
} from '../hooks/useStyleVoice';
import type { StyleScope, VoiceProfile } from '../types';

type Props = {
  projectId: string;
  token: string | null;
  chapterId?: string;
  sceneId?: string;
};

/** Density + Pace sliders for one scope. Keyed by scope by the parent so it remounts
 *  (fresh local state) on a scope switch; commits the pair on pointer release. */
function StyleSliders(
  { density, pace, onCommit }: { density: number; pace: number; onCommit: (d: number, p: number) => void },
) {
  const { t } = useTranslation('composition');
  const [d, setD] = useState(density);
  const [p, setP] = useState(pace);
  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-[11px]">
        <span className="flex justify-between text-muted-foreground">
          <span>{t('styleVoice.density')}</span><span>{t('styleVoice.densityRange')}</span>
        </span>
        <input
          type="range" min={0} max={100} value={d} data-testid="style-density"
          onChange={(e) => setD(Number(e.target.value))}
          onPointerUp={() => onCommit(d, p)} onKeyUp={() => onCommit(d, p)}
        />
      </label>
      <label className="flex flex-col gap-1 text-[11px]">
        <span className="flex justify-between text-muted-foreground">
          <span>{t('styleVoice.pace')}</span><span>{t('styleVoice.paceRange')}</span>
        </span>
        <input
          type="range" min={0} max={100} value={p} data-testid="style-pace"
          onChange={(e) => setP(Number(e.target.value))}
          onPointerUp={() => onCommit(d, p)} onKeyUp={() => onCommit(d, p)}
        />
      </label>
    </div>
  );
}

function VoiceRow(
  { vp, onSave, onRemove }: {
    vp: VoiceProfile; onSave: (tags: string[]) => void; onRemove: () => void;
  },
) {
  const { t } = useTranslation('composition');
  const [draft, setDraft] = useState('');
  const addTag = () => {
    const tag = draft.trim();
    if (tag && !vp.tags.includes(tag)) onSave([...vp.tags, tag]);
    setDraft('');
  };
  return (
    <div data-testid={`voice-row-${vp.entity_id}`} className="rounded-lg border bg-card px-3 py-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-sm font-medium">{vp.entity_name}</span>
        <button data-testid={`voice-remove-${vp.entity_id}`} onClick={onRemove}
          className="text-[11px] text-muted-foreground hover:text-destructive">{t('styleVoice.remove')}</button>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {vp.tags.map((tag) => (
          <span key={tag} className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[11px]">
            {tag}
            <button onClick={() => onSave(vp.tags.filter((x) => x !== tag))} aria-label={`remove ${tag}`}>×</button>
          </span>
        ))}
        <input
          value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } }}
          data-testid={`voice-tag-input-${vp.entity_id}`}
          placeholder={t('styleVoice.addTag')}
          className="w-24 rounded border bg-background px-2 py-0.5 text-[11px]"
        />
      </div>
    </div>
  );
}

export function StyleVoicePanel({ projectId, token, chapterId, sceneId }: Props) {
  const { t } = useTranslation('composition');
  const styleQ = useStyleProfiles(projectId, token);
  const setStyle = useSetStyleProfile(projectId, token);
  const voiceQ = useVoiceProfiles(projectId, token);
  const setVoice = useSetVoiceProfile(projectId, token);
  const delVoice = useDeleteVoiceProfile(projectId, token);
  const [scope, setScope] = useState<StyleScope>('work');
  const [search, setSearch] = useState('');
  const cast = useCast(projectId, token, { search });

  const scopes: { key: StyleScope; id?: string }[] = [
    { key: 'work', id: projectId }, { key: 'chapter', id: chapterId }, { key: 'scene', id: sceneId },
  ];
  const scopeId = scopes.find((s) => s.key === scope)?.id;
  const row = styleQ.data?.find((r) => r.scope_type === scope && r.scope_id === scopeId);
  const commitStyle = (d: number, p: number) => {
    if (scopeId) setStyle.mutate({ scope_type: scope, scope_id: scopeId, density: d, pace: p });
  };

  const voices = voiceQ.data ?? [];
  const haveVoice = new Set(voices.map((v) => v.entity_id));
  const matches = (cast.entities.data ?? []).filter((e: any) => !haveVoice.has(e.entity_id)).slice(0, 6);

  return (
    <div data-testid="style-voice-panel" className="flex flex-col gap-4 p-3">
      {/* prose style */}
      <section className="flex flex-col gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('styleVoice.proseStyle')}</div>
        <div className="flex gap-1 text-[11px]">
          {scopes.map((s) => (
            <button
              key={s.key} disabled={!s.id} onClick={() => setScope(s.key)}
              data-testid={`style-scope-${s.key}`}
              className={`rounded px-2 py-0.5 ${scope === s.key ? 'bg-muted font-medium' : 'text-muted-foreground'} disabled:opacity-40`}
            >
              {t(`styleVoice.scope.${s.key}`)}
            </button>
          ))}
        </div>
        <StyleSliders key={scope} density={row?.density ?? 50} pace={row?.pace ?? 50} onCommit={commitStyle} />
        <p className="text-[11px] text-muted-foreground">{t('styleVoice.scopeHint')}</p>
      </section>

      {/* character voices */}
      <section className="flex flex-col gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t('styleVoice.voices')}</div>
        {voices.map((vp) => (
          <VoiceRow
            key={vp.entity_id} vp={vp}
            onSave={(tags) => setVoice.mutate({ ...vp, tags })}
            onRemove={() => delVoice.mutate(vp.entity_id)}
          />
        ))}
        {voices.length === 0 && <p className="text-[11px] text-muted-foreground">{t('styleVoice.noVoices')}</p>}
        {/* add a character */}
        <input
          value={search} onChange={(e) => setSearch(e.target.value)}
          data-testid="voice-search" placeholder={t('styleVoice.addCharacter')}
          className="rounded border bg-background px-2 py-1 text-sm"
        />
        {search.trim().length >= 2 && matches.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {matches.map((e: any) => (
              <button
                key={e.entity_id}
                data-testid={`voice-add-${e.entity_id}`}
                onClick={() => {
                  setVoice.mutate({ entity_id: e.entity_id, entity_name: e.canonical_name || e.name || '?', tags: [] });
                  setSearch('');
                }}
                className="rounded-full border px-2 py-0.5 text-[11px] hover:bg-muted"
              >
                + {e.canonical_name || e.name}
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
