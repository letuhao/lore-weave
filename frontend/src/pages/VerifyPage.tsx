import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../api';
import { useAuth } from '../auth';

export function VerifyPage() {
  const { accessToken } = useAuth();
  const [token, setToken] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const request = async () => {
    setErr('');
    setMsg('');
    try {
      await apiJson('/v1/auth/verify-email/request', {
        method: 'POST',
        token: accessToken,
      });
      setMsg(
        'Verification email sent (if SMTP is configured). Check Mailhog at http://localhost:8025 or the auth-service logs for the token.',
      );
    } catch (e: unknown) {
      setErr((e as Error).message);
    }
  };

  const confirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    setMsg('');
    try {
      await apiJson('/v1/auth/verify-email/confirm', {
        method: 'POST',
        body: JSON.stringify({ token }),
      });
      setMsg('Email verified.');
    } catch (e: unknown) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="layout">
      <nav>
        <Link to="/">Home</Link>
      </nav>
      <h2>Email verification</h2>
      <button type="button" onClick={() => void request()}>
        Request verification email
      </button>
      <form onSubmit={confirm}>
        <label>
          Token (from email or server log)
          <input value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        {err && <div className="error">{err}</div>}
        {msg && <div className="success">{msg}</div>}
        <button type="submit">Confirm</button>
      </form>
    </div>
  );
}
