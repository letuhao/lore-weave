import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../api';
import { useAuth } from '../auth';

export function ProfilePage() {
  const { accessToken, refreshToken, setTokens, logoutLocal } = useAuth();
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  const load = async () => {
    setErr('');
    try {
      const p = await apiJson<Record<string, unknown>>('/v1/account/profile', {
        token: accessToken,
      });
      setProfile(p);
      setDisplayName((p.display_name as string) || '');
    } catch (e: unknown) {
      const er = e as Error & { status?: number; code?: string };
      if (er.status === 401 && refreshToken) {
        try {
          const r = await apiJson<{ access_token: string; refresh_token: string }>(
            '/v1/auth/refresh',
            {
              method: 'POST',
              body: JSON.stringify({ refresh_token: refreshToken }),
            },
          );
          setTokens(r.access_token, r.refresh_token);
          setMsg('Session refreshed — retry profile.');
          return;
        } catch {
          logoutLocal();
        }
      }
      setErr(er.message || 'load failed');
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    setMsg('');
    try {
      await apiJson('/v1/account/profile', {
        method: 'PATCH',
        token: accessToken,
        body: JSON.stringify({ display_name: displayName }),
      });
      setMsg('Saved.');
      await load();
    } catch (e: unknown) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="layout">
      <nav>
        <Link to="/">Home</Link>
      </nav>
      <h2>Profile</h2>
      {profile && (
        <pre style={{ fontSize: 12, overflow: 'auto' }}>{JSON.stringify(profile, null, 2)}</pre>
      )}
      <form onSubmit={save}>
        <label>
          Display name
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        {err && <div className="error">{err}</div>}
        {msg && <div className="success">{msg}</div>}
        <button type="submit">Save</button>
      </form>
    </div>
  );
}
