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
import type { OutlineNode } from '@/features/composition/types';
import { addTextSnapshots } from '@/lib/tiptap-utils';
import type { TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import { useStudioHost, useStudioBusSelector } from '../../host/StudioHostProvider';
import { _setManuscriptUnitBinding, emitManuscriptUnitChange, registerManuscriptUnitDocumentProvider } from './manuscriptUnitDocument';

const EMPTY_DOC: JSONContent = { type: 'doc', content: [] };

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
}

const INITIAL: ManuscriptUnitState = {
  chapterId: null, loadedBody: EMPTY_DOC, savedBody: EMPTY_DOC, workingBody: null,
  version: undefined, textContent: '', saveState: 'idle', error: null, scenes: [],
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
}

const ManuscriptUnitContext = createContext<ManuscriptUnitApi | null>(null);

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

  // #12 — the book's composition Work (scenes[] source). No Work → scenes stay [].
  // resolveWork returns an ENVELOPE {status, work, candidates} — same extraction as
  // useManuscriptTree (the live gate caught a bare `.project_id` read returning undefined).
  const work = useWorkResolution(bookId, accessToken);
  const projectId = useMemo(() => {
    const d = work.data;
    if (d?.status === 'found') return d.work?.project_id ?? null;
    if (d?.status === 'candidates') return d.candidates[0]?.project_id ?? null;
    return null;
  }, [work.data]);
  const projectIdRef = useRef<string | null>(projectId);
  projectIdRef.current = projectId;

  const loadScenes = useCallback(async (chapterId: string) => {
    const pid = projectIdRef.current;
    if (!accessToken || !pid) return;
    try {
      const r = await compositionApi.listChapterScenes(pid, chapterId, accessToken);
      setState((s) => (s.chapterId === chapterId ? { ...s, scenes: r.items } : s));
    } catch { /* scenes are additive metadata — a fetch failure must never break the editor */ }
  }, [accessToken]);

  const loadChapter = useCallback(async (chapterId: string, external: boolean) => {
    if (!accessToken) return;
    setState((s) => ({ ...s, chapterId, saveState: external ? s.saveState : 'loading', error: null }));
    try {
      const draft = await booksApi.getDraft(accessToken, bookId, chapterId);
      const body = (draft.body as JSONContent) ?? EMPTY_DOC;
      setState({
        chapterId, loadedBody: body, savedBody: body, workingBody: null,
        version: draft.draft_version, textContent: draft.text_content ?? '',
        saveState: 'idle', error: null, scenes: [],
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
    // addTextSnapshots is REQUIRED before persist (chapter_blocks trigger) — do it at the edit
    // boundary so `workingBody` is always save-ready.
    setState((s) => ({ ...s, workingBody: addTextSnapshots(doc), textContent: text, saveState: 'idle' }));
  }, []);

  const save = useCallback(async () => {
    const s = stateRef.current;
    if (!accessToken || !s.chapterId || !isDirtyState(s)) return;
    const body = s.workingBody ?? s.savedBody;
    setState((p) => ({ ...p, saveState: 'saving', error: null }));
    try {
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
      setState((p) => (p.chapterId !== s.chapterId ? p : {
        ...p, savedBody: body, workingBody: null, version: fresh.draft_version,
        textContent: fresh.text_content ?? p.textContent, saveState: 'saved',
      }));
    } catch (e) {
      setState((p) => ({ ...p, saveState: 'error', error: (e as Error).message }));
    }
  }, [accessToken, bookId]);
  const saveRef = useRef(save);
  saveRef.current = save;

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
  }), [state, openUnit, setBody, save, revert, reload, reloadScenes, isChapterDirty]);

  // #12 — bind the live api for the manuscript-unit DOCUMENT provider (S2 shared handle) and
  // register the provider once. Every api change (i.e. every state change) notifies handle views.
  useEffect(() => { registerManuscriptUnitDocumentProvider(); }, []);
  useEffect(() => {
    _setManuscriptUnitBinding({ api, token: accessToken, projectId });
    emitManuscriptUnitChange();
  }, [api, accessToken, projectId]);
  useEffect(() => () => { _setManuscriptUnitBinding(null); emitManuscriptUnitChange(); }, []);

  return <ManuscriptUnitContext.Provider value={api}>{children}</ManuscriptUnitContext.Provider>;
}

/** The Tier-4 manuscript unit. Returns null outside the provider (a panel may render before the
 * provider in tests) — callers guard. */
export function useManuscriptUnit(): ManuscriptUnitApi | null {
  return useContext(ManuscriptUnitContext);
}
