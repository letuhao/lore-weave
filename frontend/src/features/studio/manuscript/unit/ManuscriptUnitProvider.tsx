// #04 · Tier-4 domain hoist (the REFERENCE every stateful studio panel copies — #08 §Tier 4).
//
// Owns the ONE active chapter's editable state ABOVE dockview, so a dock float / close / split
// never drops in-flight edits (D4). The editor panels (Rich #04a / Raw #04b) are THIN VIEWS that
// read/write this hoist — never a separate fetch cache (M3). Reuses the whole manuscript I/O stack
// AS-IS (booksApi.getDraft/patchDraft, addTextSnapshots) — no fork.
//
// Three body buffers, deliberately distinct (avoids the cursor-jump / clobber traps the survey
// flagged):
//   • loadedBody  — the TiptapEditor `content` prop; changes ONLY on an external load (openUnit /
//                   reload), so a user-save never resets the editor under the cursor.
//   • workingBody — the latest onUpdate (what the user is typing). null until the first edit.
//   • savedBody   — last-persisted; the dirty compare + the save source.
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode,
} from 'react';
import type { JSONContent } from '@tiptap/react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { compositionApi } from '@/features/composition/api';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useActiveWorkId } from '@/features/composition/hooks/useActiveWork';
import { resolveActiveWork } from '@/features/composition/workSelect';
import { useReportProgress, useEnsureBaseline } from '@/features/composition/hooks/useProgress';
import type { OutlineNode } from '@/features/composition/types';
import { addTextSnapshots, extractText } from '@/lib/tiptap-utils';
import type { TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import type { ProvenanceAttrs } from '@/components/editor/ProvenanceMark';
import { useStudioHost, useStudioBusSelector } from '../../host/StudioHostProvider';
import { _setManuscriptUnitBinding, emitManuscriptUnitChange, registerManuscriptUnitDocumentProvider } from './manuscriptUnitDocument';

const EMPTY_DOC: JSONContent = { type: 'doc', content: [] };

// #16 2.10 — progress-reporting word count (mirrors ChapterEditorPage.tsx's own helper verbatim).
function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

// #16 2.9 — auto-save debounce window (mirrors legacy's 5-minute idle-save).
const AUTO_SAVE_DEBOUNCE_MS = 300_000;

export type SaveState = 'idle' | 'loading' | 'saving' | 'saved' | 'conflict' | 'error';

export interface ManuscriptUnitState {
  chapterId: string | null;
  loadedBody: JSONContent;            // editor content prop (external-load only)
  savedBody: JSONContent;             // last-persisted
  workingBody: JSONContent | null;    // latest edit (null = untouched since load/save)
  version: number | undefined;        // draft_version for optimistic concurrency
  textContent: string;
  saveState: SaveState;
  error: string | null;
  /** #12 cycle-1 — the chapter's composition scene nodes (outline metadata, D17). Loaded with
   * the unit when the book has a Work; [] otherwise. A separate buffer from the body (R6). */
  scenes: OutlineNode[];
  /** #12 M-G — the outline CHAPTER node scenes parent under (the rail's Create target).
   * null until scenes load / when the chapter was never outlined. */
  sceneChapterNodeId: string | null;
  /** D-S5-DERIVATIVE-MANUSCRIPT-FORK — when the active Work is a dị bản, this chapter's draft is
   * WORK-SCOPED (isolated from canon). `forked` = it has its own row (vs still inheriting canon).
   * On the canonical Work both are false and the draft is the shared book manuscript. */
  isDerivative: boolean;
  forked: boolean;
}

const INITIAL: ManuscriptUnitState = {
  chapterId: null, loadedBody: EMPTY_DOC, savedBody: EMPTY_DOC, workingBody: null,
  version: undefined, textContent: '', saveState: 'idle', error: null, scenes: [],
  sceneChapterNodeId: null, isDerivative: false, forked: false,
};

export interface ManuscriptUnitApi {
  state: ManuscriptUnitState;
  isDirty: boolean;
  /** Shared imperative editor handle (Rich panel wires it; used for editorBridge / Lane C). */
  editorRef: React.MutableRefObject<TiptapEditorHandle | null>;
  openUnit: (chapterId: string) => Promise<void>;
  setBody: (doc: JSONContent, text: string) => void;
  save: () => Promise<void>;
  revert: () => void;
  reload: () => Promise<void>;
  /** Re-fetch ONLY the scenes[] buffer (Lane-B after a scene-metadata MCP write — never
   * touches the body buffers, so it is dirty-safe by construction, R6). */
  reloadScenes: () => Promise<void>;
  /** G7 — is THIS chapter's hoist dirty? The reconciler asks before a blind reload. */
  isChapterDirty: (chapterId: string) => boolean;
  /** #12 M-F — scroll+cursor to the heading anchored to the scene. false = not anchored
   * (or no live editor) — the caller surfaces the ⚓ hint, never a silent no-op. */
  jumpToScene: (sceneId: string) => boolean;
  /** #12 M-F backfill — anchor headings↔scenes by unique title match (explicit action;
   * dirties the doc → the user saves). null = no live editor. */
  anchorScenes: () => { anchored: number; unmatched: number; changed: boolean } | null;
  /** #16 P1 (Lane C — spec 09) — the hoist-owned entry point for an AI-proposed prose write.
   * Delegates to the same live Tiptap handle `editorRef` already exposes, so the existing
   * onUpdate→setBody wiring is unchanged (this is not a new write path, just a named one this
   * hoist owns instead of a caller reaching into a raw ref via the global editorBridge
   * singleton) — exists so future hoist-level bookkeeping (Checkpoints, #16 Phase 1) has ONE
   * chokepoint for "an AI wrote into this chapter" instead of every consumer re-deriving it.
   * false = no live editor (chapter not mounted / view-only surface). */
  applyProposedEdit: (params: {
    operation: 'insert_at_cursor' | 'replace_selection';
    text: string;
    provenance?: ProvenanceAttrs;
  }) => boolean;
}

const ManuscriptUnitContext = createContext<ManuscriptUnitApi | null>(null);

/** The STABLE identity slice of the unit — changes only when the active chapter or the book's
 * composition project changes, never per keystroke. Split from ManuscriptUnitApi (which carries
 * the volatile body buffers) so low-frequency consumers — the Compose panel's studio_context
 * position pointer (CTX-1) — don't re-render the whole chat subtree on every edit. */
export interface ManuscriptUnitMeta {
  /** The book's composition/knowledge project id (null until the Work resolves / none marked). */
  projectId: string | null;
  activeChapterId: string | null;
}

const ManuscriptUnitMetaContext = createContext<ManuscriptUnitMeta | null>(null);

function isDirtyState(s: ManuscriptUnitState): boolean {
  return s.workingBody != null && JSON.stringify(s.workingBody) !== JSON.stringify(s.savedBody);
}

export function ManuscriptUnitProvider({ bookId, children }: { bookId: string; children: ReactNode }) {
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const [state, setState] = useState<ManuscriptUnitState>(INITIAL);
  const editorRef = useRef<TiptapEditorHandle | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  // #16 2.9 — pending auto-save timer (cleared by an explicit save so it never double-fires).
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // #16 2.10 — the on-disk word count at the moment a chapter loads (the "baseline" so today's
  // first progress snapshot counts only words written THIS session, not pre-existing content).
  const loadedWordCountRef = useRef<number | null>(null);
  // D-S5 — the loaded chapter TEXT + whether a REAL user edit (text changed) has happened since.
  // Distinguishes a keystroke from Tiptap's mount-normalize (which re-emits the same text under a
  // normalized structure); the fork-identity reload uses this instead of the structural dirty flag.
  const loadedTextRef = useRef<string>('');
  const userEditedRef = useRef<boolean>(false);

  // #12 — the book's composition Work (scenes[] source). No Work → scenes stay [].
  // resolveWork returns an ENVELOPE {status, work, candidates} — same extraction as
  // useManuscriptTree (the live gate caught a bare `.project_id` read returning undefined).
  const work = useWorkResolution(bookId, accessToken);
  const { data: activeWorkId } = useActiveWorkId(bookId, accessToken);
  // EC-3d: the ACTIVE Work's project (per-book pref, else canonical) — NOT candidates[0].
  const activeWork = useMemo(
    () => resolveActiveWork(work.data, activeWorkId),
    [work.data, activeWorkId],
  );
  const projectId = activeWork?.project_id ?? null;
  // D-S5-DERIVATIVE-MANUSCRIPT-FORK — a dị bản (source_work_id set) has its OWN manuscript per
  // chapter; load/save route to the composition work-draft store, not the shared book draft.
  const isDerivative = !!activeWork?.source_work_id;
  const projectIdRef = useRef<string | null>(projectId);
  projectIdRef.current = projectId;
  const isDerivativeRef = useRef<boolean>(isDerivative);
  isDerivativeRef.current = isDerivative;
  // The active-work pref: `undefined` = still loading, `null` = unset (canonical), else the project.
  // loadChapter must NOT run while it is `undefined` (it would load the WRONG draft source and need a
  // reload — the fork first-paint race). We defer the load until it resolves (see loadChapter + the
  // resolution effect below).
  const activeWorkIdRef = useRef<string | null | undefined>(activeWorkId);
  activeWorkIdRef.current = activeWorkId;
  const pendingChapterRef = useRef<string | null>(null);

  const loadScenes = useCallback(async (chapterId: string) => {
    const pid = projectIdRef.current;
    if (!accessToken || !pid) return;
    try {
      const r = await compositionApi.listChapterScenes(pid, chapterId, accessToken);
      setState((s) => (s.chapterId === chapterId
        ? { ...s, scenes: r.items, sceneChapterNodeId: r.chapter_node_id ?? null }
        : s));
    } catch { /* scenes are additive metadata — a fetch failure must never break the editor */ }
  }, [accessToken]);

  const loadChapter = useCallback(async (chapterId: string, external: boolean) => {
    if (!accessToken) return;
    // D-S5 — defer until the active-work pref resolves so the FIRST load already uses the correct draft
    // source (canon vs the dị bản's fork). The resolution effect re-invokes this once it settles. This
    // eliminates the load-canon-then-reload race (and its unreliable false-dirty guard).
    if (activeWorkIdRef.current === undefined) {
      pendingChapterRef.current = chapterId;
      setState((s) => ({ ...s, chapterId, saveState: 'loading', error: null }));
      return;
    }
    pendingChapterRef.current = null;
    setState((s) => ({ ...s, chapterId, saveState: external ? s.saveState : 'loading', error: null }));
    try {
      // D-S5 fork: on a dị bản read the WORK-scoped draft (fork if any, else read-through canon at
      // version 0); on the canonical Work read the shared book draft. `version` is the concurrency
      // token either way (book draft_version, or the fork's — 0 means "inherited, not forked yet").
      const derivative = isDerivativeRef.current;
      const pid = projectIdRef.current;
      let body: JSONContent; let version: number | undefined; let textContent: string; let forked = false;
      if (derivative && pid) {
        const wd = await compositionApi.getWorkChapterDraft(pid, chapterId, accessToken);
        body = (wd.body as JSONContent) ?? EMPTY_DOC;
        version = wd.draft_version;
        forked = wd.forked;
        textContent = extractText(body);
      } else {
        const draft = await booksApi.getDraft(accessToken, bookId, chapterId);
        body = (draft.body as JSONContent) ?? EMPTY_DOC;
        version = draft.draft_version;
        // Server text_content can be empty (blocks projection) and an already-normalized
        // body fires NO mount onUpdate to backfill it — derive from the body (M-H word count).
        textContent = draft.text_content || extractText(body);
      }
      loadedWordCountRef.current = wordCount(textContent);
      // Track the loaded TEXT so a mount-normalize onUpdate (same text, Tiptap-normalized structure)
      // is not mistaken for a user edit by the fork-identity reload below (isDirtyState false-fires on
      // the structural diff; the TEXT is the real-edit signal).
      loadedTextRef.current = textContent;
      userEditedRef.current = false;
      setState({
        chapterId, loadedBody: body, savedBody: body, workingBody: null,
        version, textContent,
        saveState: 'idle', error: null, scenes: [], sceneChapterNodeId: null,
        isDerivative: derivative, forked,
      });
      void loadScenes(chapterId);
    } catch (e) {
      setState((s) => ({ ...s, chapterId, saveState: 'error', error: (e as Error).message }));
    }
  }, [accessToken, bookId, loadScenes]);

  // Late Work resolution (the work query lands AFTER the first chapter opened) → backfill scenes.
  useEffect(() => {
    const chapterId = stateRef.current.chapterId;
    if (projectId && chapterId && stateRef.current.scenes.length === 0) void loadScenes(chapterId);
  }, [projectId, loadScenes]);

  // D-S5 — once the active-work pref RESOLVES (undefined→value|null), run any chapter load that was
  // deferred (loadChapter above) so the first paint loads the correct draft source without a reload.
  useEffect(() => {
    if (activeWorkId !== undefined && pendingChapterRef.current) {
      const cid = pendingChapterRef.current;
      pendingChapterRef.current = null;
      void loadChapter(cid, false);
    }
  }, [activeWorkId, loadChapter]);

  // D-S5-DERIVATIVE-MANUSCRIPT-FORK — a DELIBERATE "Switch to" a dị bản (or back to canon) with a
  // chapter already open must swap the manuscript to that Work's draft. Skips a real unsaved edit
  // (never clobbers) and only fires when the fork identity actually flips. The first-paint race is
  // handled by the defer above, not here — so this only sees genuine value→value switches.
  const forkIdentityRef = useRef<string>('');
  useEffect(() => {
    const identity = isDerivative ? `deriv:${projectId ?? ''}` : 'canon';
    const chapterId = stateRef.current.chapterId;
    if (!chapterId) { forkIdentityRef.current = identity; return; }
    if (forkIdentityRef.current === identity) return;
    forkIdentityRef.current = identity;
    if (userEditedRef.current) return;   // preserve a genuine unsaved edit on a deliberate switch
    void loadChapter(chapterId, false);
  }, [isDerivative, projectId, loadChapter]);

  // Open a chapter into the unit. Dirty-flush (S7/M2): a pending edit is SAVED before switching so
  // navigation never loses work (a prompt variant is a later UX polish).
  const openUnit = useCallback(async (chapterId: string) => {
    const cur = stateRef.current;
    if (cur.chapterId === chapterId) return;
    if (isDirtyState(cur)) {
      try { await saveRef.current(); } catch { /* keep going — best-effort flush */ }
    }
    await loadChapter(chapterId, false);
  }, [loadChapter]);

  const setBody = useCallback((doc: JSONContent, text: string) => {
    // A REAL edit changes the text; a mount-normalize re-emits the loaded text. Only the former
    // should block the fork-identity reload (D-S5).
    if (text !== loadedTextRef.current) userEditedRef.current = true;
    // addTextSnapshots is REQUIRED before persist (chapter_blocks trigger) — do it at the edit
    // boundary so `workingBody` is always save-ready.
    setState((s) => {
      const snap = addTextSnapshots(doc);
      // M-I — Tiptap's mount-normalize fires ONE onUpdate whose content equals what we just
      // loaded; without this guard every open marked the unit dirty (and forced the
      // json-editor's empty-buffer workaround). Only the FIRST update is compared (workingBody
      // null) — a real edit path never pays the stringify.
      if (s.workingBody == null && JSON.stringify(snap) === JSON.stringify(s.savedBody)) {
        return s.textContent === text ? s : { ...s, textContent: text };
      }
      return { ...s, workingBody: snap, textContent: text, saveState: 'idle' };
    });
  }, []);

  const reportProgress = useReportProgress(projectId ?? undefined, accessToken);
  const ensureBaseline = useEnsureBaseline(projectId ?? undefined, accessToken);

  const save = useCallback(async () => {
    // #16 2.9 — a manual/keyboard save cancels any pending auto-save (mirrors legacy).
    if (autoSaveTimerRef.current) { clearTimeout(autoSaveTimerRef.current); autoSaveTimerRef.current = null; }
    const s = stateRef.current;
    if (!accessToken || !s.chapterId || !isDirtyState(s)) return;
    const body = s.workingBody ?? s.savedBody;
    setState((p) => ({ ...p, saveState: 'saving', error: null }));
    try {
      const derivative = isDerivativeRef.current;
      const pid = projectIdRef.current;
      let freshVersion: number | undefined; let freshText: string; let freshForked = s.forked;
      if (derivative && pid) {
        // D-S5 fork: write the WORK-scoped draft (expected_version 0 forks; >=1 OCC-bumps). Canon
        // is NEVER touched. On a stale token (fork raced / concurrent edit), refetch + retry once.
        let saved: { draft_version: number };
        try {
          saved = await compositionApi.patchWorkChapterDraft(pid, s.chapterId, {
            body, expected_version: s.version ?? 0,
          }, accessToken);
        } catch (e) {
          const err = e as { code?: string; status?: number };
          if (err.status === 412 || err.status === 409) {
            const cur = await compositionApi.getWorkChapterDraft(pid, s.chapterId, accessToken);
            saved = await compositionApi.patchWorkChapterDraft(pid, s.chapterId, {
              body, expected_version: cur.draft_version,
            }, accessToken);
          } else { throw e; }
        }
        freshVersion = saved.draft_version;
        freshText = extractText(body);
        freshForked = true;  // any successful work-draft write means this chapter is now forked
      } else {
        try {
          await booksApi.patchDraft(accessToken, bookId, s.chapterId, {
            body, body_format: 'json', expected_draft_version: s.version,
          });
        } catch (e) {
          const err = e as { code?: string; status?: number };
          if (err.code === 'CHAPTER_DRAFT_CONFLICT' || err.status === 409) {
            // Last-write-wins fallback (mirrors ChapterEditorPage). Then re-sync the version below.
            await booksApi.patchDraft(accessToken, bookId, s.chapterId, { body, body_format: 'json' });
          } else { throw e; }
        }
        // Re-fetch to pick up the new draft_version + text snapshot (patchDraft returns void).
        const fresh = await booksApi.getDraft(accessToken, bookId, s.chapterId);
        freshVersion = fresh.draft_version;
        freshText = fresh.text_content ?? extractText(body);
      }
      loadedTextRef.current = freshText;
      userEditedRef.current = false;   // persisted — no unsaved user edit remains
      setState((p) => (p.chapterId !== s.chapterId ? p : {
        ...p, savedBody: body, workingBody: null, version: freshVersion,
        textContent: freshText, saveState: 'saved', forked: freshForked,
      }));
      // #16 2.10 — best-effort; NEVER disrupts the save it rides on (the hook swallows failures).
      reportProgress(s.chapterId, wordCount(freshText));
    } catch (e) {
      setState((p) => ({ ...p, saveState: 'error', error: (e as Error).message }));
    }
  }, [accessToken, bookId, reportProgress]);
  const saveRef = useRef(save);
  saveRef.current = save;

  // #16 2.9 — auto-save: a debounced 5-minute idle-save while dirty (mirrors legacy's
  // ChapterEditorPage timer). Resets on every edit (any state change while dirty); a manual
  // save (above) or the doc going clean cancels the pending timer.
  useEffect(() => {
    if (!isDirtyState(state)) return;
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(() => { void saveRef.current(); }, AUTO_SAVE_DEBOUNCE_MS);
    return () => {
      if (autoSaveTimerRef.current) { clearTimeout(autoSaveTimerRef.current); autoSaveTimerRef.current = null; }
    };
  }, [state]);

  // #16 2.10 — seed the server's per-chapter baseline once per chapter load (server is
  // insert-once, so a re-fire here is a safe no-op). Waits on projectId in case the Work
  // resolves AFTER the first chapter opens (same late-resolution shape as the scenes backfill).
  useEffect(() => {
    if (!projectId || !state.chapterId || loadedWordCountRef.current == null) return;
    ensureBaseline(state.chapterId, loadedWordCountRef.current);
  }, [projectId, state.chapterId, ensureBaseline]);

  const revert = useCallback(() => {
    setState((s) => ({ ...s, loadedBody: s.savedBody, workingBody: null, saveState: 'idle' }));
  }, []);

  // External reload (Lane B reconciler after an agent MCP write). Re-pushes loadedBody → the editor
  // resets to the fresh server content. The CALLER guards on isChapterDirty (G7) — never reload
  // over unsaved edits.
  const reload = useCallback(async () => {
    const s = stateRef.current;
    if (s.chapterId) await loadChapter(s.chapterId, true);
  }, [loadChapter]);

  const reloadScenes = useCallback(async () => {
    const chapterId = stateRef.current.chapterId;
    if (chapterId) await loadScenes(chapterId);
  }, [loadScenes]);

  const isChapterDirty = useCallback(
    (chapterId: string) => stateRef.current.chapterId === chapterId && isDirtyState(stateRef.current),
    [],
  );

  // #12 M-F — scene anchoring, thin wrappers over the live editor handle. The rich
  // panel wires editorRef; with no live editor (JSON-only view) jump=false / anchor=null.
  const jumpToScene = useCallback(
    (sceneId: string) => editorRef.current?.jumpToScene(sceneId) ?? false,
    [],
  );
  const anchorScenes = useCallback(() => {
    const handle = editorRef.current;
    if (!handle) return null;
    return handle.applySceneAnchors(
      stateRef.current.scenes.map((s) => ({ id: s.id, title: s.title })),
    );
  }, []);

  // #16 P1 — Lane C hoist action (see ManuscriptUnitApi doc comment). Thin wrapper over the
  // same editorRef the panel already renders; the write itself is unchanged (still a Tiptap
  // command that fires onUpdate → setBody), only the call site moves from a raw ref lookup to
  // a named hoist method.
  const applyProposedEdit = useCallback((params: {
    operation: 'insert_at_cursor' | 'replace_selection';
    text: string;
    provenance?: ProvenanceAttrs;
  }) => {
    const handle = editorRef.current;
    if (!handle) return false;
    return params.operation === 'replace_selection'
      ? handle.replaceSelection(params.text, params.provenance)
      : handle.insertAtCursor(params.text, params.provenance);
  }, []);

  // Bus-driven open (decoupled): host.focusManuscriptUnit publishes {chapter} → the hoist loads it.
  // The navigator / Quick Open / agent all drive the editor through this one seam.
  const activeChapterId = useStudioBusSelector((snap) => snap.activeChapterId);
  useEffect(() => {
    if (activeChapterId && activeChapterId !== stateRef.current.chapterId) {
      void openUnit(activeChapterId);
    }
  }, [activeChapterId, openUnit]);

  // Publish a light unit context slice for chat/reconciler (they read activeChapterId off the bus).
  // The host bus already carries it (focusManuscriptUnit publishes) — nothing extra to emit here.
  void host;

  const api = useMemo<ManuscriptUnitApi>(() => ({
    state, isDirty: isDirtyState(state), editorRef,
    openUnit, setBody, save, revert, reload, reloadScenes, isChapterDirty,
    jumpToScene, anchorScenes, applyProposedEdit,
  }), [
    state, openUnit, setBody, save, revert, reload, reloadScenes, isChapterDirty,
    jumpToScene, anchorScenes, applyProposedEdit,
  ]);

  // #12 — bind the live api for the manuscript-unit DOCUMENT provider (S2 shared handle) and
  // register the provider once. Every api change (i.e. every state change) notifies handle views.
  useEffect(() => { registerManuscriptUnitDocumentProvider(); }, []);
  useEffect(() => {
    _setManuscriptUnitBinding({ api, token: accessToken, projectId });
    emitManuscriptUnitChange();
  }, [api, accessToken, projectId]);
  useEffect(() => () => { _setManuscriptUnitBinding(null); emitManuscriptUnitChange(); }, []);

  const meta = useMemo<ManuscriptUnitMeta>(
    () => ({ projectId, activeChapterId: state.chapterId }),
    [projectId, state.chapterId],
  );

  return (
    <ManuscriptUnitMetaContext.Provider value={meta}>
      <ManuscriptUnitContext.Provider value={api}>{children}</ManuscriptUnitContext.Provider>
    </ManuscriptUnitMetaContext.Provider>
  );
}

/** The Tier-4 manuscript unit. Returns null outside the provider (a panel may render before the
 * provider in tests) — callers guard. */
export function useManuscriptUnit(): ManuscriptUnitApi | null {
  return useContext(ManuscriptUnitContext);
}

/** The stable identity slice (projectId + activeChapterId) — safe for low-frequency consumers. */
export function useManuscriptUnitMeta(): ManuscriptUnitMeta | null {
  return useContext(ManuscriptUnitMetaContext);
}
