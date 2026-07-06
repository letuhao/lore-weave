import { useTranslation } from 'react-i18next';
import { Search as SearchIcon, Wrench, Sparkles } from 'lucide-react';
import { FormDialog } from '@/components/shared/FormDialog';
import { EmptyState } from '@/components/shared/EmptyState';
import { Pagination } from '@/components/shared/Pagination';
import type { ToolCatalogItem } from '../types';
import {
  TOOL_SKILL_TABS, TOOL_SKILL_ALL_CATEGORY, TOOL_SKILL_PAGE_SIZE,
  useToolSkillCatalog, type ToolSkillTab,
} from '../hooks/useToolSkillCatalog';

interface ToolSkillAddModalProps {
  open: boolean;
  onClose: () => void;
  token: string | null;
  onAddTool: (name: string) => void;
  onAddSkill: (id: string) => void;
  existingTools: string[];
  existingSkills: string[];
  /** Tool-catalog-simplification Part D (CAT-4) — manually pin a legacy
   *  (superseded, find_tools-invisible) tool into THIS session. Optional:
   *  omitting it hides the "Advanced tools" section entirely. */
  onAddLegacyTool?: (name: string) => void;
  existingLegacyTools?: string[];
}

export function ToolSkillAddModal({
  open,
  onClose,
  token,
  onAddTool,
  onAddSkill,
  existingTools,
  existingSkills,
  onAddLegacyTool,
  existingLegacyTools = [],
}: ToolSkillAddModalProps) {
  const { t } = useTranslation('chat');
  const {
    tab, onTabChange, query, onQueryChange, category, onCategoryChange, page, setPage,
    loading, availableTools, categories, filteredTools, showGroupedAllView, groupedAllView,
    groupPreviewSize, pagedTools, filteredSkills, availableSkillsCount,
    showLegacy, setShowLegacy, availableLegacyToolsCount, filteredLegacyTools,
  } = useToolSkillCatalog(open, token, existingTools, existingSkills, existingLegacyTools);

  const onToolKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const i = TOOL_SKILL_TABS.indexOf(tab);
    const next = e.key === 'ArrowRight' ? (i + 1) % TOOL_SKILL_TABS.length : (i - 1 + TOOL_SKILL_TABS.length) % TOOL_SKILL_TABS.length;
    onTabChange(TOOL_SKILL_TABS[next]);
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={t('rack.add_title', { defaultValue: 'Add tools or skills' })}
      size="2xl"
    >
      <div data-testid="tool-skill-modal" className="flex min-h-0 flex-col gap-3">
        <TabBar tab={tab} onTabChange={onTabChange} onKeyDown={onToolKeyDown} t={t} toolsCount={availableTools.length} skillsCount={availableSkillsCount} />

        <div className="relative">
          <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder={t('rack.search_placeholder', { defaultValue: 'Search…' })}
            data-testid="tool-skill-search"
            className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>

        {tab === 'tools' && categories.length > 1 && (
          <CategoryChips
            categories={categories}
            category={category}
            onCategoryChange={onCategoryChange}
            totalCount={availableTools.length}
            t={t}
          />
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading && (
            <p className="py-4 text-center text-xs text-muted-foreground">{t('view.loading_messages')}</p>
          )}

          {!loading && tab === 'tools' && filteredTools.length === 0 && (
            <EmptyState
              icon={Wrench}
              title={t('rack.no_tools_title', { defaultValue: 'No matching tools' })}
              description={t('rack.no_tools_description', {
                defaultValue: 'Try a different search term or category.',
              })}
            />
          )}

          {!loading && tab === 'tools' && filteredTools.length > 0 && showGroupedAllView && (
            <GroupedToolsView
              groups={groupedAllView}
              previewSize={groupPreviewSize}
              onSeeAll={onCategoryChange}
              onAddTool={(name) => { onAddTool(name); onClose(); }}
              t={t}
            />
          )}

          {!loading && tab === 'tools' && filteredTools.length > 0 && !showGroupedAllView && (
            <>
              <ul className="space-y-1">
                {pagedTools.map((item) => (
                  <ToolRow key={item.name} item={item} onAdd={() => { onAddTool(item.name); onClose(); }} />
                ))}
              </ul>
              <Pagination
                total={filteredTools.length}
                limit={TOOL_SKILL_PAGE_SIZE}
                offset={page * TOOL_SKILL_PAGE_SIZE}
                onChange={(offset) => setPage(Math.floor(offset / TOOL_SKILL_PAGE_SIZE))}
                className="mt-3"
              />
            </>
          )}

          {!loading && tab === 'tools' && onAddLegacyTool && availableLegacyToolsCount > 0 && (
            <AdvancedToolsSection
              show={showLegacy}
              onToggle={() => setShowLegacy((v) => !v)}
              items={filteredLegacyTools}
              count={availableLegacyToolsCount}
              onAdd={(name) => { onAddLegacyTool(name); onClose(); }}
              t={t}
            />
          )}

          {!loading && tab === 'skills' && filteredSkills.length === 0 && (
            <EmptyState
              icon={Sparkles}
              title={t('rack.no_skills_title', { defaultValue: 'No matching skills' })}
              description={t('rack.no_skills_description', {
                defaultValue: 'Try a different search term.',
              })}
            />
          )}

          {!loading && tab === 'skills' && filteredSkills.length > 0 && (
            <ul className="space-y-1">
              {filteredSkills.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    data-testid={`tool-skill-item-${item.id}`}
                    onClick={() => { onAddSkill(item.id); onClose(); }}
                    className="w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted/60"
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
    </FormDialog>
  );
}

type Translate = (key: string, opts?: Record<string, unknown>) => string;

function TabBar({ tab, onTabChange, onKeyDown, t, toolsCount, skillsCount }: {
  tab: ToolSkillTab;
  onTabChange: (t: ToolSkillTab) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  t: Translate;
  toolsCount: number;
  skillsCount: number;
}) {
  return (
    <div
      role="tablist"
      aria-label={t('rack.add_title', { defaultValue: 'Add tools or skills' })}
      className="flex gap-1 border-b"
      onKeyDown={onKeyDown}
    >
      {TOOL_SKILL_TABS.map((tb) => (
        <button
          key={tb}
          type="button"
          role="tab"
          aria-selected={tab === tb}
          tabIndex={tab === tb ? 0 : -1}
          data-testid={`tool-skill-tab-${tb}`}
          onClick={() => onTabChange(tb)}
          className={`flex items-center gap-1.5 rounded-t px-3 py-1.5 text-xs font-medium transition-colors ${
            tab === tb ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {tb === 'tools' ? <Wrench className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
          {tb === 'tools'
            ? t('rack.tools_tab', { defaultValue: 'Tools' })
            : t('rack.skills_tab', { defaultValue: 'Skills' })}
          <span className="text-[10px] text-muted-foreground">({tb === 'tools' ? toolsCount : skillsCount})</span>
        </button>
      ))}
    </div>
  );
}

function CategoryChips({ categories, category, onCategoryChange, totalCount, t }: {
  categories: { category: string; items: ToolCatalogItem[] }[];
  category: string;
  onCategoryChange: (c: string) => void;
  totalCount: number;
  t: Translate;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" data-testid="tool-skill-category-chips">
      <button
        type="button"
        onClick={() => onCategoryChange(TOOL_SKILL_ALL_CATEGORY)}
        data-testid="tool-skill-category-chip-all"
        data-active={category === TOOL_SKILL_ALL_CATEGORY}
        className="rounded-full border px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground data-[active=true]:border-primary/40 data-[active=true]:bg-primary/10 data-[active=true]:text-primary"
      >
        {t('rack.category_all', { defaultValue: 'All' })} ({totalCount})
      </button>
      {categories.map(({ category: c, items }) => (
        <button
          key={c}
          type="button"
          onClick={() => onCategoryChange(c)}
          data-testid={`tool-skill-category-chip-${c}`}
          data-active={category === c}
          className="rounded-full border px-2.5 py-1 text-[11px] font-medium capitalize text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground data-[active=true]:border-primary/40 data-[active=true]:bg-primary/10 data-[active=true]:text-primary"
        >
          {c} ({items.length})
        </button>
      ))}
    </div>
  );
}

function GroupedToolsView({ groups, previewSize, onSeeAll, onAddTool, t }: {
  groups: { category: string; items: ToolCatalogItem[] }[];
  previewSize: number;
  onSeeAll: (category: string) => void;
  onAddTool: (name: string) => void;
  t: Translate;
}) {
  return (
    <div className="space-y-4" data-testid="tool-skill-grouped-view">
      {groups.map(({ category: c, items }) => (
        <div key={c}>
          <div className="mb-1 flex items-center justify-between">
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{c}</h4>
            {items.length > previewSize && (
              <button
                type="button"
                onClick={() => onSeeAll(c)}
                data-testid={`tool-skill-category-more-${c}`}
                className="text-[11px] text-primary hover:underline"
              >
                {t('rack.category_see_all', { count: items.length, defaultValue: 'See all {{count}} →' })}
              </button>
            )}
          </div>
          <ul className="space-y-1">
            {items.slice(0, previewSize).map((item) => (
              <ToolRow key={item.name} item={item} onAdd={() => onAddTool(item.name)} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Tool-catalog-simplification Part D (CAT-4) — a legacy tool is otherwise
 *  unreachable through any normal agent action (find_tools excludes it); this
 *  is the ONLY GUI path back to one, and it's deliberately behind a collapsed
 *  toggle so it doesn't compete with the primary (new-tool) discovery flow. */
function AdvancedToolsSection({ show, onToggle, items, count, onAdd, t }: {
  show: boolean;
  onToggle: () => void;
  items: ToolCatalogItem[];
  count: number;
  onAdd: (name: string) => void;
  t: Translate;
}) {
  return (
    <div className="mt-3 border-t pt-2" data-testid="tool-skill-advanced-section">
      <button
        type="button"
        data-testid="tool-skill-advanced-toggle"
        onClick={onToggle}
        className="text-[11px] font-medium text-muted-foreground hover:text-foreground"
      >
        {show ? '▾' : '▸'} {t('rack.advanced_tools', { count, defaultValue: 'Advanced tools ({{count}})' })}
      </button>
      {show && (
        <>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {t('rack.advanced_tools_hint', {
              defaultValue: 'Superseded tools kept for older callers. Prefer the tools above unless you specifically need one of these.',
            })}
          </p>
          <ul className="mt-1 space-y-1">
            {items.map((item) => (
              <ToolRow key={item.name} item={item} onAdd={() => onAdd(item.name)} legacy />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function ToolRow({ item, onAdd, legacy }: { item: ToolCatalogItem; onAdd: () => void; legacy?: boolean }) {
  return (
    <li>
      <button
        type="button"
        data-testid={`tool-skill-item-${item.name}`}
        onClick={onAdd}
        className="w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-muted/60"
      >
        <div className="flex items-center gap-1.5 text-xs font-medium">
          {item.name}
          <span className="rounded-full border px-1.5 py-0.5 text-[9px] font-normal capitalize text-muted-foreground">
            {item.domain || 'other'}
          </span>
          {legacy && (
            <span
              data-testid={`tool-skill-item-${item.name}-legacy-badge`}
              className="rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-normal text-amber-600 dark:text-amber-400"
            >
              legacy
            </span>
          )}
        </div>
        <div className="text-[10px] text-muted-foreground line-clamp-2">{item.description}</div>
      </button>
    </li>
  );
}
