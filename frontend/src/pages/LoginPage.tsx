import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiJson } from '../api';
import { useAuth } from '../auth';

export function LoginPage() {
  const nav = useNavigate();
  const { setTokens } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    try {
      const res = await apiJson<{
        access_token: string;
        refresh_token: string;
      }>('/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      setTokens(res.access_token, res.refresh_token);
      nav('/profile');
    } catch (e: unknown) {
      setErr((e as Error).message || 'login failed');
    }
  };

  return (
    <div className="layout">
      <nav>
        <Link to="/">Home</Link>
      </nav>
      <h2>Login</h2>
      <form onSubmit={submit}>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
          />
        </label>
        {err && <div className="error">{err}</div>}
        <button type="submit">Login</button>
      </form>
    </div>
  );
}
