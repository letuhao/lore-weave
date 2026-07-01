import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { chatApi } from '../api';
import type { SkillCatalogItem, ToolCatalogItem } from '../types';

type Tab = 'tools' | 'skills';

interface ToolSkillAddModalProps {
  open: boolean;
  onClose: () => void;
  token: string | null;
  onAddTool: (name: string) => void;
  onAddSkill: (id: string) => void;
  existingTools: string[];
  existingSkills: string[];
}

export function ToolSkillAddModal({
  open,
  onClose,
  token,
  onAddTool,
  onAddSkill,
  existingTools,
  existingSkills,
}: ToolSkillAddModalProps) {
  const { t } = useTranslation('chat');
  const [tab, setTab] = useState<Tab>('tools');
  const [query, setQuery] = useState('');
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [skills, setSkills] = useState<SkillCatalogItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !token) return;
    setLoading(true);
    Promise.all([chatApi.listToolsCatalog(token), chatApi.listSkillsCatalog(token)])
      .then(([tRes, sRes]) => {
        setTools(tRes.items);
        setSkills(sRes.items);
      })
      .catch(() => {
        setTools([]);
        setSkills([]);
      })
      .finally(() => setLoading(false));
  }, [open, token]);

  const filteredTools = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tools.filter((item) => {
      if (existingTools.includes(item.name)) return false;
      if (!q) return true;
      return (
        item.name.toLowerCase().includes(q)
        || item.description.toLowerCase().includes(q)
        || item.domain.toLowerCase().includes(q)
      );
    });
  }, [tools, query, existingTools]);

  const filteredSkills = useMemo(() => {
    const q = query.trim().toLowerCase();
    return skills.filter((item) => {
      if (existingSkills.includes(item.id)) return false;
      if (!q) return true;
      return item.label.toLowerCase().includes(q) || item.id.toLowerCase().includes(q);
    });
  }, [skills, query, existingSkills]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center">
      <div className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-t-lg border border-border bg-card shadow-xl sm:rounded-lg">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold">{t('rack.add_title', { defaultValue: 'Add tools or skills' })}</h3>
          <button type="button" onClick={onClose} className="text-xs text-muted-foreground hover:text-foreground">
            {t('view.cancel', { defaultValue: 'Cancel' })}
          </button>
        </div>
        <div className="flex gap-2 border-b border-border px-4 py-2">
          <button
            type="button"
            onClick={() => setTab('tools')}
            className={`rounded px-2 py-1 text-xs ${tab === 'tools' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground'}`}
          >
            {t('rack.tools_tab', { defaultValue: 'Tools' })}
          </button>
          <button
            type="button"
            onClick={() => setTab('skills')}
            className={`rounded px-2 py-1 text-xs ${tab === 'skills' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground'}`}
          >
            {t('rack.skills_tab', { defaultValue: 'Skills' })}
          </button>
        </div>
        <div className="px-4 py-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('rack.search_placeholder', { defaultValue: 'Search…' })}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          />
        </div>
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          {loading && (
            <p className="py-4 text-center text-xs text-muted-foreground">{t('view.loading_messages')}</p>
          )}
          {!loading && tab === 'tools' && (
            <ul className="space-y-1">
              {filteredTools.slice(0, 50).map((item) => (
                <li key={item.name}>
                  <button
                    type="button"
                    onClick={() => { onAddTool(item.name); onClose(); }}
                    className="w-full rounded-md px-2 py-2 text-left hover:bg-muted/60"
                  >
                    <div className="text-xs font-medium">{item.name}</div>
                    <div className="text-[10px] text-muted-foreground line-clamp-2">{item.description}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!loading && tab === 'skills' && (
            <ul className="space-y-1">
              {filteredSkills.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => { onAddSkill(item.id); onClose(); }}
                    className="w-full rounded-md px-2 py-2 text-left hover:bg-muted/60"
                  >
                    <div className="text-xs font-medium">{item.label}</div>
                    <div className="text-[10px] text-muted-foreground">{item.surfaces.join(', ')}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
