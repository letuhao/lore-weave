import { FormEvent, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { m02Api } from '@/m02/api';

export function ChapterEditorPage() {
  const { accessToken } = useAuth();
  const { bookId = '', chapterId = '' } = useParams();
  const [body, setBody] = useState('');
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [revisions, setRevisions] = useState<Array<{ revision_id: string; created_at: string; message?: string }>>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken || !bookId || !chapterId) return;
    try {
      const d = await m02Api.getDraft(accessToken, bookId, chapterId);
      setBody(d.body);
      setVersion(d.draft_version);
      const rev = await m02Api.listRevisions(accessToken, bookId, chapterId);
      setRevisions(rev.items);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken, bookId, chapterId]);

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
    await load();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Chapter editor</h1>
      <form onSubmit={save} className="space-y-2">
        <textarea
          className="min-h-[280px] w-full rounded border px-2 py-1"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
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
              <button className="underline" onClick={() => void restore(r.revision_id)}>
                Restore
              </button>
            </li>
          ))}
        </ul>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
