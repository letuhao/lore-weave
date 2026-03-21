import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../api';
import { useAuth } from '../auth';

export function SecurityPage() {
  const { accessToken } = useAuth();
  const [prefs, setPrefs] = useState<Record<string, unknown> | null>(null);
  const [method, setMethod] = useState<'email_link' | 'email_code'>('email_link');
  const [err, setErr] = useState('');

  const load = async () => {
    try {
      const p = await apiJson<Record<string, unknown>>('/v1/account/security/preferences', {
        token: accessToken,
      });
      setPrefs(p);
      setMethod((p.password_reset_method as 'email_link' | 'email_code') || 'email_link');
    } catch (e: unknown) {
      setErr((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    try {
      await apiJson('/v1/account/security/preferences', {
        method: 'PATCH',
        token: accessToken,
        body: JSON.stringify({ password_reset_method: method }),
      });
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
      <h2>Security preferences</h2>
      {prefs && (
        <pre style={{ fontSize: 12 }}>{JSON.stringify(prefs, null, 2)}</pre>
      )}
      <form onSubmit={save}>
        <label>
          Password reset method
          <select value={method} onChange={(e) => setMethod(e.target.value as typeof method)}>
            <option value="email_link">email_link</option>
            <option value="email_code">email_code</option>
          </select>
        </label>
        {err && <div className="error">{err}</div>}
        <button type="submit">Save</button>
      </form>
    </div>
  );
}
