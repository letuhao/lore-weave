import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiJson } from '../api';

export function ForgotPage() {
  const [email, setEmail] = useState('');
  const [msg, setMsg] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg('');
    try {
      await apiJson('/v1/auth/password-reset/request', {
        method: 'POST',
        body: JSON.stringify({ email }),
      });
      setMsg(
        'If the account exists, a reset was triggered. Check Mailhog at http://localhost:8025 or auth-service logs for the token.',
      );
    } catch {
      setMsg('Request accepted.');
    }
  };

  return (
    <div className="layout">
      <nav>
        <Link to="/">Home</Link>
      </nav>
      <h2>Forgot password</h2>
      <form onSubmit={submit}>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        {msg && <div className="success">{msg}</div>}
        <button type="submit">Request reset</button>
      </form>
    </div>
  );
}
