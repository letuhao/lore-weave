import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/shared/Button';
import type { JSX } from 'react';

// Login placeholder. Session E wires real auth handshake against
// auth-service via api-gateway-bff. Single-domain + path-routing per
// spec §8 (MED-8 rejected cross-subdomain cookie complexity).

export function LoginRoute(): JSX.Element {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-slate-100 gap-4">
      <h1 className="text-3xl font-bold">LoreWeave — Login (placeholder)</h1>
      <p className="text-slate-400">Session E will wire real auth.</p>
      <Button onClick={() => navigate('/world-select')}>Continue as guest</Button>
    </div>
  );
}
