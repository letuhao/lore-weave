import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../api';

export function ResetPage() {
  const [token, setToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    setMsg('');
    try {
      await apiJson('/v1/auth/password-reset/confirm', {
        method: 'POST',
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      setMsg('Password updated — log in again.');
    } catch (e: unknown) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="layout">
      <nav>
        <Link to="/">Home</Link>
      </nav>
      <h2>Reset password</h2>
      <form onSubmit={submit}>
        <label>
          Token (from dev log)
          <input value={token} onChange={(e) => setToken(e.target.value)} required />
        </label>
        <label>
          New password
          <input
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            type="password"
            required
          />
        </label>
        {err && <div className="error">{err}</div>}
        {msg && <div className="success">{msg}</div>}
        <button type="submit">Confirm reset</button>
      </form>
    </div>
  );
}
