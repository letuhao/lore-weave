import { useEffect, useState } from 'react';
import { m02Api } from '@/m02/api';

export function BrowsePage() {
  const [items, setItems] = useState<Array<{ book_id: string; title: string; summary_excerpt?: string; original_language?: string }>>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const res = await m02Api.listCatalog();
        setItems(res.items);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Browse public books</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-2">
        {items.map((b) => (
          <li key={b.book_id} className="rounded border p-3">
            <p className="font-medium">{b.title}</p>
            <p className="text-xs text-muted-foreground">
              language: {b.original_language || 'n/a'} | {b.summary_excerpt || ''}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
