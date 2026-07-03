// Add-MCP-Server wizard (REG-P3-06) — 4 steps: Connection → Auth → Health & Scan →
// Review & Enable. State lives in this component so it survives panel hide/show
// (never conditionally unmounted). The server is REGISTERED at the Health & Scan
// step (quarantined pending), then scanned/connected before the user enables it.
import { useState } from 'react';
import { useCreateMcpServer, useMcpServerDetail } from '../hooks/useMcpServers';
import type { McpAuthKind } from '../types';
import { McpStatusChip } from './McpServersView';
import { ScanReport } from './McpServerDetail';

type Step = 1 | 2 | 3 | 4;

export function AddMcpWizard({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [step, setStep] = useState<Step>(1);
  const [displayName, setDisplayName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [authKind, setAuthKind] = useState<McpAuthKind>('none');
  const [bearer, setBearer] = useState('');
  const [oauth, setOauth] = useState({ authorization_endpoint: '', token_endpoint: '', client_id: '', scopes: '' });
  const [createdId, setCreatedId] = useState<string | null>(null);

  const { create, creating, error: createErr } = useCreateMcpServer();

  const register = async () => {
    const server = await create({
      display_name: displayName,
      endpoint_url: endpoint,
      auth_kind: authKind,
      bearer_token: authKind === 'bearer' ? bearer : undefined,
      oauth: authKind === 'oauth2'
        ? { ...oauth, scopes: oauth.scopes ? oauth.scopes.split(/[\s,]+/).filter(Boolean) : [] }
        : undefined,
    });
    if (server) {
      setCreatedId(server.mcp_server_id);
      setStep(3);
    }
  };

  return (
    <div className="space-y-4" data-testid="mcp-add-wizard">
      <Steps step={step} />
      {step === 1 && (
        <div className="space-y-3">
          <Field label="Display name">
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} data-testid="wiz-display-name" className={inputCls} placeholder="My tools server" />
          </Field>
          <Field label="Server URL (streamable-http)">
            <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} data-testid="wiz-endpoint-url" className={inputCls} placeholder="https://mcp.example.com/mcp" />
          </Field>
          <Field label="Authentication">
            <select value={authKind} onChange={(e) => setAuthKind(e.target.value as McpAuthKind)} data-testid="wiz-auth-kind" className={inputCls}>
              <option value="none">None</option>
              <option value="bearer">Bearer token</option>
              <option value="oauth2">OAuth 2.1</option>
            </select>
          </Field>
          <Nav onCancel={onCancel} onNext={() => setStep(2)} nextDisabled={!endpoint.trim()} />
        </div>
      )}

      {step === 2 && (
        <div className="space-y-3">
          {authKind === 'none' && <p className="text-xs text-muted-foreground">No authentication — this server is open. Continue to register and scan it.</p>}
          {authKind === 'bearer' && (
            <Field label="Bearer token (sealed in the vault; never shown again)">
              <input type="password" value={bearer} onChange={(e) => setBearer(e.target.value)} data-testid="wiz-bearer-token" className={inputCls} placeholder="paste token" />
            </Field>
          )}
          {authKind === 'oauth2' && (
            <>
              <Field label="Authorization endpoint"><input value={oauth.authorization_endpoint} onChange={(e) => setOauth({ ...oauth, authorization_endpoint: e.target.value })} data-testid="wiz-oauth-authz" className={inputCls} /></Field>
              <Field label="Token endpoint"><input value={oauth.token_endpoint} onChange={(e) => setOauth({ ...oauth, token_endpoint: e.target.value })} data-testid="wiz-oauth-token" className={inputCls} /></Field>
              <Field label="Client ID"><input value={oauth.client_id} onChange={(e) => setOauth({ ...oauth, client_id: e.target.value })} data-testid="wiz-oauth-client" className={inputCls} /></Field>
              <Field label="Scopes (space-separated)"><input value={oauth.scopes} onChange={(e) => setOauth({ ...oauth, scopes: e.target.value })} data-testid="wiz-oauth-scopes" className={inputCls} /></Field>
            </>
          )}
          {createErr && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400" data-testid="wiz-error">{createErr}</div>}
          <Nav onCancel={() => setStep(1)} cancelLabel="Back" onNext={() => void register()} nextLabel={creating ? 'Registering…' : 'Register & scan'} nextDisabled={creating || (authKind === 'bearer' && !bearer) || (authKind === 'oauth2' && (!oauth.authorization_endpoint || !oauth.token_endpoint || !oauth.client_id))} />
        </div>
      )}

      {step === 3 && createdId && (
        <HealthScanStep id={createdId} authKind={authKind} onNext={() => setStep(4)} />
      )}

      {step === 4 && createdId && (
        <ReviewEnableStep id={createdId} onDone={onDone} />
      )}
    </div>
  );
}

function HealthScanStep({ id, authKind, onNext }: { id: string; authKind: McpAuthKind; onNext: () => void }) {
  const d = useMcpServerDetail(id);
  return (
    <div className="space-y-3" data-testid="wiz-health-scan">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">Status:</span>
        {d.server && <McpStatusChip status={d.server.status} />}
      </div>
      {authKind === 'oauth2' && d.server?.status !== 'active' && (
        <button onClick={() => void d.connectOAuth()} data-testid="wiz-oauth-connect" className="rounded-md border px-3 py-1.5 text-xs font-semibold">Connect with OAuth →</button>
      )}
      <div className="flex gap-2">
        <button onClick={() => void d.rescan()} disabled={d.busy} data-testid="wiz-run-scan" className="rounded-md border px-3 py-1.5 text-xs disabled:opacity-40">{d.busy ? 'Scanning…' : 'Run health & scan'}</button>
        <button onClick={() => void d.refresh()} className="rounded-md border px-3 py-1.5 text-xs">Refresh</button>
      </div>
      {d.server?.scan_result && <ScanReport server={d.server} />}
      <Nav onCancel={onNext} cancelLabel="" onNext={onNext} nextLabel="Continue" />
    </div>
  );
}

function ReviewEnableStep({ id, onDone }: { id: string; onDone: () => void }) {
  const d = useMcpServerDetail(id);
  const [enabled, setEnabled] = useState(true);
  const finish = async () => {
    await d.setEnabled(enabled);
    onDone();
  };
  return (
    <div className="space-y-3" data-testid="wiz-review">
      {d.server && (
        <div className="rounded-md border p-3 text-xs">
          <div className="font-medium">{d.server.display_name || d.server.endpoint_url}</div>
          <div className="text-muted-foreground">{d.server.endpoint_url}</div>
          <div className="mt-1 flex items-center gap-2"><McpStatusChip status={d.server.status} /><span className="text-muted-foreground">auth: {d.server.auth_kind}</span></div>
        </div>
      )}
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} data-testid="wiz-enable-toggle" />
        Enable for my sessions
      </label>
      <button onClick={() => void finish()} data-testid="wiz-finish" className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground">Done</button>
    </div>
  );
}

