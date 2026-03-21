import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { m02Api } from '@/m02/api';

export function SharingPage() {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const { bookId = '' } = useParams();
  const [visibility, setVisibility] = useState<'private' | 'unlisted' | 'public'>('private');
  const [token, setToken] = useState<string | undefined>(undefined);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = async () => {
    if (!accessToken || !bookId) return;
    try {
      const res = await m02Api.getSharing(accessToken, bookId);
      setVisibility(res.visibility);
      setToken(res.unlisted_access_token);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, [accessToken, bookId]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!accessToken || !bookId) return;
    setSaving(true);
    try {
      const res = await m02Api.patchSharing(accessToken, bookId, { visibility });
      setVisibility((res as { visibility: 'private' | 'unlisted' | 'public' }).visibility);
      setToken((res as { unlisted_access_token?: string }).unlisted_access_token);
      navigate(`/books/${bookId}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">Sharing policy</h1>
        <Link className="text-sm underline" to={`/books/${bookId}`}>
          Back to book detail
        </Link>
      </div>
      <form className="space-y-2" onSubmit={save}>
        <select
          className="w-full rounded border px-2 py-1"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as 'private' | 'unlisted' | 'public')}
        >
          <option value="private">private</option>
          <option value="unlisted">unlisted</option>
          <option value="public">public</option>
        </select>
        <button className="rounded bg-primary px-3 py-1 text-primary-foreground" disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </form>
      {visibility === 'unlisted' && token && (
        <p className="text-sm">
          Unlisted URL: <code>{`${window.location.origin}/s/${token}`}</code>
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
