import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { m02Api } from '@/m02/api';
import { PaginationBar } from '@/components/m02/PaginationBar';

export function BrowsePage() {
  const [items, setItems] = useState<Array<{ book_id: string; title: string; summary_excerpt?: string; original_language?: string; chapter_count?: number }>>([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(12);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const res = await m02Api.listCatalog({ limit, offset });
        setItems(res.items);
        setTotal(res.total);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [limit, offset]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Browse public books</h1>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-2">
        {items.map((b) => (
          <li key={b.book_id} className="rounded border p-3">
            <Link className="font-medium underline" to={`/browse/${b.book_id}`}>
              {b.title}
            </Link>
            <p className="text-xs text-muted-foreground">
              language: {b.original_language || 'n/a'} | chapters: {b.chapter_count || 0}
            </p>
            <p className="mt-1 text-sm">{b.summary_excerpt || ''}</p>
          </li>
        ))}
      </ul>
      <PaginationBar total={total} limit={limit} offset={offset} onChange={setOffset} />
    </div>
  );
}
