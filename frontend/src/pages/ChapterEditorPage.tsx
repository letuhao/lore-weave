import { FormEvent, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { m02Api } from '@/m02/api';
import { LexicalComposer } from '@lexical/react/LexicalComposer';
import { PlainTextPlugin } from '@lexical/react/LexicalPlainTextPlugin';
import { ContentEditable } from '@lexical/react/LexicalContentEditable';
import { HistoryPlugin } from '@lexical/react/LexicalHistoryPlugin';
import { OnChangePlugin } from '@lexical/react/LexicalOnChangePlugin';
import { $createParagraphNode, $createTextNode, $getRoot, EditorState } from 'lexical';
import { PaginationBar } from '@/components/m02/PaginationBar';

export function ChapterEditorPage() {
  const { accessToken } = useAuth();
  const { bookId = '', chapterId = '' } = useParams();
  const [body, setBody] = useState('');
  const [editorKey, setEditorKey] = useState(0);
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [revisions, setRevisions] = useState<Array<{ revision_id: string; created_at: string; message?: string }>>([]);
  const [revisionTotal, setRevisionTotal] = useState(0);
  const [revisionLimit] = useState(10);
  const [revisionOffset, setRevisionOffset] = useState(0);
  const [preview, setPreview] = useState<{ revision_id: string; message?: string; body: string } | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken || !bookId || !chapterId) return;
    try {
      const d = await m02Api.getDraft(accessToken, bookId, chapterId);
      setBody(d.body);
      setEditorKey((v) => v + 1);
      setVersion(d.draft_version);
      const rev = await m02Api.listRevisions(accessToken, bookId, chapterId, {
        limit: revisionLimit,
        offset: revisionOffset,
      });
      setRevisions(rev.items);
      setRevisionTotal(rev.total);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken, bookId, chapterId, revisionLimit, revisionOffset]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken || !bookId || !chapterId) return;
    try {
      await m02Api.patchDraft(accessToken, bookId, chapterId, {
        body,
        commit_message: message || undefined,
        expected_draft_version: version,
      });
      setMessage('');
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const restore = async (revisionId: string) => {
    if (!accessToken || !bookId || !chapterId) return;
    await m02Api.restoreRevision(accessToken, bookId, chapterId, revisionId);
    setPreview(null);
    await load();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Chapter editor</h1>
      <form onSubmit={save} className="space-y-2">
        <LexicalPlainEditor key={editorKey} initialValue={body} onChange={setBody} />
        <textarea className="sr-only" value={body} readOnly aria-hidden />
        <input
          className="w-full rounded border px-2 py-1"
          placeholder="Commit message (optional)"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <button className="rounded bg-primary px-3 py-1 text-primary-foreground">Save draft</button>
      </form>
      <div className="space-y-2">
        <h2 className="font-medium">Revision history</h2>
        <ul className="space-y-2 text-sm">
          {revisions.map((r) => (
            <li key={r.revision_id} className="flex items-center justify-between rounded border p-2">
              <span>
                {new Date(r.created_at).toLocaleString()} {r.message ? `- ${r.message}` : ''}
              </span>
              <div className="flex items-center gap-3">
                <button
                  className="underline"
                  onClick={async () => {
                    if (!accessToken || !bookId || !chapterId) return;
                    const detail = await m02Api.getRevision(accessToken, bookId, chapterId, r.revision_id);
                    setPreview({
                      revision_id: r.revision_id,
                      message: detail.message,
                      body: detail.body,
                    });
                  }}
                >
                  Preview
                </button>
                <button className="underline" onClick={() => void restore(r.revision_id)}>
                  Restore
                </button>
              </div>
            </li>
          ))}
        </ul>
        <PaginationBar total={revisionTotal} limit={revisionLimit} offset={revisionOffset} onChange={setRevisionOffset} />
      </div>
      {preview && (
        <div className="space-y-2 rounded border p-3 text-sm">
          <h3 className="font-medium">Preview revision {preview.revision_id}</h3>
          <p className="text-xs text-muted-foreground">{preview.message || 'No message'}</p>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-muted p-2">{preview.body}</pre>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}

function LexicalPlainEditor({ initialValue, onChange }: { initialValue: string; onChange: (value: string) => void }) {
  return (
    <LexicalComposer
      initialConfig={{
        namespace: 'm02-chapter-editor',
        onError: (err) => {
          throw err;
        },
        editorState: () => {
          const root = $getRoot();
          root.clear();
          const paragraph = $createParagraphNode();
          paragraph.append($createTextNode(initialValue || ''));
          root.append(paragraph);
        },
      }}
    >
      <div className="rounded border">
        <PlainTextPlugin
          contentEditable={<ContentEditable className="min-h-[280px] whitespace-pre-wrap px-3 py-2 text-sm outline-none" />}
          placeholder={<p className="px-3 py-2 text-sm text-muted-foreground">Write chapter draft here…</p>}
          ErrorBoundary={() => <></>}
        />
        <HistoryPlugin />
        <OnChangePlugin
          onChange={(editorState: EditorState) => {
            editorState.read(() => {
              onChange($getRoot().getTextContent());
            });
          }}
        />
      </div>
    </LexicalComposer>
  );
}
