import { useCallback, useEffect, useState } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import type {
  EvidenceListItem,
  EvidenceListParams,
  EvidenceFilterOption,
  EvidenceChapterOption,
  EvidenceType,
  CreateEvidencePayload,
  PatchEvidencePayload,
} from '@/features/glossary/types';

interface EvidenceTabProps {
  bookId: string;
  entityId: string;
  bookOriginalLanguage?: string;
  onCountChange?: () => void;
}

const PAGE_SIZE = 20;
const EVIDENCE_TYPES: EvidenceType[] = ['quote', 'summary', 'reference'];
const TYPE_COLORS: Record<EvidenceType, string> = {
  quote: 'bg-emerald-500/15 text-emerald-400',
  summary: 'bg-blue-500/15 text-blue-400',
  reference: 'bg-amber-500/15 text-amber-400',
};

export function EvidenceTab({ bookId, entityId, bookOriginalLanguage, onCountChange }: EvidenceTabProps) {
  const { accessToken } = useAuth();

  // List state
  const [items, setItems] = useState<EvidenceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [availAttrs, setAvailAttrs] = useState<EvidenceFilterOption[]>([]);
  const [availChapters, setAvailChapters] = useState<EvidenceChapterOption[]>([]);

  // Filters
  const [typeFilter, setTypeFilter] = useState<EvidenceType | ''>('');
  const [attrFilter, setAttrFilter] = useState('');
  const [chapterFilter, setChapterFilter] = useState('');
  const [language, setLanguage] = useState(bookOriginalLanguage ?? '');
  const [sortBy, setSortBy] = useState<EvidenceListParams['sort_by']>('created_at');
  const [sortDir, setSortDir] = useState<EvidenceListParams['sort_dir']>('desc');
  const [offset, setOffset] = useState(0);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<PatchEvidencePayload>({});
  const [saving, setSaving] = useState(false);

  // Create state
  const [creating, setCreating] = useState(false);
  const [createForm, setCreateForm] = useState<CreateEvidencePayload>({
    evidence_type: 'quote',
    original_text: '',
    block_or_line: '',
  });
  const [createAttrValueId, setCreateAttrValueId] = useState('');

  const fetchList = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const params: EvidenceListParams = {
        limit: PAGE_SIZE,
        offset,
        sort_by: sortBy,
        sort_dir: sortDir,
      };
      if (typeFilter) params.evidence_type = typeFilter;
      if (attrFilter) params.attr_value_id = attrFilter;
      if (chapterFilter) params.chapter_id = chapterFilter;
      if (language) params.language = language;

      const resp = await glossaryApi.listEntityEvidences(bookId, entityId, params, accessToken);
      setItems(resp.items);
      setTotal(resp.total);
      setAvailAttrs(resp.available_attributes);
      setAvailChapters(resp.available_chapters);
    } catch (e) {
      toast.error((e as Error).message);
    }
    setLoading(false);
  }, [accessToken, bookId, entityId, offset, sortBy, sortDir, typeFilter, attrFilter, chapterFilter, language]);

  useEffect(() => { void fetchList(); }, [fetchList]);

  // Reset offset when filters change
  useEffect(() => { setOffset(0); }, [typeFilter, attrFilter, chapterFilter, language, sortBy, sortDir]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  // ── Edit handlers ──

  const startEdit = (item: EvidenceListItem) => {
    setEditingId(item.evidence_id);
    setEditForm({
      original_text: item.original_text,
      evidence_type: item.evidence_type,
      block_or_line: item.block_or_line,
      note: item.note,
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({});
  };

  const saveEdit = async (item: EvidenceListItem) => {
    if (!accessToken) return;
    setSaving(true);
    try {
      await glossaryApi.patchEvidence(bookId, entityId, item.attr_value_id, item.evidence_id, editForm, accessToken);
      toast.success('Evidence updated');
      setEditingId(null);
      void fetchList();
      onCountChange?.();
    } catch (e) {
      toast.error((e as Error).message);
    }
    setSaving(false);
  };

  const handleDelete = async (item: EvidenceListItem) => {
    if (!accessToken) return;
    if (!confirm('Delete this evidence?')) return;
    try {
      await glossaryApi.deleteEvidence(bookId, entityId, item.attr_value_id, item.evidence_id, accessToken);
      toast.success('Evidence deleted');
      void fetchList();
      onCountChange?.();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  // ── Create handlers ──

  const openCreate = () => {
    setCreating(true);
    setCreateForm({ evidence_type: 'quote', original_text: '', block_or_line: '' });
    setCreateAttrValueId(availAttrs[0]?.attr_value_id ?? '');
  };

  const saveCreate = async () => {
    if (!accessToken || !createAttrValueId) return;
    if (!createForm.original_text?.trim()) {
      toast.error('Original text is required');
      return;
    }
    setSaving(true);
    try {
      await glossaryApi.createEvidence(bookId, entityId, createAttrValueId, createForm, accessToken);
      toast.success('Evidence created');
      setCreating(false);
      void fetchList();
      onCountChange?.();
    } catch (e) {
      toast.error((e as Error).message);
    }
    setSaving(false);
  };

  // ── Render ──

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Evidence type chips */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setTypeFilter('')}
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
              onClick={() => setTypeFilter(typeFilter === t ? '' : t)}
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
            onChange={(e) => setAttrFilter(e.target.value)}
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
            onChange={(e) => setChapterFilter(e.target.value)}
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

        {/* Language selector */}
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="rounded border bg-background px-2 py-1 text-[11px] focus:outline-none"
          aria-label="Display language"
        >
          <option value="">Original</option>
          <option value="en">English</option>
          <option value="vi">Vietnamese</option>
          <option value="ja">Japanese</option>
          <option value="zh">Chinese</option>
          <option value="zh-TW">Chinese (TW)</option>
        </select>

        <span className="flex-1" />

        {/* Sort */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as EvidenceListParams['sort_by'])}
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
          onClick={() => setSortDir(sortDir === 'asc' ? 'desc' : 'asc')}
          className="rounded border bg-background px-2 py-1 text-[10px] font-medium hover:bg-secondary transition-colors"
          title={sortDir === 'asc' ? 'Ascending' : 'Descending'}
        >
          {sortDir === 'asc' ? '↑' : '↓'}
        </button>

        {/* Add button */}
        <button
          type="button"
          onClick={openCreate}
          className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[10px] font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3 w-3" /> Add
        </button>
      </div>

      {/* Create form */}
      {creating && (
        <div className="rounded-lg border bg-card p-4 space-y-3">
          <div className="text-xs font-semibold text-primary">New Evidence</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-muted-foreground">Attribute *</label>
              <select
                value={createAttrValueId}
                onChange={(e) => setCreateAttrValueId(e.target.value)}
                className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
                aria-label="Attribute for new evidence"
              >
                {availAttrs.map((a) => (
                  <option key={a.attr_value_id} value={a.attr_value_id}>{a.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground">Type</label>
              <select
                value={createForm.evidence_type}
                onChange={(e) => setCreateForm({ ...createForm, evidence_type: e.target.value as EvidenceType })}
                className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
                aria-label="Evidence type"
              >
                {EVIDENCE_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground">Original Text *</label>
            <textarea
              value={createForm.original_text}
              onChange={(e) => setCreateForm({ ...createForm, original_text: e.target.value })}
              rows={3}
              className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none resize-y"
              placeholder="Paste the source text..."
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-muted-foreground">Block / Line</label>
              <input
                value={createForm.block_or_line ?? ''}
                onChange={(e) => setCreateForm({ ...createForm, block_or_line: e.target.value })}
                className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
                placeholder="e.g. p.42"
              />
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground">Note</label>
              <input
                value={createForm.note ?? ''}
                onChange={(e) => setCreateForm({ ...createForm, note: e.target.value })}
                className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
                placeholder="Optional note"
              />
            </div>
          </div>
          <div className="flex items-center gap-2 justify-end">
            <button
              type="button"
              onClick={() => setCreating(false)}
              className="rounded-md border px-3 py-1 text-xs text-muted-foreground hover:bg-secondary transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void saveCreate()}
              disabled={saving || !createForm.original_text?.trim()}
              className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {saving && <Loader2 className="h-3 w-3 animate-spin" />}
              Create
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty state */}
      {!loading && items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <FileText className="h-8 w-8 mb-2 opacity-40" />
          <p className="text-xs">No evidences found</p>
          {(typeFilter || attrFilter || chapterFilter) && (
            <button
              type="button"
              onClick={() => { setTypeFilter(''); setAttrFilter(''); setChapterFilter(''); }}
              className="mt-2 text-[10px] text-primary hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {/* Evidence list */}
      {!loading && items.length > 0 && (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.evidence_id} className="rounded-lg border bg-card p-3 space-y-2">
              {editingId === item.evidence_id ? (
                /* ── Edit mode ── */
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[9px] font-medium capitalize ${TYPE_COLORS[item.evidence_type]}`}>
                      {item.evidence_type}
                    </span>
                    <select
                      value={editForm.evidence_type ?? item.evidence_type}
                      onChange={(e) => setEditForm({ ...editForm, evidence_type: e.target.value as EvidenceType })}
                      className="rounded border bg-background px-2 py-0.5 text-[10px] focus:outline-none"
                      aria-label="Edit evidence type"
                    >
                      {EVIDENCE_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                    <span className="flex-1" />
                    <button type="button" onClick={cancelEdit} className="p-1 text-muted-foreground hover:text-foreground" title="Cancel">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <textarea
                    value={editForm.original_text ?? item.original_text}
                    onChange={(e) => setEditForm({ ...editForm, original_text: e.target.value })}
                    rows={3}
                    className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none resize-y"
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[10px] text-muted-foreground">Block / Line</label>
                      <input
                        value={editForm.block_or_line ?? item.block_or_line}
                        onChange={(e) => setEditForm({ ...editForm, block_or_line: e.target.value })}
                        className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground">Note</label>
                      <input
                        value={editForm.note ?? item.note ?? ''}
                        onChange={(e) => setEditForm({ ...editForm, note: e.target.value || null })}
                        className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={cancelEdit}
                      className="rounded-md border px-3 py-1 text-xs text-muted-foreground hover:bg-secondary transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => void saveEdit(item)}
                      disabled={saving}
                      className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                    >
                      {saving && <Loader2 className="h-3 w-3 animate-spin" />}
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                /* ── Read mode ── */
                <>
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className={`rounded-full px-2 py-0.5 font-medium capitalize ${TYPE_COLORS[item.evidence_type]}`}>
                      {item.evidence_type}
                    </span>
                    <span className="rounded bg-muted px-1.5 py-0.5 font-medium text-muted-foreground">
                      {item.attribute_name}
                    </span>
                    {item.chapter_title && (
                      <span className="text-muted-foreground">
                        {item.chapter_title}{item.block_or_line ? ` · ${item.block_or_line}` : ''}
                      </span>
                    )}
                    <span className="flex-1" />
                    <span className="text-muted-foreground">
                      {new Date(item.created_at).toLocaleDateString()}
                    </span>
                    <button type="button" onClick={() => startEdit(item)} className="p-1 text-muted-foreground hover:text-foreground transition-colors" title="Edit">
                      <Pencil className="h-3 w-3" />
                    </button>
                    <button type="button" onClick={() => void handleDelete(item)} className="p-1 text-muted-foreground hover:text-destructive transition-colors" title="Delete">
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                  <p className="text-xs leading-relaxed whitespace-pre-wrap">
                    {item.display_text}
                  </p>
                  {item.display_language !== item.original_language && (
                    <p className="text-[10px] text-muted-foreground italic">
                      Translated ({item.display_language})
                    </p>
                  )}
                  {item.note && (
                    <p className="text-[10px] text-muted-foreground italic">
                      Note: {item.note}
                    </p>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between pt-2">
          <span className="text-[10px] text-muted-foreground">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors"
              title="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-[10px] text-muted-foreground px-2">
              {currentPage} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total}
              className="rounded p-1 text-muted-foreground hover:bg-secondary disabled:opacity-30 transition-colors"
              title="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
