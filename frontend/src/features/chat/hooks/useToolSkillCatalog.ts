import { useEffect, useMemo, useState } from 'react';
import { chatApi } from '../api';
import type { SkillCatalogItem, ToolCatalogItem } from '../types';

export type ToolSkillTab = 'tools' | 'skills';

export const TOOL_SKILL_TABS: ToolSkillTab[] = ['tools', 'skills'];
export const TOOL_SKILL_ALL_CATEGORY = '__all__';
export const TOOL_SKILL_PAGE_SIZE = 20;
// A category drilled into from "All" shows every match (no further paging);
// "All" itself caps each category preview so one huge domain can't push
// every other category below the fold.
const ALL_VIEW_GROUP_PREVIEW = 5;

export interface ToolCategoryGroup {
  category: string;
  items: ToolCatalogItem[];
}

/** item.domain is the BE's raw tool-name prefix (chat-service catalog.py
 *  _provider_prefix) — always in sync with the live catalog by construction,
 *  no separate FE mirror to drift. Deliberately NOT the rack's
 *  serverKeyForTool/PREFIX_TO_SERVER grouping: that mirror serves a
 *  different feature (already-added chip grouping) and is pinned 1:1 against
 *  a DIFFERENT backend table (chat-service agent_surface.py) than the one
 *  this catalog's domain field comes from — reusing it here would either
 *  require widening that cross-service pin for an unrelated UI, or drift
 *  silently the day the two diverge further. */
function groupByCategory(items: ToolCatalogItem[]): ToolCategoryGroup[] {
  const byCategory = new Map<string, ToolCatalogItem[]>();
  for (const item of items) {
    const key = item.domain || 'other';
    const list = byCategory.get(key);
    if (list) list.push(item);
    else byCategory.set(key, [item]);
  }
  return [...byCategory.entries()]
    .map(([category, categoryItems]) => ({ category, items: categoryItems }))
    .sort((a, b) => b.items.length - a.items.length || a.category.localeCompare(b.category));
}

/** Owns catalog fetch + search/category/tab/pagination state for the
 *  tools-or-skills add modal. Split out of ToolSkillAddModal (DOCK/MVC:
 *  hooks own logic, components render) so the component stays render-only. */
export function useToolSkillCatalog(
  open: boolean,
  token: string | null,
  existingTools: string[],
  existingSkills: string[],
) {
  const [tab, setTab] = useState<ToolSkillTab>('tools');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState(TOOL_SKILL_ALL_CATEGORY);
  const [page, setPage] = useState(0);
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

  // Resetting on open (not on every keystroke) so a re-open always starts
  // from "All tools" / page 1 rather than the previous session's narrowing.
  useEffect(() => {
    if (open) {
      setTab('tools');
      setQuery('');
      setCategory(TOOL_SKILL_ALL_CATEGORY);
      setPage(0);
    }
  }, [open]);

  const onTabChange = (next: ToolSkillTab) => {
    setTab(next);
    setPage(0);
  };
  const onQueryChange = (next: string) => {
    setQuery(next);
    setPage(0);
  };
  const onCategoryChange = (next: string) => {
    setCategory(next);
    setPage(0);
  };

  const availableTools = useMemo(
    () => tools.filter((item) => !existingTools.includes(item.name)),
    [tools, existingTools],
  );

  const categories = useMemo(() => groupByCategory(availableTools), [availableTools]);

  const filteredTools = useMemo(() => {
    const q = query.trim().toLowerCase();
    return availableTools.filter((item) => {
      if (category !== TOOL_SKILL_ALL_CATEGORY && (item.domain || 'other') !== category) return false;
      if (!q) return true;
      return (
        item.name.toLowerCase().includes(q)
        || item.description.toLowerCase().includes(q)
        || item.domain.toLowerCase().includes(q)
      );
    });
  }, [availableTools, query, category]);

  // "All" groups by category (each capped to a short preview so one huge
  // domain can't push every other category below the fold); drilling into a
  // specific category (or searching) flattens + paginates instead.
  const showGroupedAllView = category === TOOL_SKILL_ALL_CATEGORY && query.trim() === '';
  const groupedAllView = useMemo(
    () => (showGroupedAllView ? groupByCategory(filteredTools) : []),
    [showGroupedAllView, filteredTools],
  );
  const pagedTools = useMemo(
    () => filteredTools.slice(page * TOOL_SKILL_PAGE_SIZE, (page + 1) * TOOL_SKILL_PAGE_SIZE),
    [filteredTools, page],
  );

  const filteredSkills = useMemo(() => {
    const q = query.trim().toLowerCase();
    return skills.filter((item) => {
      if (existingSkills.includes(item.id)) return false;
      if (!q) return true;
      return item.label.toLowerCase().includes(q) || item.id.toLowerCase().includes(q);
    });
  }, [skills, query, existingSkills]);

  const availableSkillsCount = useMemo(
    () => skills.filter((item) => !existingSkills.includes(item.id)).length,
    [skills, existingSkills],
  );

  return {
    tab, onTabChange,
    query, onQueryChange,
    category, onCategoryChange,
    page, setPage,
    loading,
    availableTools,
    categories,
    filteredTools,
    showGroupedAllView,
    groupedAllView,
    groupPreviewSize: ALL_VIEW_GROUP_PREVIEW,
    pagedTools,
    filteredSkills,
    availableSkillsCount,
  };
}
