import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import type {
  EvidenceListItem,
  EvidenceListParams,
  EvidenceFilterOption,
  EvidenceChapterOption,
  EvidenceType,
  PatchEvidencePayload,
} from '@/features/glossary/types';

const PAGE_SIZE = 20;

export function useEvidenceList(bookId: string, entityId: string, bookOriginalLanguage?: string) {
  const { accessToken } = useAuth();

  // List state
  const [items, setItems] = useState<EvidenceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [availAttrs, setAvailAttrs] = useState<EvidenceFilterOption[]>([]);
  const [availChapters, setAvailChapters] = useState<EvidenceChapterOption[]>([]);
  const [availLanguages, setAvailLanguages] = useState<string[]>([]);

  // Filters
  const [typeFilter, setTypeFilter] = useState<EvidenceType | ''>('');
  const [attrFilter, setAttrFilter] = useState('');
  const [chapterFilter, setChapterFilter] = useState('');
  const [language, setLanguage] = useState(bookOriginalLanguage ?? '');
  const [sortBy, setSortBy] = useState<EvidenceListParams['sort_by']>('created_at');
  const [sortDir, setSortDir] = useState<EvidenceListParams['sort_dir']>('desc');
  const [offset, setOffset] = useState(0);

  // Track whether we've loaded filter options (only on first page)
  const filterOptionsLoaded = useRef(false);

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
      // Only update filter options when returned (first page)
      if (resp.available_attributes.length > 0 || !filterOptionsLoaded.current) {
        setAvailAttrs(resp.available_attributes);
        setAvailChapters(resp.available_chapters);
        setAvailLanguages(resp.available_languages);
        filterOptionsLoaded.current = true;
      }
    } catch (e) {
      toast.error((e as Error).message);
    }
    setLoading(false);
  }, [accessToken, bookId, entityId, offset, sortBy, sortDir, typeFilter, attrFilter, chapterFilter, language]);

  // Single effect for fetching — offset changes are the ONLY trigger for pagination.
  // Filter changes reset offset to 0 via the handler functions, which triggers a re-fetch.
  useEffect(() => { void fetchList(); }, [fetchList]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  // Filter change handlers that reset offset (preventing double fetch)
  const changeTypeFilter = useCallback((v: EvidenceType | '') => { setTypeFilter(v); setOffset(0); }, []);
  const changeAttrFilter = useCallback((v: string) => { setAttrFilter(v); setOffset(0); }, []);
  const changeChapterFilter = useCallback((v: string) => { setChapterFilter(v); setOffset(0); }, []);
  const changeLanguage = useCallback((v: string) => { setLanguage(v); setOffset(0); }, []);
  const changeSortBy = useCallback((v: EvidenceListParams['sort_by']) => { setSortBy(v); setOffset(0); }, []);
  const changeSortDir = useCallback((v: EvidenceListParams['sort_dir']) => { setSortDir(v); setOffset(0); }, []);
  const clearFilters = useCallback(() => { setTypeFilter(''); setAttrFilter(''); setChapterFilter(''); setOffset(0); }, []);

  // Edit handlers
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<PatchEvidencePayload>({});
  const [editSaving, setEditSaving] = useState(false);

  const startEdit = useCallback((item: EvidenceListItem) => {
    setEditingId(item.evidence_id);
    setEditForm({
      original_text: item.original_text,
      evidence_type: item.evidence_type,
      block_or_line: item.block_or_line,
      note: item.note,
    });
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditForm({});
  }, []);

  const saveEdit = useCallback(async (item: EvidenceListItem) => {
    if (!accessToken) return;
    setEditSaving(true);
    try {
      await glossaryApi.patchEvidence(bookId, entityId, item.attr_value_id, item.evidence_id, editForm, accessToken);
      toast.success('Evidence updated');
      setEditingId(null);
      void fetchList();
    } catch (e) {
      toast.error((e as Error).message);
    }
    setEditSaving(false);
  }, [accessToken, bookId, entityId, editForm, fetchList]);

  // Delete handler (returns promise for ConfirmDialog pattern)
  const deleteEvidence = useCallback(async (item: EvidenceListItem) => {
    if (!accessToken) return;
    try {
      await glossaryApi.deleteEvidence(bookId, entityId, item.attr_value_id, item.evidence_id, accessToken);
      toast.success('Evidence deleted');
      void fetchList();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [accessToken, bookId, entityId, fetchList]);

  // Create handler
  const [createSaving, setCreateSaving] = useState(false);

  const createEvidence = useCallback(async (attrValueId: string, payload: Parameters<typeof glossaryApi.createEvidence>[3]) => {
    if (!accessToken || !attrValueId) return;
    if (!payload.original_text?.trim()) {
      toast.error('Original text is required');
      return;
    }
    setCreateSaving(true);
    try {
      await glossaryApi.createEvidence(bookId, entityId, attrValueId, payload, accessToken);
      toast.success('Evidence created');
      filterOptionsLoaded.current = false; // refresh filter options
      void fetchList();
      setCreateSaving(false);
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      setCreateSaving(false);
      return false;
    }
  }, [accessToken, bookId, entityId, fetchList]);

  return {
    // Data
    items, total, loading, availAttrs, availChapters, availLanguages,
    // Filters
    typeFilter, attrFilter, chapterFilter, language, sortBy, sortDir, offset,
    changeTypeFilter, changeAttrFilter, changeChapterFilter, changeLanguage,
    changeSortBy, changeSortDir, clearFilters,
    // Pagination
    totalPages, currentPage, setOffset, PAGE_SIZE,
    // Edit
    editingId, editForm, setEditForm, editSaving, startEdit, cancelEdit, saveEdit,
    // Delete
    deleteEvidence,
    // Create
    createSaving, createEvidence,
    // Refresh
    refresh: fetchList,
  };
}
