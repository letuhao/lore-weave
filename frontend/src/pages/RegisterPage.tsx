import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../api';

export function RegisterPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    setOk('');
    try {
      const res = await apiJson<Record<string, unknown>>('/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          email,
          password,
          display_name: displayName || undefined,
        }),
      });
      setOk(`Created user ${res.user_id}. You can log in.`);
    } catch (e: unknown) {
      setErr((e as Error).message || 'register failed');
    }
  };

  return (
    <div className="layout">
      <nav>
        <Link to="/">Home</Link>
      </nav>
      <h2>Register</h2>
      <form onSubmit={submit}>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        </label>
        <label>
          Password (min 8, letter + digit)
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
          />
        </label>
        <label>
          Display name
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        {err && <div className="error">{err}</div>}
        {ok && <div className="success">{ok}</div>}
        <button type="submit">Register</button>
      </form>
    </div>
  );
}
