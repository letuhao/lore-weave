// ============================================================================
// ⚠️ DEPRECATED — DO NOT EDIT (agent or human) — see docs/specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md
// ============================================================================
// This legacy chapter editor is SUPERSEDED by Writing Studio v2
// (`/books/:bookId/studio`, `frontend/src/features/studio/**`). Per spec 16 (M1),
// Studio is the sole chapter-editing surface going forward; this page is kept
// alive ONLY as a fallback route reachable by direct URL (never linked to from
// the app UI — `ChaptersTab.tsx`'s row-click/pencil icon already point at
// Studio, spec 16 task 1.5) — a decision to keep it around, not a decision
// pending removal (spec 16 Phase 4b, 2026-07-05: kept indefinitely, not deleted).
//
// DO NOT port new capabilities here, and DO NOT fix bugs here beyond what's
// needed to keep it loading — any real editor-craft work belongs in
// `frontend/src/features/studio/panels/EditorPanel.tsx` and its siblings. If
// you're an agent about to touch this file because a task mentions "the
// chapter editor," stop and check whether the task actually means Studio's
// EditorPanel instead — it almost always does.
// ============================================================================
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  Save, PanelLeft, PanelRight, Clock, ChevronRight, ChevronLeft, ChevronRight as ChevronRightNav, SpellCheck,
  BookOpen, FileText, BookMarked, ListTree, Pen, Sparkles, AlertTriangle, Focus,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { useEditorPanels } from '@/hooks/useEditorPanels';
