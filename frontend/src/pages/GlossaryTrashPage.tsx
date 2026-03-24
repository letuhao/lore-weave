import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import type { EntityTrashItem } from '@/features/glossary/types';

export function GlossaryTrashPage() {
  const { bookId } = useParams<{ bookId: string }>();
  const { accessToken } = useAuth();
  const [items, setItems] = useState<EntityTrashItem[]>([]);
  const [error, setError] = useState('');

  const load = async () => {
    if (!accessToken || !bookId) return;
    try {
      const res = await glossaryApi.listEntityTrash(bookId, accessToken);
      setItems(res.items);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => { void load(); }, [accessToken, bookId]);

  const restore = async (item: EntityTrashItem) => {
    if (!accessToken || !bookId) return;
    await glossaryApi.restoreEntity(bookId, item.entity_id, accessToken);
    void load();
  };

  const purge = async (item: EntityTrashItem) => {
    if (!accessToken || !bookId) return;
    await glossaryApi.purgeEntity(bookId, item.entity_id, accessToken);
    void load();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Glossary trash</h1>
        <Link to={`/books/${bookId}/glossary`} className="text-sm underline">
          Back to glossary
        </Link>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <ul className="space-y-2">
        {items.map((it) => (
          <li key={it.entity_id} className="rounded border p-3 text-sm">
            <div className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: it.kind_color }}
              />
              <span className="font-medium">{it.display_name || '(unnamed)'}</span>
              <span className="ml-1 text-xs text-muted-foreground">{it.kind_name}</span>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Deleted {new Date(it.deleted_at).toLocaleDateString()}
            </p>
            <div className="mt-2 flex gap-3">
              <button className="underline" onClick={() => void restore(it)}>
                Restore
              </button>
              <button className="underline text-destructive" onClick={() => void purge(it)}>
                Delete permanently
              </button>
            </div>
          </li>
        ))}
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">Trash is empty.</p>
        )}
      </ul>
    </div>
  );
}
