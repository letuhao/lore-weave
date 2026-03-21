import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { m02Api } from '@/m02/api';

export function UnlistedPage() {
  const { accessToken = '' } = useParams();
  const [data, setData] = useState<{ title: string; summary_excerpt?: string; original_language?: string } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const res = await m02Api.getUnlisted(accessToken);
        setData(res);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [accessToken]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">{data.title}</h1>
      <p className="text-sm text-muted-foreground">language: {data.original_language || 'n/a'}</p>
      <p>{data.summary_excerpt || ''}</p>
    </div>
  );
}