import { useEditorDirty } from '@/contexts/EditorDirtyContext';
import { RevisionHistory } from '@/components/editor/RevisionHistory';
import { useTurnCheckpoints } from '@/features/composition/hooks/useTurnCheckpoints';
import { TurnCheckpoints } from '@/features/composition/components/TurnCheckpoints';
import { TiptapEditor, type TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { UnsavedChangesDialog } from '@/components/shared/UnsavedChangesDialog';
import { PublishControl } from '@/features/books/components/PublishControl';
import { KnowledgeIndexControl } from '@/features/books/components/KnowledgeIndexControl';
import { cn } from '@/lib/utils';
import { useGrammarEnabled } from '@/hooks/useGrammarCheck';
import { useEditorMode } from '@/hooks/useEditorMode';
import { useWorkmode, type Workmode } from '@/hooks/useWorkmode';
import { WorkmodeSwitcher } from '@/components/editor/WorkmodeSwitcher';
import { ChapterTranslationsPanel } from '@/features/translation/components/ChapterTranslationsPanel';
import { VersionHistoryPanel } from '@/components/editor/VersionHistoryPanel';
import { GlossaryTooltip } from '@/components/editor/GlossaryTooltip';
import { GlossaryAutocomplete } from '@/components/editor/GlossaryAutocomplete';
import { GlossaryPanel } from '@/components/editor/GlossaryPanel';
import { glossaryApi } from '@/features/glossary/api';
import type { EntityNameEntry } from '@/features/glossary/types';
import { Chat } from '@/features/chat/Chat';
import { fireSendToChat } from '@/features/chat/context/sendToChat';
import { registerEditorTarget } from '@/features/chat/context/editorBridge';
import { CompositionPanel } from '@/features/composition/components/CompositionPanel';
import { WorkspaceShell } from '@/features/composition/components/workspace/WorkspaceShell';
import { MobileEditorShell, type MobileGroup } from '@/components/editor/MobileEditorShell';
import { useIsMobile } from '@/hooks/useIsMobile';
import { SelectionToolbar } from '@/features/composition/components/SelectionToolbar';
import { InlineAiLayer } from '@/features/composition/components/InlineAiLayer';
import { useWorkResolution, useChapterScenes } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { useReportProgress, useEnsureBaseline } from '@/features/composition/hooks/useProgress';
import { useMentionHeatmap } from '@/features/composition/hooks/useMentionHeatmap';
import { useFocusMode } from '@/features/composition/hooks/useFocusMode';
import { usePopoutInsertRelay } from '@/features/composition/hooks/usePopoutInsertRelay';
import { useProvenance } from '@/features/composition/hooks/useProvenance';
import { ProvenanceToolbar } from '@/features/composition/components/ProvenanceToolbar';
import { ProvenanceTag } from '@/features/composition/components/ProvenanceTag';
import { aiModelsApi } from '@/features/ai-models/api';
import { useQuery } from '@tanstack/react-query';
import { OutlineTree } from '@/features/composition/components/OutlineTree';
import { useChapterPublishGate, publishGateMessages } from '@/features/composition/hooks/usePublishGate';

function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

export function ChapterEditorPage() {
  const { t } = useTranslation('editor');
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  const panels = useEditorPanels();
  const { focusMode, toggle: toggleFocus } = useFocusMode();  // T5.1 focus/typewriter
  // M5a — mobile shell: a two-level nav (Editor / Studio / History group bar) replaces
  // the desktop 3-pane on ≤767px. The desktop tree is untouched.
  const isMobile = useIsMobile();
  const [mobileGroup, setMobileGroup] = useState<MobileGroup>('editor');

  // Resizable right panel — drag the left edge. Width is per-device UI state
  // (persisted in useEditorPanels → localStorage per CLAUDE.md). During the
  // drag we update a transient `liveRightWidth` for instant feedback and only
  // persist on mouse-up (avoids a localStorage write every frame).
  const [liveRightWidth, setLiveRightWidth] = useState<number | null>(null);
  const rightDragRef = useRef(0);
  const startRightResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = panels.rightWidth ?? 320;
    const clamp = (w: number) => Math.min(Math.max(w, 280), Math.min(window.innerWidth * 0.7, 900));
    rightDragRef.current = startW;
    const onMove = (ev: MouseEvent) => {
      // dragging left → panel grows (right panel is anchored to the right edge)
      rightDragRef.current = clamp(startW + (startX - ev.clientX));
      setLiveRightWidth(rightDragRef.current);
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      panels.setRightWidth(rightDragRef.current);
      setLiveRightWidth(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [panels.rightWidth, panels.setRightWidth]);
  const rightWidth = liveRightWidth ?? panels.rightWidth ?? 320;

  // Resizable left panel — drag its RIGHT edge (left panel is anchored to the
  // left, so dragging right grows it). Same persist-on-mouse-up pattern.
  const [liveLeftWidth, setLiveLeftWidth] = useState<number | null>(null);
  const leftDragRef = useRef(0);
  const startLeftResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = panels.leftWidth ?? 300;
    const clamp = (w: number) => Math.min(Math.max(w, 240), Math.min(window.innerWidth * 0.5, 720));
    leftDragRef.current = startW;
    const onMove = (ev: MouseEvent) => {
      leftDragRef.current = clamp(startW + (ev.clientX - startX));
      setLiveLeftWidth(leftDragRef.current);
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      panels.setLeftWidth(leftDragRef.current);
      setLiveLeftWidth(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [panels.leftWidth, panels.setLeftWidth]);
  const leftWidth = liveLeftWidth ?? panels.leftWidth ?? 300;

  // Editor AI "Compose" mode (per-device UI pref). Agent = tools on
  // (propose_edit edits the doc). Compose = prose-only, no tools — for
  // reasoning models that write well but stumble on tool-calling.
  const [composeMode, setComposeModeState] = useState<boolean>(() => {
    try { return localStorage.getItem('lw_editor_compose_mode') === '1'; } catch { return false; }
  });
  const setComposeMode = useCallback((v: boolean) => {
    setComposeModeState(v);
    try { localStorage.setItem('lw_editor_compose_mode', v ? '1' : '0'); } catch { /* ignore */ }
  }, []);

  // Draft state
  const [version, setVersion] = useState<number | undefined>();
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState('');

  // Chapter metadata
  const [title, setTitle] = useState('');
  const [savedTitle, setSavedTitle] = useState('');
  const [editorialStatus, setEditorialStatus] = useState<'draft' | 'published' | undefined>();
  // WS-0.9 — publish-independent KG indexing. "Is this chapter in my knowledge graph?" is
  // a SEPARATE question from "is it published", so it needs its own state.
  const [kgIndexedRevisionId, setKgIndexedRevisionId] = useState<string | null | undefined>();
  const [kgExclude, setKgExclude] = useState<boolean | undefined>();

  // Editor content
  const [savedBody, setSavedBody] = useState<any>(null);
  const [tiptapJson, setTiptapJson] = useState<any>(null);
  const [textContent, setTextContent] = useState('');
  const tiptapEditorRef = useRef<TiptapEditorHandle>(null);
  // RAID C6 — pin the pre-edit revision at every AI-apply seam so the writer can
  // restore to "before the agent touched it" (see historyMain).
  const checkpoints = useTurnCheckpoints(bookId);
  // RAID C6 — the chapter's latest revision id, held synchronously so capture()
  // can pin the pre-edit restore point WITHOUT an async listRevisions read that
  // could race a concurrent manual save. Refreshed once per chapter open and
  // after every save/restore (all revision-mutating paths end in load()).
  const latestRevIdRef = useRef<string | null>(null);

  // T5.4 M4 — prose accepted in a popped-out Compose/co-writer window has no editor of
  // its own; it relays over the per-book channel and lands here at the cursor (same as
  // the in-app onAccept path below), so popping a panel to monitor 2 still writes to the
  // manuscript on monitor 1.
  usePopoutInsertRelay(bookId, chapterId, (text, model) => {
    if (chapterId) void checkpoints.capture(chapterId, text, 'insert', latestRevIdRef.current);
    tiptapEditorRef.current?.insertAtCursor(text, {
      source: 'ai', status: 'unreviewed', model: model ?? null, ts: new Date().toISOString(),
    });
  });

  // Editor mode + grammar
  const [editorMode, setEditorMode] = useEditorMode();
  const [grammarEnabled, setGrammarEnabled] = useGrammarEnabled();

  // The chapter's primary Workmode — Write (manuscript) / Translate (versions panel) /
  // Compose (co-writer studio). "Read" is not a mode: it opens the full ReaderPage route.
  const [workmode, setWorkmode] = useWorkmode();

  // Panels
  const [rightTab, setRightTab] = useState<'history' | 'ai'>('history');
  const [revKey, setRevKey] = useState(0);

  // T3.2 — resolve the co-writer Work (for the editor Selection Tools' projectId)
  // + lift the active scene so the toolbar grounds on the compose panel's scene.
  // useWorkResolution is react-query-cached, so CompositionPanel reuses this fetch.
  const workResolution = useWorkResolution(bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(bookId, accessToken);
  // EC-3d: the ACTIVE Work (per-book pref, else canonical) so the legacy editor page
  // opens the dị bản a user switched to in the Studio, not always canon.
  const composeWork = resolveActiveWork(workResolution.data, activeWorkId);
  const composeProjectId = composeWork?.project_id ?? null;
  // T4.2 — report the chapter's word count to the progress SSOT on save (best-effort,
  // accrues regardless of which sub-tab is open). `wcRef` keeps the live count fresh
  // for the save callback (which doesn't depend on the per-render `wc`).
  const reportProgress = useReportProgress(composeProjectId ?? undefined, accessToken);
  const ensureBaseline = useEnsureBaseline(composeProjectId ?? undefined, accessToken);
  const wcRef = useRef(0);
  // T4.2 — the chapter's ON-DISK word count at load (NOT the live `wc`, which moves as
  // you type). The baseline is captured from this so pre-existing content is the
  // reference point, not a mid-session count.
  const [loadedWordCount, setLoadedWordCount] = useState<number | null>(null);
  // C17 (WG-5) — "Continue from cursor" needs a model. Prefer the persisted per-Work
  // default; otherwise fall back to the SOLE registered chat model (same auto-pick
  // rule as the guided first-run — only when exactly one exists, never 0/≥2, and read
  // from the registry, no hardcoded model name) so a guided writer can Continue from
  // their cursor without first opening the co-writer Settings to set a default.
  const chatModels = useQuery({
    queryKey: ['composition', 'chat-models'],
    queryFn: () => aiModelsApi.listUserModels(accessToken!, { capability: 'chat' }),
    enabled: !!accessToken,
    select: (d) => d.items.filter((m) => m.is_active),
  });
  const persistedDefaultModel =
    typeof composeWork?.settings?.default_model_ref === 'string' ? composeWork.settings.default_model_ref : null;
  const soleChatModel = chatModels.data?.length === 1 ? chatModels.data[0].user_model_id : null;
  const composeDefaultModel = persistedDefaultModel ?? soleChatModel;
  // Model metadata for the inline-continue reasoning-strategy hint (parity with the
  // Compose panel's generate path). Resolved from the registry — no hardcoded name.
  const composeDefaultModelMeta = chatModels.data?.find((m) => m.user_model_id === composeDefaultModel);
  const [activeSceneId, setActiveSceneId] = useState('');
  // C17 (WG-5) — "Continue from cursor" grounds on a scene. The guided first-run
  // (DPS1) auto-creates an opening scene, but the writer never touched the Compose
  // panel's scene selector, so activeSceneId is still empty. Fall back to this
  // chapter's first scene from the outline so inline Continue works straight after
  // the guided setup — same react-query-cached outline the Compose panel reads.
  const chapterScenes = useChapterScenes(composeProjectId ?? undefined, chapterId, accessToken);
  const effectiveSceneId = activeSceneId || chapterScenes.data?.[0]?.id || '';

  // ARCH-1 C5: when the AI panel opens (or the chapter changes while it's
  // open), auto-attach the current chapter as chat context via the existing
  // send-to-chat event. The chat listener re-fetches the chapter body fresh at
  // send time, so we only pass identity (book/chapter/title) — the title is
  // read through a ref so editing it doesn't re-fire on every keystroke; only
  // tab-open / chapter change triggers it. A microtask defer lets <Chat>'s
  // listener mount first (the defer is belt-and-suspenders for toggle-open).
  const chapterTitleRef = useRef('');
  chapterTitleRef.current = title;
  useEffect(() => {
    if (rightTab !== 'ai' || !bookId || !chapterId) return;
    const id = setTimeout(() => {
      fireSendToChat({
        bookId,
        chapterId,
        chapterTitle: chapterTitleRef.current || 'Untitled chapter',
      });
    }, 0);
    return () => clearTimeout(id);
  }, [rightTab, bookId, chapterId]);

  // ARCH-1 C6 — register this chapter's Tiptap handle so the AI panel's
  // Apply-edit handler can write back to the open document (and verify the
  // proposal targets THIS chapter). Cleared on unmount / chapter change.
  useEffect(() => {
    if (!bookId || !chapterId) return;
    registerEditorTarget({ bookId, chapterId, handleRef: tiptapEditorRef });
    return () => registerEditorTarget(null);
  }, [bookId, chapterId]);

  // Glossary integration
  const [glossaryEntities, setGlossaryEntities] = useState<EntityNameEntry[]>([]);
  const [glossaryEnabled, setGlossaryEnabledState] = useState(true);
  const [heatmapEnabled, setHeatmapEnabled] = useState(false); // T5.2 — in-prose mention tint (off by default)
  const editorElRef = useRef<HTMLElement | null>(null);

  // Left sidebar
  const [leftTab, setLeftTab] = useState<'source' | 'chapters' | 'glossary' | 'outline'>('chapters');
  const [originalContent, setOriginalContent] = useState<string | null>(null);
  const [originalLoading, setOriginalLoading] = useState(false);
  const [allChapters, setAllChapters] = useState<Chapter[]>([]);

  // Navigation
  const [prevChapterId, setPrevChapterId] = useState<string | undefined>();
  const [nextChapterId, setNextChapterId] = useState<string | undefined>();

  // Auto-save
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveRef = useRef<() => Promise<void>>(async () => {});

  const { setIsDirty, guardedNavigate, pendingNavigation, confirmNavigation, cancelNavigation } = useEditorDirty();

  const bodyChanged = tiptapJson ? JSON.stringify(tiptapJson) !== JSON.stringify(savedBody) : false;
  const titleChanged = title !== savedTitle;
  const isDirty = bodyChanged || titleChanged;

  // M9 chapter-gate (OI-1) + A2-S4b: if this book has a composition Work, block
  // Publish until every scene is 'done' AND no scene's latest auto-generation
  // left a CONFIRMED canon contradiction; separately warn (non-blocking) when
  // canon couldn't be verified. No Work → ungated. Reason-building is the pure
  // publishGateMessages helper (unit-tested), kept here so i18n stays in the view.
  const publishGate = useChapterPublishGate(bookId, chapterId, accessToken);
  const { blockedReason: publishBlockedReason, uncheckedWarning: publishUncheckedWarning } =
    publishGateMessages(publishGate, t);

  // Sync isDirty into context so EditorLayout sidebar can read it
  useEffect(() => {
    setIsDirty(isDirty);
    return () => setIsDirty(false);
  }, [isDirty, setIsDirty]);

  // Discard state for in-place cancel (no navigation)
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  // Version history panel
  const [versionHistory, setVersionHistory] = useState<{ blockId: string; blockTitle: string; mediaSrc: string | null } | null>(null);

  // Mode switch with unsaved-changes check
  const [pendingModeSwitch, setPendingModeSwitch] = useState<'classic' | 'ai' | null>(null);
  const handleModeSwitch = useCallback((newMode: 'classic' | 'ai') => {
    // Classic → AI is always safe (expanding, no data loss)
    if (newMode === 'ai' || !isDirty) {
      setEditorMode(newMode);
      return;
    }
    // AI → Classic with dirty editor — confirm first
    setPendingModeSwitch(newMode);
  }, [isDirty, setEditorMode]);

  const discardChanges = useCallback(() => {
    setTiptapJson(null);
    setTitle(savedTitle);
    tiptapEditorRef.current?.setContent(savedBody);
  }, [savedBody, savedTitle]);

  // ── Wire media upload context for image/video blocks ──────────────────────
  // #16 Phase 2 (2.7) — routed through the editor's OWN ref method (writes to
  // `editor.storage.mediaUpload`) instead of the retired module-level singleton
  // (ImageBlockNode.setImageUploadContext/setOnOpenHistory,
  // VideoBlockNode.setOnOpenVideoHistory). This page still mounts exactly one TiptapEditor
  // instance, so behavior is byte-identical to before — same deps, same set/clear shape, just
  // addressed at this page's own editor instance instead of a global variable.
  useEffect(() => {
    if (accessToken && bookId && chapterId) {
      const openHistory = (blockId: string, blockTitle: string, mediaSrc: string | null) => {
        setVersionHistory({ blockId, blockTitle, mediaSrc });
      };
      tiptapEditorRef.current?.setUploadContext({
        token: accessToken,
        bookId,
        chapterId,
        onOpenHistory: openHistory,
        onOpenVideoHistory: openHistory,
      });
    }
    return () => {
      tiptapEditorRef.current?.setUploadContext(null);
    };
  }, [accessToken, bookId, chapterId]);

  // ── Load ──────────────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    if (!accessToken) return;
    setLoadedWordCount(null); // clear the prior chapter's baseline count while loading
    try {
      const [draft, chapter] = await Promise.all([
        booksApi.getDraft(accessToken, bookId, chapterId),
        booksApi.getChapter(accessToken, bookId, chapterId),
      ]);
      setSavedBody(draft.body);
      const loadedText = draft.text_content ?? '';
      setTextContent(loadedText);
      setLoadedWordCount(wordCount(loadedText)); // T4.2 — pre-existing count for the baseline
      setTiptapJson(null);
      setVersion(draft.draft_version);
      const chTitle = chapter.title ?? '';
      setTitle(chTitle);
      setSavedTitle(chTitle);
      setEditorialStatus(chapter.editorial_status);
      // WS-0.9 — the KG markers load with the chapter (see refreshEditorialStatus).
      setKgIndexedRevisionId(chapter.kg_indexed_revision_id ?? null);
      setKgExclude(chapter.kg_exclude ?? false);
      // RAID C6 — refresh the pre-edit-revision pointer. Runs on chapter open and
      // after every save/restore (both call load()), so it always reflects the
      // latest committed revision when the next AI edit captures a checkpoint.
      try {
        const revs = await booksApi.listRevisions(accessToken, bookId, chapterId, { limit: 1, offset: 0 });
        latestRevIdRef.current = revs.items[0]?.revision_id ?? null;
      } catch { latestRevIdRef.current = null; }
    } catch (e) { toast.error((e as Error).message); }
  }, [accessToken, bookId, chapterId]);

  // CM-FE: light refetch of just the chapter's MARKERS after publish/unpublish/index
  // — must NOT touch body/title (would clobber the editor).
  //
  // WS-0.9: the KG markers refresh on the same trip. They must, because the two controls
  // interact: publishing a chapter also indexes it (so the "in your knowledge" badge has
  // to move), and unpublishing does NOT un-index it (so the badge must NOT move).
  // Refreshing only editorial_status would leave the knowledge badge lying.
  const refreshEditorialStatus = useCallback(async () => {
    if (!accessToken) return;
    try {
      const chapter = await booksApi.getChapter(accessToken, bookId, chapterId);
      setEditorialStatus(chapter.editorial_status);
      setKgIndexedRevisionId(chapter.kg_indexed_revision_id ?? null);
      setKgExclude(chapter.kg_exclude ?? false);
    } catch { /* non-fatal — badges stay until next load */ }
  }, [accessToken, bookId, chapterId]);

  useEffect(() => { void load(); }, [load]);

  // Load chapter list — used for prev/next nav and the Chapters sidebar tab
  useEffect(() => {
    if (!accessToken || !bookId || !chapterId) return;
    booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 200, offset: 0 })
      .then((res) => {
        setAllChapters(res.items);
        const idx = res.items.findIndex((c) => c.chapter_id === chapterId);
        setPrevChapterId(idx > 0 ? res.items[idx - 1].chapter_id : undefined);
        setNextChapterId(idx >= 0 && idx < res.items.length - 1 ? res.items[idx + 1].chapter_id : undefined);
      })
      .catch(() => {});
  }, [accessToken, bookId, chapterId]);

  // Load glossary entities for decoration + autocomplete
  const loadGlossaryEntities = useCallback(() => {
    if (!accessToken || !bookId) return;
    glossaryApi.listEntityNames(bookId, accessToken)
      .then((entries) => {
        setGlossaryEntities(entries);
        tiptapEditorRef.current?.setGlossaryEntities(entries);
      })
      .catch(() => {});
  }, [accessToken, bookId]);

  useEffect(() => {
    loadGlossaryEntities();
  }, [loadGlossaryEntities]);

  // Sync glossary enabled state to editor
  useEffect(() => {
    tiptapEditorRef.current?.setGlossaryEnabled(glossaryEnabled);
  }, [glossaryEnabled]);

  // T5.2 — mention heatmap: push the top-cast density terms + the toggle into the
  // editor so the in-prose tinting tracks both the data and the on/off state. The
  // GroundingPanel shares this same query (cache) for its bar list.
  // M7 — the heatmap is now windowed to THIS chapter's per-chapter mention_count
  // (glossary), keyed by bookId + chapterId (not the knowledge projectId).
  const heatmap = useMentionHeatmap(bookId, chapterId, accessToken);
  useEffect(() => {
    // tint the canonical name AND every alias (mention_count counts all surface
    // forms; canonical-only would miss most occurrences in alias-heavy CJK prose)
    const terms = (heatmap.data ?? []).flatMap((h) =>
      [h.name, ...h.aliases].map((name) => ({ name, band: h.band })),
    );
    tiptapEditorRef.current?.setHeatmapTerms(terms);
  }, [heatmap.data]);
  useEffect(() => {
    tiptapEditorRef.current?.setHeatmapEnabled(heatmapEnabled);
  }, [heatmapEnabled]);

  // T5.3 — AI-provenance: derive the unreviewed-span badge + underlay visibility
  // from the live doc (tiptapJson changes on insert / review-click / mark-all).
  const provenance = useProvenance(tiptapEditorRef, tiptapJson);

  // Capture editor DOM element for autocomplete positioning (after editor mounts)
  useEffect(() => {
    const timer = setTimeout(() => {
      const el = document.querySelector('.tiptap-content') as HTMLElement | null;
      editorElRef.current = el;
    }, 100);
    return () => clearTimeout(timer);
  }, [tiptapJson]); // re-capture when editor content loads

  // Insert entity name via editor ref (safe ProseMirror transaction, no DOM mutation)
  const handleInsertEntity = useCallback((from: number, to: number, name: string) => {
    // The from/to are approximate text offsets — use editor commands to replace
    const editorEl = editorElRef.current;
    if (!editorEl) return;
    // For now, use document.execCommand as a bridge — Tiptap will pick up the input event
    // A more robust approach would pass the editor instance directly
    document.execCommand('insertText', false, name);
  }, []);

  // Lazy-load original source when the Source tab is opened
  useEffect(() => {
    if (!panels.left || leftTab !== 'source' || originalContent !== null || originalLoading) return;
    if (!accessToken) return;
    setOriginalLoading(true);
    booksApi.getOriginalContent(accessToken, bookId, chapterId)
      .then((text) => setOriginalContent(text))
      .catch(() => setOriginalContent(''))
      .finally(() => setOriginalLoading(false));
  }, [panels.left, leftTab, accessToken, bookId, chapterId, originalContent, originalLoading]);

  // ── Save ──────────────────────────────────────────────────────────────────

  const save = useCallback(async () => {
    if (!accessToken) return;
    setSaving(true);
    if (autoSaveTimer.current) { clearTimeout(autoSaveTimer.current); autoSaveTimer.current = null; }
    try {
      const bodyToSave = tiptapJson ?? savedBody;
      try {
        await booksApi.patchDraft(accessToken, bookId, chapterId, {
          body: bodyToSave,
          body_format: 'json',
          commit_message: saveNote || undefined,
          expected_draft_version: version,
        });
      } catch (e) {
        // On version conflict, retry without version check (single-user, last-write-wins).
        // Match the structured error (book-service: 409 CHAPTER_DRAFT_CONFLICT) like the
        // publish path does — not a substring of the message, which is brittle to wording.
        const err = e as { code?: string; status?: number };
        if (err.code === 'CHAPTER_DRAFT_CONFLICT' || err.status === 409) {
          await booksApi.patchDraft(accessToken, bookId, chapterId, {
            body: bodyToSave,
            body_format: 'json',
            commit_message: saveNote || undefined,
          });
        } else {
          throw e;
        }
      }
      if (title !== savedTitle) {
        await booksApi.patchChapter(accessToken, bookId, chapterId, { title: title || null });
      }
      setSaveNote('');
      toast.success(t('saved'));
      setRevKey((k) => k + 1);
      // T4.2 — snapshot the chapter's word count for today's progress (fire-and-forget
      // inside the hook; a failure never reaches here / never disrupts the save).
      reportProgress(chapterId, wcRef.current);
      await load();
    } catch (e) { toast.error((e as Error).message); }
    setSaving(false);
  }, [accessToken, bookId, chapterId, tiptapJson, savedBody, saveNote, version, title, savedTitle, load, reportProgress]);

  // Keep ref current so auto-save always calls the latest version
  useEffect(() => { saveRef.current = save; }, [save]);

  // T4.2 — seed the chapter's progress baseline once the Work is resolved and the
  // chapter's on-disk content has loaded. SYNCHRONIZATION (server baseline ↔ loaded
  // resource), not a user-action reaction. Server-side insert-once, so re-firing
  // (e.g. when composeProjectId resolves after load) is a harmless no-op.
  useEffect(() => {
    if (!composeProjectId || loadedWordCount == null) return;
    ensureBaseline(chapterId, loadedWordCount);
  }, [composeProjectId, chapterId, loadedWordCount, ensureBaseline]);

  // ── Auto-save (5 minutes after last change) ─────────────────────────────

  useEffect(() => {
    if (!isDirty) {
      if (autoSaveTimer.current) { clearTimeout(autoSaveTimer.current); autoSaveTimer.current = null; }
      return;
    }
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => { void saveRef.current(); }, 300_000);
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current); };
  }, [isDirty, tiptapJson, title]);

  // Translation is now a first-class Workmode (the embedded ChapterTranslationsPanel with
  // versions / compare / set-active / jobs), not a one-shot toolbar button that overwrote
  // the doc. The old `handleTranslate` (POST /translate-text → setContent) was removed with
  // the button; the reader/translate lifecycle lives in the panel.

  // ── M6 Polish — replace the doc with the self-heal-accepted prose ──────────
  // Builds the same Tiptap paragraph shape book-service writes (a `_text` snapshot per
  // block) from the healed plain text, then swaps the whole doc.
  const handleApplyPolish = useCallback((healedText: string) => {
    if (chapterId) void checkpoints.capture(chapterId, healedText, 'polish', latestRevIdRef.current);  // RAID C6
    const content = healedText.split(/\n\n+/).map((para) => {
      const tx = para.trim();
      return tx
        ? { type: 'paragraph', _text: tx, content: [{ type: 'text', text: tx }] }
        : { type: 'paragraph', _text: '' };
    });
    tiptapEditorRef.current?.setContent({ type: 'doc', content });
    toast.success(t('polish_applied', { defaultValue: 'Applied polish edits' }));
  }, [t, chapterId, checkpoints]);

  // ── Leave-page guard ──────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  // ── Ctrl+S shortcut ───────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        void save();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [save]);

  // ── Chapter navigation (with unsaved-changes guard) ──────────────────────

  const navigateToChapter = (targetId: string) => {
    if (targetId === chapterId) return;
    guardedNavigate(`/books/${bookId}/chapters/${targetId}/edit`);
  };

  // "Read" workmode entry — open the full ReaderPage (TTS / theme / TOC / language switch)
  // over the current draft. It's a route, not an in-editor pane; guarded so an unsaved
  // draft prompts to save first.
  const openReader = useCallback(() => {
    guardedNavigate(`/books/${bookId}/chapters/${chapterId}/read`);
  }, [guardedNavigate, bookId, chapterId]);

  // Compose surfaces its studio in the right companion panel — opening the mode with the
  // panel collapsed would hide the whole point, so ensure it's open on entry.
  const changeWorkmode = useCallback((m: Workmode) => {
    setWorkmode(m);
    if (m === 'compose' && !panels.right) panels.toggleRight();
  }, [setWorkmode, panels]);

  // ── Stats ─────────────────────────────────────────────────────────────────

  const wc = wordCount(textContent);
  wcRef.current = wc; // T4.2 — keep the live count fresh for the save-time progress report
  const charCount = textContent.length;
  const paraCount = textContent ? textContent.split(/\n\n+/).filter(Boolean).length : 0;
  const chapterLang = allChapters.find((c) => c.chapter_id === chapterId)?.original_language;

  // ── Render ────────────────────────────────────────────────────────────────

  // M5a — the three editor surfaces, extracted so the desktop 3-pane AND the mobile
  // group shell render the SAME element instances (the desktop↔mobile flip swaps which
  // branch mounts; within a branch the panes keep their state). editorMain = the center
  // column; studioMain = the hoisted co-writer studio; historyMain = revision history.
  const editorMain = (
    <div className="relative flex flex-1 flex-col overflow-hidden bg-background">
      {/* Title + metadata bar */}
      <div className="flex-shrink-0 border-b px-6 pt-4 pb-3">
        <input
          type="text"
          data-testid="chapter-title-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full bg-transparent font-serif text-xl font-semibold outline-none placeholder:text-muted-foreground/30"
          placeholder={t('title_placeholder')}
        />
        <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
          {chapterLang && (
            <>
              <span>{chapterLang} <span className="font-mono opacity-60">({chapterLang})</span></span>
              <span className="text-border">|</span>
            </>
          )}
          <span>{t('chars', { n: charCount.toLocaleString() })}</span>
          <span className="text-border">|</span>
          <span>{t('words', { n: wc.toLocaleString() })}</span>
          <span className="text-border">|</span>
          <span>{t('paragraphs', { count: paraCount })}</span>
        </div>
      </div>

      {/* T5.3 — AI-provenance toolbar (self-hides when there's nothing to review) */}
      {composeProjectId && !versionHistory && (
        <div className="px-3 pt-1">
          <ProvenanceToolbar
            visible={provenance.visible}
            unreviewedCount={provenance.unreviewedCount}
            onToggleVisible={provenance.toggleVisible}
            onMarkAllReviewed={provenance.markAllReviewed}
          />
        </div>
      )}

      {/* Tiptap editor or version history panel */}
      {versionHistory ? (
        <VersionHistoryPanel
          token={accessToken!}
          bookId={bookId}
          chapterId={chapterId}
          blockId={versionHistory.blockId}
          blockTitle={versionHistory.blockTitle}
          currentMediaUrl={versionHistory.mediaSrc}
          onClose={() => setVersionHistory(null)}
          onRestore={(version) => {
            if (version.media_url) {
              setVersionHistory(null);
            }
          }}
        />
      ) : (
        <TiptapEditor
          ref={tiptapEditorRef}
          content={savedBody}
          onUpdate={(json, text) => { setTiptapJson(json); setTextContent(text); }}
          grammarEnabled={grammarEnabled}
          editorMode={editorMode}
          focusMode={focusMode}
          className="flex-1 overflow-y-auto"
          selectionMenu={composeProjectId
            ? (editor) => (
                <SelectionToolbar
                  editor={editor}
                  projectId={composeProjectId}
                  sceneContext={effectiveSceneId || null}
                  token={accessToken}
                />
              )
            : undefined}
          aiLayer={composeProjectId
            ? (editor) => (
                <InlineAiLayer
                  editor={editor}
                  projectId={composeProjectId}
                  sceneId={effectiveSceneId || null}
                  modelRef={composeDefaultModel}
                  modelKind={composeDefaultModelMeta?.provider_kind}
                  modelName={composeDefaultModelMeta?.provider_model_name}
                  token={accessToken}
                />
              )
            : undefined}
        />
      )}

      {/* Save note — dimmed in focus mode (mockup .savenote) */}
      <div className={cn('flex-shrink-0 border-t px-4 py-2', focusMode && 'pointer-events-none opacity-0')}>
        <input
          value={saveNote}
          onChange={(e) => setSaveNote(e.target.value)}
          placeholder={t('save_note_placeholder')}
          className="w-full rounded border bg-background px-3 py-1.5 text-xs placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring/40"
        />
      </div>
    </div>
  );

  const historyMain = (
    <div className="flex h-full flex-col">
      {/* RAID C6 — AI-edit checkpoints sit above the full revision list; both restore. */}
      <TurnCheckpoints
        checkpoints={checkpoints.checkpoints}
        chapterId={chapterId}
        onRestore={async (cp) => { await checkpoints.restore(cp); await load(); setRevKey((k) => k + 1); }}
      />
      <div className="min-h-0 flex-1">
        <RevisionHistory key={revKey} bookId={bookId} chapterId={chapterId} onRestore={() => { void load(); setRevKey((k) => k + 1); }} />
      </div>
    </div>
  );

  const studioMain = (
    <WorkspaceShell token={accessToken} bookId={bookId} chapterId={chapterId}>
      <CompositionPanel
        key={bookId}
        bookId={bookId}
        chapterId={chapterId}
        token={accessToken}
        onAccept={(text, meta) => {
          if (chapterId) void checkpoints.capture(chapterId, text, 'insert', latestRevIdRef.current);  // RAID C6
          tiptapEditorRef.current?.insertAtCursor(text, {
            source: 'ai', status: 'unreviewed', model: meta?.model ?? null,
            ts: new Date().toISOString(),
          });
        }}
        onApplyPolish={handleApplyPolish}
        sceneId={activeSceneId}
        onSceneChange={setActiveSceneId}
        heatmapEnabled={heatmapEnabled}
        onToggleHeatmap={() => setHeatmapEnabled((v) => !v)}
      />
    </WorkspaceShell>
  );

  // M5a — compact mobile header: breadcrumb-lite + save (the desktop toolbar's controls
  // don't fit a phone; the studio/history affordances live in the bottom group bar).
  const mobileHeader = (
    <div className="flex h-11 flex-shrink-0 items-center gap-2 border-b bg-card px-3">
      <button onClick={() => guardedNavigate(`/books/${bookId}`)} className="truncate text-xs text-muted-foreground" title={t('breadcrumb.book')}>
        {title || t('breadcrumb.chapter')}
      </button>
      <span className="ml-auto" />
      {isDirty ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-warning/12 px-2 py-0.5 text-[10px] font-medium text-warning">
          <span className="h-1.5 w-1.5 rounded-full bg-warning" />{t('unsaved')}
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 rounded-full bg-success/12 px-2 py-0.5 text-[10px] font-medium text-success">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />{t('saved_badge')}
        </span>
      )}
      <button
        data-testid="chapter-save-button-mobile"
        onClick={() => void save()}
        disabled={saving}
        className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        <Save className="h-3 w-3" />{t('save')}
      </button>
    </div>
  );

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* T5.1 — focus-mode continuity pill (static ambient affordance; the live
          continuity signal lives in the co-writer Critic/Grounding tabs). */}
      {focusMode && (
        <div
          data-testid="editor-focus-pill"
          className="fixed right-6 top-14 z-30 inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-[11px] shadow-lg"
        >
          <span className="font-semibold text-success">🛡 {t('focus.continuity', { defaultValue: 'Continuity ✓' })}</span>
          <span className="text-muted-foreground">{t('focus.hint', { defaultValue: '✦ tap a line for grounding' })}</span>
        </div>
      )}
      {/* M5a — mobile: a two-level group shell (Editor / Studio / History) replaces the
          desktop 3-pane. The shared dialogs/tooltips below render in BOTH shells. */}
      {isMobile ? (
        <MobileEditorShell
          group={mobileGroup}
          onGroupChange={setMobileGroup}
          header={mobileHeader}
          editor={editorMain}
          studio={studioMain}
          history={historyMain}
        />
      ) : (
      <>
      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div className="flex h-[42px] flex-shrink-0 items-center justify-between border-b bg-card px-4">

        {/* Breadcrumb + prev/next */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {prevChapterId && (
            <button
              onClick={() => navigateToChapter(prevChapterId)}
              className="rounded p-1 hover:bg-secondary hover:text-foreground"
              title={t('prev_chapter')}
            >
              <ChevronLeft className="h-3 w-3" />
            </button>
          )}
          <button onClick={() => guardedNavigate('/books')} className="hover:text-foreground">{t('breadcrumb.workspace')}</button>
          <ChevronRight className="h-3 w-3" />
          <button onClick={() => guardedNavigate(`/books/${bookId}`)} className="hover:text-foreground">{t('breadcrumb.book')}</button>
          <ChevronRight className="h-3 w-3" />
          <span className="font-medium text-foreground">{title || t('breadcrumb.chapter')}</span>
          {nextChapterId && (
            <button
              onClick={() => navigateToChapter(nextChapterId)}
              className="rounded p-1 hover:bg-secondary hover:text-foreground"
              title={t('next_chapter')}
            >
              <ChevronRightNav className="h-3 w-3" />
            </button>
          )}
        </div>

        {/* Right controls */}
        <div className="flex flex-shrink-0 items-center gap-2">
          {/* Primary workmode switch — Write / Translate / Read / Compose. Replaces the
              old Pen/Sparkles toggle, the Co-write bridge, and the one-off Translate +
              Translations buttons: one obvious dropdown for "what am I doing to this
              chapter". Read opens the full reader route; the rest swap the centre pane. */}
          <WorkmodeSwitcher mode={workmode} onChange={changeWorkmode} onOpenReader={openReader} />

          {/* Write-only sub-controls — the classic/AI editor toggle + grammar check only
              affect the manuscript surface, so they hide outside Write mode. */}
          {workmode === 'write' && (
            <>
              <div className="mx-1 h-4 w-px bg-border" />
              <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
                <button
                  onClick={() => handleModeSwitch('classic')}
                  className={cn(
                    'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                    editorMode === 'classic'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  title={t('mode.classic_title')}
                >
                  <Pen className="h-3 w-3" />
                  {t('mode.classic')}
                </button>
                <button
                  onClick={() => handleModeSwitch('ai')}
                  className={cn(
                    'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                    editorMode === 'ai'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  title={t('mode.ai_title')}
                >
                  <Sparkles className="h-3 w-3" />
                  {t('mode.ai')}
                </button>
              </div>

              {/* Grammar check toggle */}
              <label
                className={cn(
                  'flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                  grammarEnabled ? 'text-warning' : 'text-muted-foreground hover:text-foreground',
                )}
                title={t('grammar_title')}
              >
                <input
                  type="checkbox"
                  checked={grammarEnabled}
                  onChange={(e) => setGrammarEnabled(e.target.checked)}
                  className="sr-only"
                />
                <SpellCheck className="h-3.5 w-3.5" />
              </label>
            </>
          )}

          <div className="mx-1 h-4 w-px bg-border" />

          <button
            onClick={panels.toggleLeft}
            className={cn('rounded p-1.5 transition-colors', panels.left ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')}
            title={t('toggle_source')}
          >
            <PanelLeft className="h-3.5 w-3.5" />
          </button>
          {/* The right companion panel toggles the history/AI chat (Write) or the studio
              (Compose); Translate has its own sidebar so no companion there. */}
          {workmode !== 'translate' && (
            <button
              onClick={panels.toggleRight}
              className={cn('rounded p-1.5 transition-colors', panels.right ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')}
              title={t('toggle_history')}
            >
              <PanelRight className="h-3.5 w-3.5" />
            </button>
          )}
          {/* T5.1 — focus/typewriter mode: hides side panels + dims non-current prose. Only
              meaningful over the Write editor surface. */}
          {workmode === 'write' && (
            <button
              data-testid="editor-focus-toggle"
              onClick={toggleFocus}
              aria-pressed={focusMode}
              className={cn('rounded p-1.5 transition-colors', focusMode ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')}
              title={t('focus.toggle', { defaultValue: 'Focus mode' })}
            >
              <Focus className="h-3.5 w-3.5" />
            </button>
          )}
          <div className="mx-1 h-4 w-px bg-border" />

          {/* Save status */}
          {isDirty ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/12 px-2 py-0.5 text-[10px] font-medium text-warning">
              <span className="h-1.5 w-1.5 rounded-full bg-warning" />
              {t('unsaved')}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success/12 px-2 py-0.5 text-[10px] font-medium text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              {t('saved_badge')}
            </span>
          )}
          <span className="text-[10px] font-mono text-muted-foreground">v{version ?? '?'}</span>

          {isDirty && (
            <button
              onClick={() => setShowDiscardConfirm(true)}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-destructive/50 hover:text-destructive"
              title={t('discard_title')}
            >
              {t('discard')}
            </button>
          )}

          <button
            data-testid="chapter-save-button"
            onClick={() => void save()}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Save className="h-3 w-3" />
            {t('save')}
            <kbd className="ml-1 rounded border border-primary-foreground/20 bg-primary-foreground/10 px-1 py-px font-mono text-[9px]">Ctrl+S</kbd>
          </button>

          <div className="mx-1 h-4 w-px bg-border" />

          {/* A2-S4b: canon could not be verified in some scenes (dirty data —
              cast present but no resolved reading position). NON-blocking: publish
              stays enabled; the author is warned so they can act. */}
          {publishUncheckedWarning && (
            <span
              data-testid="publish-canon-unchecked"
              className="inline-flex items-center gap-1 rounded-full bg-amber-500/12 px-2 py-0.5 text-[10px] font-medium text-amber-600"
              title={t('publish.gate_unchecked_hint')}
            >
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              {publishUncheckedWarning}
            </span>
          )}

          {/* CM-FE: canon publish affordance — "is this the canonical, shareable version?" */}
          <PublishControl
            token={accessToken ?? ''}
            bookId={bookId}
            chapterId={chapterId}
            draftVersion={version}
            editorialStatus={editorialStatus}
            dirty={isDirty}
            blockedReason={publishBlockedReason}
            onChanged={refreshEditorialStatus}
          />

          {/* WS-0.9: a SEPARATE question — "should the assistant know about this?".
              Publishing no longer puts a chapter in the knowledge graph, so without this
              control there is no way to get a draft into the KG, and no way to SEE what
              is in it. Both halves matter: an invisible knowledge graph is one the user
              can neither trust nor correct. */}
          {kgExclude !== undefined && (
            <KnowledgeIndexControl
              token={accessToken ?? ''}
              bookId={bookId}
              chapterId={chapterId}
              kgIndexedRevisionId={kgIndexedRevisionId}
              kgExclude={kgExclude}
              dirty={isDirty}
              onChanged={refreshEditorialStatus}
            />
          )}
        </div>
      </div>


      {/* ── Panel area ────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left panel */}
        {panels.left && (
          <div className={cn('relative flex flex-shrink-0 flex-col border-r bg-card', focusMode && 'hidden')} style={{ width: leftWidth }}>
            {/* Drag handle — resize by dragging the right edge. */}
            <div
              onMouseDown={startLeftResize}
              role="separator"
              aria-orientation="vertical"
              title={t('resize_panel', { defaultValue: 'Drag to resize' })}
              className="group absolute right-0 top-0 z-20 h-full w-1.5 translate-x-1/2 cursor-col-resize"
            >
              <div className="mx-auto h-full w-px bg-transparent transition-colors group-hover:bg-primary/50" />
            </div>
            {/* Tab bar */}
            <div className="flex border-b">
              <button
                onClick={() => setLeftTab('chapters')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                  leftTab === 'chapters' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <BookOpen className="h-3 w-3" />{t('tabs.chapters')}
              </button>
              <button
                onClick={() => setLeftTab('source')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                  leftTab === 'source' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <FileText className="h-3 w-3" />{t('tabs.original')}
              </button>
              <button
                onClick={() => setLeftTab('glossary')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                  leftTab === 'glossary' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <BookMarked className="h-3 w-3" />{t('tabs.glossary')}
                {glossaryEntities.length > 0 && (
                  <span className="text-[9px] px-1 py-px rounded-full bg-[var(--primary-muted)] text-[var(--primary)]">
                    {glossaryEntities.length}
                  </span>
                )}
              </button>
              <button
                onClick={() => setLeftTab('outline')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                  leftTab === 'outline' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <ListTree className="h-3 w-3" />{t('tabs.outline')}
              </button>
            </div>

            {/* ── Outline tab (T1.1a — committed-outline browser) ───────── */}
            {leftTab === 'outline' && (
              <OutlineTree
                bookId={bookId}
                token={accessToken}
                currentChapterId={chapterId}
                onNavigateChapter={navigateToChapter}
              />
            )}

            {/* ── Chapters tab ─────────────────────────────────────────── */}
            {leftTab === 'chapters' && (
              <div className="flex flex-1 flex-col overflow-hidden">
                <div className="flex-shrink-0 border-b px-3 py-2 text-[10px] text-muted-foreground">
                  {t('chapter_count', { count: allChapters.length })}
                </div>
                <div className="flex-1 overflow-y-auto">
                  {allChapters.length === 0 && (
                    <div className="space-y-1.5 p-3">
                      <Skeleton className="h-6 w-full" />
                      <Skeleton className="h-6 w-4/5" />
                      <Skeleton className="h-6 w-full" />
                    </div>
                  )}
                  {allChapters.map((ch, i) => (
                    <button
                      key={ch.chapter_id}
                      onClick={() => navigateToChapter(ch.chapter_id)}
                      className={cn(
                        'flex w-full items-start gap-2 border-b px-3 py-2.5 text-left transition-colors',
                        ch.chapter_id === chapterId
                          ? 'border-l-2 border-l-primary bg-primary/[0.07] text-primary'
                          : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
                      )}
                    >
                      <span className="mt-0.5 w-5 flex-shrink-0 text-right font-mono text-[10px] opacity-50">
                        {i + 1}
                      </span>
                      <span className="flex-1 text-xs leading-[1.5]">
                        {ch.title || ch.original_filename}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ── Original source tab ───────────────────────────────────── */}
            {leftTab === 'source' && (
              <div className="flex flex-1 flex-col overflow-hidden">
                <div className="flex-shrink-0 border-b px-3 py-2 text-[10px] text-muted-foreground">
                  {t('original_readonly')}
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  {originalLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-5/6" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-4/5" />
                      <Skeleton className="h-3 w-full" />
                    </div>
                  ) : originalContent ? (
                    <div className="space-y-0">
                      {originalContent.split(/\n\n+/).filter(Boolean).map((line, i) => (
                        <div key={i} className="flex gap-2 border-b border-border/30 px-3 py-1.5">
                          <span className="w-5 flex-shrink-0 text-right font-mono text-[10px] text-muted-foreground/50">{i + 1}</span>
                          <p className="text-xs leading-[1.75] text-foreground/70">{line}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] italic text-muted-foreground">
                      {t('no_original')}
                    </p>
                  )}
                </div>
              </div>
            )}

            {leftTab === 'glossary' && (
              <GlossaryPanel
                entities={glossaryEntities.map((e) => ({ ...e, count: 0 }))}
                glossaryEnabled={glossaryEnabled}
                onToggleEnabled={() => setGlossaryEnabledState((v) => !v)}
                onRefresh={loadGlossaryEntities}
                onEntityClick={() => {}}
              />
            )}
          </div>
        )}

        {/* Center — driven by the Workmode switch. Write AND Compose both keep the
            manuscript editor mounted in the centre (shared with the mobile Editor group
            via editorMain) — Compose's studio inserts generated prose into it via the
            editor ref, so unmounting the editor would silently drop those writes.
            Translate swaps the centre for the embedded translation workspace. */}
        {workmode !== 'translate' && editorMain}
        {workmode === 'translate' && (
          <ChapterTranslationsPanel
            key={`xl-${chapterId}`}
            bookId={bookId}
            chapterId={chapterId}
            showBreadcrumb={false}
            className="flex flex-1 overflow-hidden bg-background"
          />
        )}

        {/* Right panel companion. Write = history / AI chat tabs; Compose = the co-writer
            studio (promoted from the old right-panel tab into the Workmode). Translate has
            its own sidebar, so no companion there. */}
        {panels.right && workmode === 'compose' && (
          <div className={cn('relative flex flex-shrink-0 flex-col border-l bg-card', focusMode && 'hidden')} style={{ width: rightWidth }}>
            <div
              onMouseDown={startRightResize}
              role="separator"
              aria-orientation="vertical"
              title={t('resize_panel', { defaultValue: 'Drag to resize' })}
              className="group absolute left-0 top-0 z-20 h-full w-1.5 -translate-x-1/2 cursor-col-resize"
            >
              <div className="mx-auto h-full w-px bg-transparent transition-colors group-hover:bg-primary/50" />
            </div>
            <div className="min-h-0 flex-1 overflow-hidden">{studioMain}</div>
          </div>
        )}
        {panels.right && workmode === 'write' && (
          <div className={cn('relative flex flex-shrink-0 flex-col border-l bg-card', focusMode && 'hidden')} style={{ width: rightWidth }}>
            {/* Drag handle — resize the panel by dragging its left edge. */}
            <div
              onMouseDown={startRightResize}
              role="separator"
              aria-orientation="vertical"
              title={t('resize_panel', { defaultValue: 'Drag to resize' })}
              className="group absolute left-0 top-0 z-20 h-full w-1.5 -translate-x-1/2 cursor-col-resize"
            >
              <div className="mx-auto h-full w-px bg-transparent transition-colors group-hover:bg-primary/50" />
            </div>
            <div className="flex border-b">
              <button
                onClick={() => setRightTab('history')}
                className={cn('flex-1 px-3 py-2 text-xs font-medium', rightTab === 'history' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground')}
              >
                <Clock className="mr-1.5 inline h-3 w-3" />{t('history')}
              </button>
              <button
                onClick={() => setRightTab('ai')}
                className={cn('flex-1 px-3 py-2 text-xs font-medium', rightTab === 'ai' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground')}
              >
                <Sparkles className="mr-1.5 inline h-3 w-3" />{t('ai_chat')}
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              {rightTab === 'history' && historyMain}
              {/* ARCH-1 C5: the editor AI panel — the reusable <Chat> bound to
                  the book's knowledge project, with the current chapter
                  auto-attached as context (fired below when the tab opens).
                  key={bookId} forces a full remount when the user navigates to
                  a different book, so the per-book binding (session, project,
                  dialog state) resets instead of bleeding the previous book's
                  session into the new book (review-impl C5 #1). */}
              {rightTab === 'ai' && (
                <div className="flex h-full flex-col">
                  {/* Agent vs Compose mode. Agent = AI may call tools + edit the
                      doc (propose_edit). Compose = prose-only (no tools) so a
                      reasoning model drafts and you Apply via "Send to editor" —
                      reasoning models write better but stumble on tool-calling. */}
                  <div className="flex items-center gap-1.5 border-b px-2 py-1.5">
                    <span className="text-[10px] text-muted-foreground">{t('chat_mode', { defaultValue: 'Mode' })}</span>
                    <div className="ml-auto inline-flex rounded-md bg-secondary p-0.5 text-[10px] font-medium">
                      <button
                        type="button"
                        onClick={() => setComposeMode(false)}
                        title={t('mode_agent_hint', { defaultValue: 'AI can use tools and edit your document' })}
                        className={cn('flex items-center gap-1 rounded px-2 py-0.5 transition-colors', !composeMode ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground')}
                      >
                        <Sparkles className="h-2.5 w-2.5" />{t('mode_agent', { defaultValue: 'Agent' })}
                      </button>
                      <button
                        type="button"
                        onClick={() => setComposeMode(true)}
                        title={t('mode_compose_hint', { defaultValue: 'Prose only — AI writes, you Apply. Best for reasoning models.' })}
                        className={cn('flex items-center gap-1 rounded px-2 py-0.5 transition-colors', composeMode ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground')}
                      >
                        <Pen className="h-2.5 w-2.5" />{t('mode_compose', { defaultValue: 'Compose' })}
                      </button>
                    </div>
                  </div>
                  <Chat
                    key={bookId}
                    bookId={bookId}
                    editorContext={{ book_id: bookId, chapter_id: chapterId }}
                    composeMode={composeMode}
                    className="min-h-0 flex-1"
                  />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Status bar ───────────────────────────────────────────────────── */}
      <div className="flex h-6 flex-shrink-0 items-center justify-between border-t px-3 text-[10px] text-muted-foreground" style={{ background: 'rgba(24,20,18,0.6)' }}>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            {t('connected')}
          </span>
          {chapterLang && <span>{chapterLang}</span>}
          <span>{t('words', { n: wc.toLocaleString() })}</span>
        </div>
        <div className="flex items-center gap-3">
          <span><kbd className="rounded border border-border bg-secondary px-1 py-px font-mono text-[9px]">Ctrl+B</kbd> {t('left_panel')}</span>
          <span><kbd className="rounded border border-border bg-secondary px-1 py-px font-mono text-[9px]">Ctrl+J</kbd> {t('right_panel')}</span>
          <span><kbd className="rounded border border-border bg-secondary px-1 py-px font-mono text-[9px]">Ctrl+S</kbd> {t('save')}</span>
        </div>
      </div>
      </>
      )}

      {/* In-place discard confirm */}
      <ConfirmDialog
        open={showDiscardConfirm}
        onOpenChange={setShowDiscardConfirm}
        title={t('discard_confirm.title')}
        description={t('discard_confirm.desc')}
        confirmLabel={t('discard_confirm.confirm')}
        cancelLabel={t('discard_confirm.cancel')}
        variant="destructive"
        onConfirm={() => { discardChanges(); setShowDiscardConfirm(false); }}
      />

      {/* Navigation guard — shown when trying to leave with unsaved changes */}
      <UnsavedChangesDialog
        open={pendingNavigation !== null}
        onOpenChange={(open) => { if (!open) cancelNavigation(); }}
        onSave={async () => { await save(); confirmNavigation(); }}
        onDiscard={() => { discardChanges(); confirmNavigation(); }}
        saving={saving}
      />

      {/* Mode switch guard — shown when switching AI → Classic with dirty editor */}
      <UnsavedChangesDialog
        open={pendingModeSwitch !== null}
        onOpenChange={(open) => { if (!open) setPendingModeSwitch(null); }}
        onSave={async () => { await save(); setEditorMode(pendingModeSwitch!); setPendingModeSwitch(null); }}
        onDiscard={() => { discardChanges(); setEditorMode(pendingModeSwitch!); setPendingModeSwitch(null); }}
        saving={saving}
      />

      {/* Glossary hover tooltip */}
      {glossaryEnabled && <GlossaryTooltip bookId={bookId} />}

      {/* T5.3 — AI-provenance hover tag (reads the span's data-* attrs) */}
      {composeProjectId && <ProvenanceTag />}

      {/* Glossary [[ autocomplete */}
      {glossaryEnabled && (
        <GlossaryAutocomplete
          entities={glossaryEntities}
          editorEl={editorElRef.current}
          onInsertEntity={handleInsertEntity}
          onSelect={() => {}}
          onCreateNew={() => {}}
        />
      )}
    </div>
  );
}