const inputCls = 'w-full rounded-md border bg-background px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-ring';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block space-y-1"><span className="text-xs font-medium text-muted-foreground">{label}</span>{children}</label>;
}

function Steps({ step }: { step: Step }) {
  const labels = ['Connection', 'Auth', 'Health & Scan', 'Review'];
  return (
    <ol className="flex gap-2 text-[11px]" data-testid="wiz-steps">
      {labels.map((l, i) => (
        <li key={l} className={`rounded-full px-2 py-0.5 ${i + 1 === step ? 'bg-primary text-primary-foreground font-semibold' : i + 1 < step ? 'bg-muted text-foreground' : 'text-muted-foreground'}`}>{i + 1}. {l}</li>
      ))}
    </ol>
  );
}

function Nav({ onCancel, onNext, cancelLabel = 'Cancel', nextLabel = 'Next', nextDisabled }: { onCancel: () => void; onNext: () => void; cancelLabel?: string; nextLabel?: string; nextDisabled?: boolean }) {
  return (
    <div className="flex justify-between pt-1">
      {cancelLabel ? <button onClick={onCancel} className="rounded-md border px-3 py-1.5 text-xs">{cancelLabel}</button> : <span />}
      <button onClick={onNext} disabled={nextDisabled} data-testid="wiz-next" className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground disabled:opacity-40">{nextLabel}</button>
    </div>
  );
}
