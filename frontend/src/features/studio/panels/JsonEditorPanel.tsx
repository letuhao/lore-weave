// #12 S4/S5 · the generic json-editor dock panel — ONE singleton panel that retargets via
// dock params {docType, resourceId} (R3, VS Code settings-tab UX). A THIN VIEW over the shared
// DocumentHandle (S2): CM6 + JSON(-schema) tooling renders the doc; edits flow handle.update();
// ⌘S saves THROUGH the domain API (S3). hiddenFromPalette (R4) — opened by "Open as JSON"
// affordances and the F1 params seam, never the agent enum (this cycle).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { IDockviewPanelProps } from 'dockview-react';
import CodeMirror from '@uiw/react-codemirror';
import { json } from '@codemirror/lang-json';
import { jsonSchema } from 'codemirror-json-schema';
import { getJsonDocumentProvider } from '../documents/registry';
import { useJsonDocument } from '../documents/useJsonDocument';
import { useStudioPanel } from './useStudioPanel';

interface JsonEditorParams { docType?: unknown; resourceId?: unknown }

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);

export function JsonEditorPanel(props: IDockviewPanelProps) {
  useStudioPanel('json-editor', props.api);
  const { t } = useTranslation('studio');

  // Retarget on EVERY updateParameters (R3 singleton; same lesson as SettingsPanel — the
  // event fires on every call, so a repeat open of the same doc still lands).
  const p = (props.params ?? {}) as JsonEditorParams;
  const [target, setTarget] = useState<{ docType: string | null; resourceId: string | null }>({
    docType: str(p.docType), resourceId: str(p.resourceId),
  });
  useEffect(() => {
    const d = props.api.onDidParametersChange?.((next: Record<string, unknown> | undefined) => {
      const np = (next ?? {}) as JsonEditorParams;
      setTarget({ docType: str(np.docType), resourceId: str(np.resourceId) });
    });
    return () => d?.dispose?.();
  }, [props.api]);

  const { handle, snapshot, openError } = useJsonDocument(target.docType, target.resourceId);
  const provider = target.docType ? getJsonDocumentProvider(target.docType) : undefined;

  // The CM6 text buffer: re-seeded when the underlying doc identity changes (load/save/revert/
  // external reload), NOT on every keystroke (text is the source while typing).
  const [text, setText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const docJson = useMemo(
    () => (snapshot && snapshot.doc !== null ? JSON.stringify(snapshot.doc, null, 2) : ''),
    [snapshot?.doc], // eslint-disable-line react-hooks/exhaustive-deps
  );
  useEffect(() => {
    // External identity change → reseed buffer unless the user has local edits pending
    // (dirty ⇒ the buffer IS the working copy; never clobber it — G7 spirit).
    if (!snapshot?.dirty) { setText(docJson); setParseError(null); }
  }, [docJson]); // eslint-disable-line react-hooks/exhaustive-deps

  const onChange = useCallback((value: string) => {
    setText(value);
    try {
      const parsed = JSON.parse(value);
      setParseError(null);
      handle?.update(parsed);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : 'invalid JSON');
      // invalid JSON stays local to the buffer — the handle keeps the last parseable doc
    }
  }, [handle]);

  const onFormat = useCallback(() => {
    try { setText(JSON.stringify(JSON.parse(text), null, 2)); setParseError(null); }
    catch { /* leave as-is; parseError already shown */ }
  }, [text]);

  const onSave = useCallback(() => {
    if (parseError) return;
    void handle?.save();
  }, [handle, parseError]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); onSave(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onSave]);

  const extensions = useMemo(() => {
    const schema = provider?.schema;
    return schema ? [json(), jsonSchema(schema as never)] : [json()];
  }, [provider]);

  if (!target.docType || !target.resourceId) {
    return (
      <div data-testid="studio-json-editor" className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground">
        {t('jsonEditor.empty', { defaultValue: 'Open a resource as JSON from its panel ("Open as JSON").' })}
      </div>
    );
  }
  if (openError) {
    return (
      <div data-testid="studio-json-editor" className="flex h-full items-center justify-center p-6 text-center text-xs text-destructive">
        {openError}
      </div>
    );
  }

  const status = snapshot?.status ?? 'loading';
  const dirty = snapshot?.dirty ?? false;

  return (
    <div data-testid="studio-json-editor" className="flex h-full min-h-0 flex-col">
      <div className="flex h-7 flex-shrink-0 items-center gap-2 border-b px-3 text-[11px] text-muted-foreground">
        <span className="font-mono text-[10px]">{target.docType}</span>
        <span
          data-testid="json-editor-status"
          className={
            parseError || status === 'error' || status === 'conflict'
              ? 'text-destructive'
              : dirty ? 'text-warning' : 'text-muted-foreground/60'
          }
        >
          {parseError
            ? t('jsonEditor.invalid', { defaultValue: 'invalid JSON' })
            : status === 'conflict'
              ? t('jsonEditor.conflict', { defaultValue: `conflict: ${snapshot?.detail ?? ''}`, part: snapshot?.detail })
              : status === 'error'
                ? (snapshot?.detail ?? 'error')
                : dirty ? t('editor.unsaved', { defaultValue: '● unsaved' }) : status}
        </span>
        <div className="flex-1" />
        <button type="button" data-testid="json-editor-format" onClick={onFormat}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground">
          {t('jsonEditor.format', { defaultValue: 'Format' })}
        </button>
        <button type="button" data-testid="json-editor-revert" onClick={() => handle?.revert()}
          disabled={!dirty}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-40">
          {t('jsonEditor.revert', { defaultValue: 'Revert' })}
        </button>
        <button type="button" data-testid="json-editor-save" onClick={onSave}
          disabled={!dirty || !!parseError || status === 'saving'}
          className="rounded px-1.5 py-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-40">
          {t('editor.save', { defaultValue: 'Save' })} <span className="font-mono text-[10px]">⌘S</span>
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto" data-testid="json-editor-cm">
        <CodeMirror
          value={text}
          height="100%"
          extensions={extensions}
          onChange={onChange}
          basicSetup={{ lineNumbers: true, foldGutter: true }}
        />
      </div>
    </div>
  );
}
