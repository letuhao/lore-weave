import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { booksApi } from '@/features/books/api';
import { PaginationBar } from '@/components/books/PaginationBar';

export function UnlistedPage() {
  const { accessToken = '' } = useParams();
  const [data, setData] = useState<{ title: string; summary_excerpt?: string; original_language?: string } | null>(null);
  const [items, setItems] = useState<Array<{ chapter_id: string; title?: string | null; sort_order: number }>>([]);
  const [selected, setSelected] = useState<{ chapter_id: string; title?: string | null; body: string } | null>(null);
  const [total, setTotal] = useState(0);
  const [limit] = useState(20);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const res = await booksApi.getUnlisted(accessToken);
        const chapters = await booksApi.listUnlistedChapters(accessToken, { limit, offset });
        setData(res);
        setItems(chapters.items);
        setTotal(chapters.total);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [accessToken, limit, offset]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
      <div className="space-y-3 rounded border p-3">
        <h1 className="text-xl font-semibold">{data.title}</h1>
        <p className="text-sm text-muted-foreground">language: {data.original_language || 'n/a'}</p>
        <p>{data.summary_excerpt || ''}</p>
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.chapter_id} className="rounded border p-2 text-sm">
              <button
                className="text-left underline"
                onClick={async () => {
                  const detail = await booksApi.getUnlistedChapter(accessToken, item.chapter_id);
                  setSelected({ chapter_id: item.chapter_id, title: item.title, body: detail.body });
                }}
              >
                Ch. {item.sort_order} - {item.title || 'Untitled'}
              </button>
            </li>
          ))}
        </ul>
        <PaginationBar total={total} limit={limit} offset={offset} onChange={setOffset} />
      </div>
      <div className="rounded border p-3">
        {!selected ? (
          <p className="text-sm text-muted-foreground">Select a chapter to read.</p>
        ) : (
          <div className="space-y-2">
            <h2 className="text-lg font-medium">{selected.title || 'Untitled'}</h2>
            <pre className="whitespace-pre-wrap text-sm">{selected.body}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
