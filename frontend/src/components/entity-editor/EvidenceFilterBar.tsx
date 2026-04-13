import { Plus } from 'lucide-react';
import type {
  EvidenceType,
  EvidenceFilterOption,
  EvidenceChapterOption,
  EvidenceListParams,
} from '@/features/glossary/types';

const EVIDENCE_TYPES: EvidenceType[] = ['quote', 'summary', 'reference'];
export const TYPE_COLORS: Record<EvidenceType, string> = {
  quote: 'bg-emerald-500/15 text-emerald-400',
  summary: 'bg-blue-500/15 text-blue-400',
  reference: 'bg-amber-500/15 text-amber-400',
};

interface EvidenceFilterBarProps {
  typeFilter: EvidenceType | '';
  onTypeFilter: (v: EvidenceType | '') => void;
  availAttrs: EvidenceFilterOption[];
  attrFilter: string;
  onAttrFilter: (v: string) => void;
  availChapters: EvidenceChapterOption[];
  chapterFilter: string;
  onChapterFilter: (v: string) => void;
  availLanguages: string[];
  language: string;
  onLanguage: (v: string) => void;
  sortBy: EvidenceListParams['sort_by'];
  onSortBy: (v: EvidenceListParams['sort_by']) => void;
  sortDir: EvidenceListParams['sort_dir'];
  onSortDir: (v: EvidenceListParams['sort_dir']) => void;
  onAdd: () => void;
}

export function EvidenceFilterBar({
  typeFilter, onTypeFilter,
  availAttrs, attrFilter, onAttrFilter,
  availChapters, chapterFilter, onChapterFilter,
  availLanguages, language, onLanguage,
  sortBy, onSortBy, sortDir, onSortDir,
  onAdd,
}: EvidenceFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Evidence type chips */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onTypeFilter('')}
          className={`rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
            !typeFilter ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground'
          }`}
        >
          All
        </button>
        {EVIDENCE_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => onTypeFilter(typeFilter === t ? '' : t)}
            className={`rounded-full px-2.5 py-1 text-[10px] font-medium capitalize transition-colors ${
              typeFilter === t ? TYPE_COLORS[t] : 'bg-muted text-muted-foreground hover:text-foreground'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Attribute filter */}
      {availAttrs.length > 0 && (
        <select
          value={attrFilter}
          onChange={(e) => onAttrFilter(e.target.value)}
          className="rounded border bg-background px-2 py-1 text-[11px] focus:outline-none"
          aria-label="Filter by attribute"
        >
          <option value="">All attributes</option>
          {availAttrs.map((a) => (
            <option key={a.attr_value_id} value={a.attr_value_id}>{a.name}</option>
          ))}
        </select>
      )}

      {/* Chapter filter */}
      {availChapters.length > 0 && (
        <select
          value={chapterFilter}
          onChange={(e) => onChapterFilter(e.target.value)}
          className="rounded border bg-background px-2 py-1 text-[11px] focus:outline-none"
          aria-label="Filter by chapter"
        >
          <option value="">All chapters</option>
          {availChapters.map((c) => (
            <option key={c.chapter_id} value={c.chapter_id}>
              {c.chapter_title ?? `Chapter ${c.chapter_index ?? '?'}`}
            </option>
          ))}
        </select>
      )}

      {/* Language selector — dynamic from available_languages */}
      <select
        value={language}
        onChange={(e) => onLanguage(e.target.value)}
        className="rounded border bg-background px-2 py-1 text-[11px] focus:outline-none"
        aria-label="Display language"
      >
        <option value="">Original</option>
        {availLanguages.map((lang) => (
          <option key={lang} value={lang}>{lang}</option>
        ))}
      </select>

      <span className="flex-1" />

      {/* Sort */}
      <select
        value={sortBy}
        onChange={(e) => onSortBy(e.target.value as EvidenceListParams['sort_by'])}
        className="rounded border bg-background px-2 py-1 text-[11px] focus:outline-none"
        aria-label="Sort by"
      >
        <option value="created_at">Created</option>
        <option value="chapter_index">Chapter</option>
        <option value="block_or_line">Block/Line</option>
        <option value="attribute_name">Attribute</option>
      </select>
      <button
        type="button"
        onClick={() => onSortDir(sortDir === 'asc' ? 'desc' : 'asc')}
        className="rounded border bg-background px-2 py-1 text-[10px] font-medium hover:bg-secondary transition-colors"
        title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
      >
        {sortDir === 'asc' ? '\u2191' : '\u2193'}
      </button>

      {/* Add button */}
      <button
        type="button"
        onClick={onAdd}
        className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[10px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        <Plus className="h-3 w-3" /> Add
      </button>
    </div>
  );
}
