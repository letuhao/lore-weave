// View (MVC) — render-only skills browser. Logic lives in useSkills.
import { useTranslation } from 'react-i18next';
import { useSkills } from '../hooks/useExtensions';
import type { Skill } from '../types';

const TIER_STYLE: Record<string, string> = {
  system: 'border-indigo-400 text-indigo-400',
  user: 'border-teal-400 text-teal-400',
  book: 'border-pink-400 text-pink-400',
};

export function SkillsView() {
  const { t } = useTranslation('extensions');
  const s = useSkills();
  const pageCount = Math.max(1, Math.ceil(s.total / s.limit));

  return (
    <div className="space-y-3" data-testid="extensions-skills-view">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={s.q}
          onChange={(e) => { s.setPage(0); s.setQ(e.target.value); }}
          placeholder={t('skills.search')}
          data-testid="skills-search-input"
          className="min-w-[180px] flex-1 rounded-md border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <select
          value={s.tier}
          onChange={(e) => { s.setPage(0); s.setTier(e.target.value); }}
          data-testid="skills-tier-filter"
          className="rounded-md border bg-background px-2 py-1.5 text-xs"
        >
          <option value="">{t('skills.tier.all')}</option>
          <option value="system">{t('skills.tier.system')}</option>
          <option value="user">{t('skills.tier.user')}</option>
          <option value="book">{t('skills.tier.book')}</option>
        </select>
        <select
          value={s.sort}
          onChange={(e) => s.setSort(e.target.value)}
          data-testid="skills-sort"
          className="rounded-md border bg-background px-2 py-1.5 text-xs"
        >
          <option value="updated">{t('skills.sort.updated')}</option>
          <option value="name">{t('skills.sort.name')}</option>
          <option value="last_triggered">{t('skills.sort.lastTriggered')}</option>
        </select>
      </div>

      {s.error && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400">{s.error}</div>}
      {s.loading && s.skills.length === 0 && <div className="text-xs text-muted-foreground">{t('common.loading')}</div>}
      {!s.loading && s.skills.length === 0 && !s.error && (
        <div className="rounded-md border border-dashed px-6 py-8 text-center text-xs text-muted-foreground">
          {t('skills.empty')}
        </div>
      )}

      <ul className="divide-y rounded-md border">
        {s.skills.map((sk) => (
          <SkillRow key={sk.skill_id} skill={sk} onToggle={(en) => void s.toggle(sk, en)} onRemove={() => void s.remove(sk)} />
        ))}
      </ul>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{s.total === 0 ? '0' : `${s.page * s.limit + 1}–${Math.min((s.page + 1) * s.limit, s.total)}`} {t('common.of')} {s.total}</span>
        <div className="flex gap-1">
          <button disabled={s.page === 0} onClick={() => s.setPage(s.page - 1)} className="rounded border px-2 py-0.5 disabled:opacity-40">‹</button>
          <span className="px-2 py-0.5">{s.page + 1}/{pageCount}</span>
          <button disabled={s.page + 1 >= pageCount} onClick={() => s.setPage(s.page + 1)} className="rounded border px-2 py-0.5 disabled:opacity-40">›</button>
        </div>
      </div>
    </div>
  );
}

function SkillRow({ skill, onToggle, onRemove }: { skill: Skill; onToggle: (enabled: boolean) => void; onRemove: () => void }) {
  const { t } = useTranslation('extensions');
  const isSystem = skill.tier === 'system';
  return (
    <li className="flex items-center gap-3 px-3 py-2" data-testid="skill-row">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{skill.slug}</span>
          <span className={`rounded-full border px-1.5 text-[10px] font-bold uppercase ${TIER_STYLE[skill.tier] ?? ''}`}>{skill.tier}</span>
          {skill.status === 'draft' && <span className="text-[10px] font-semibold text-amber-400">{t('skills.draft')}</span>}
        </div>
        <div className="truncate text-xs text-muted-foreground">{skill.description}</div>
      </div>
      <label className="inline-flex cursor-pointer items-center">
        <input type="checkbox" role="switch" defaultChecked={skill.status !== 'draft'} onChange={(e) => onToggle(e.target.checked)} data-testid="skill-toggle" />
      </label>
      {!isSystem && (
        <button onClick={onRemove} data-testid="skill-delete" className="rounded border border-red-400/50 px-2 py-0.5 text-[11px] text-red-400">{t('common.delete')}</button>
      )}
    </li>
  );
}
