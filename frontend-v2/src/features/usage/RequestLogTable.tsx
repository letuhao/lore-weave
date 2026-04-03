import { Fragment, useState } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Pagination } from '@/components/shared/Pagination';
import { ExpandedRow } from './ExpandedRow';
import type { UsageLog, UsageFilters, ProviderKind, RequestStatus, Purpose } from './types';

const STATUS_STYLES: Record<string, string> = {
  success: 'bg-green-500/10 text-green-400',
  provider_error: 'bg-destructive/10 text-destructive',
  billing_rejected: 'bg-yellow-500/10 text-yellow-400',
};

const PURPOSE_STYLES: Record<string, string> = {
  translation: 'bg-green-500/10 text-green-400 border-green-500/15',
  chat: 'bg-accent/10 text-accent border-accent/15',
  chunk_edit: 'bg-purple-500/10 text-purple-400 border-purple-500/15',
  image_gen: 'bg-primary/10 text-primary border-primary/15',
  unknown: 'bg-secondary text-muted-foreground border-border',
};

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: 'text-[#d4a574]',
  openai: 'text-[#74c0a4]',
  ollama: 'text-[#7ab4f0]',
  lm_studio: 'text-[#a78bfa]',
};

const PURPOSE_LABELS: Record<string, string> = {
  translation: 'Translation',
  chat: 'Chat',
  chunk_edit: 'Chunk Edit',
  image_gen: 'Image Gen',
  unknown: 'Other',
};

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
    ', ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

type Props = {
  logs: UsageLog[];
  total: number;
  limit: number;
  offset: number;
  filters: UsageFilters;
  search: string;
  loading?: boolean;
  onSearchChange: (v: string) => void;
  onFiltersChange: (f: UsageFilters) => void;
  onOffsetChange: (offset: number) => void;
  onLimitChange: (limit: number) => void;
};

export function RequestLogTable({
  logs,
  total,
  limit,
  offset,
  filters,
  search,
  loading,
  onSearchChange,
  onFiltersChange,
  onOffsetChange,
  onLimitChange,
}: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const activeFilters = Object.entries(filters).filter(([, v]) => v);

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold">Request Log</span>
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {total} requests
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground">Show</span>
          <select
            value={limit}
            onChange={(e) => { onLimitChange(Number(e.target.value)); onOffsetChange(0); }}
            className="h-7 rounded border bg-background px-1.5 text-[11px]"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>
      </div>

      {/* Filters bar */}
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
        {/* Search */}
        <div className="relative min-w-[200px] max-w-[280px] flex-1">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Filter current page..."
            aria-label="Search usage logs on current page"
            className="h-[30px] w-full rounded border bg-background pl-7 pr-2 text-[11px] placeholder:text-muted-foreground/40 focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
        </div>

        {/* Dropdowns */}
        <select
          value={filters.provider_kind ?? ''}
          onChange={(e) => onFiltersChange({ ...filters, provider_kind: (e.target.value || undefined) as ProviderKind | undefined })}
          aria-label="Filter by provider"
          className="h-[30px] min-w-[130px] rounded border bg-background px-2 text-[11px]"
        >
          <option value="">All Providers</option>
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
          <option value="ollama">Ollama</option>
          <option value="lm_studio">LM Studio</option>
        </select>

        <select
          value={filters.purpose ?? ''}
          onChange={(e) => onFiltersChange({ ...filters, purpose: (e.target.value || undefined) as Purpose | undefined })}
          aria-label="Filter by purpose"
          className="h-[30px] min-w-[120px] rounded border bg-background px-2 text-[11px]"
        >
          <option value="">All Purposes</option>
          <option value="translation">Translation</option>
          <option value="chat">Chat</option>
          <option value="chunk_edit">Chunk Edit</option>
          <option value="image_gen">Image Gen</option>
        </select>

        <select
          value={filters.request_status ?? ''}
          onChange={(e) => onFiltersChange({ ...filters, request_status: (e.target.value || undefined) as RequestStatus | undefined })}
          aria-label="Filter by status"
          className="h-[30px] min-w-[100px] rounded border bg-background px-2 text-[11px]"
        >
          <option value="">All Status</option>
          <option value="success">Success</option>
          <option value="provider_error">Error</option>
          <option value="billing_rejected">Rejected</option>
        </select>

        {/* Active filter chips */}
        {activeFilters.map(([key, value]) => (
          <span
            key={key}
            className="flex items-center gap-1 rounded-full border border-primary bg-primary/10 px-2.5 py-0.5 text-[11px] text-primary"
          >
            {String(value)}
            <button
              onClick={() => onFiltersChange({ ...filters, [key]: undefined })}
              className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-primary/20"
            >
              <X className="h-2 w-2" />
            </button>
          </span>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="border-b bg-muted/30 px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 140 }}>Time</th>
              <th className="border-b bg-muted/30 px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 80 }}>Status</th>
              <th className="border-b bg-muted/30 px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 90 }}>Purpose</th>
              <th className="border-b bg-muted/30 px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 100 }}>Provider</th>
              <th className="border-b bg-muted/30 px-3 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 80 }}>Input</th>
              <th className="border-b bg-muted/30 px-3 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 80 }}>Output</th>
              <th className="border-b bg-muted/30 px-3 py-2 text-right text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 70 }}>Cost</th>
              <th className="border-b bg-muted/30 px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground" style={{ width: 36 }} />
            </tr>
          </thead>
          <tbody>
            {loading && logs.length === 0 && Array.from({ length: 5 }).map((_, i) => (
              <tr key={`skel-${i}`}>
                {Array.from({ length: 8 }).map((_, j) => (
                  <td key={j} className="px-3 py-2">
                    <div className="h-4 animate-pulse rounded bg-muted" />
                  </td>
                ))}
              </tr>
            ))}
            {logs.map((log) => (
              <Fragment key={log.usage_log_id}>
                <tr
                  onClick={() => setExpandedId(expandedId === log.usage_log_id ? null : log.usage_log_id)}
                  className={cn(
                    'cursor-pointer border-b transition-colors hover:bg-card',
                    expandedId === log.usage_log_id && 'bg-primary/5',
                  )}
                >
                  <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{formatTime(log.created_at)}</td>
                  <td className="px-3 py-2">
                    <span className={cn('inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium', STATUS_STYLES[log.request_status] ?? 'bg-secondary text-muted-foreground')}>
                      {log.request_status === 'success' ? '200 OK' : log.request_status === 'provider_error' ? 'Error' : 'Rejected'}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={cn('inline-flex rounded border px-2 py-0.5 text-[10px] font-medium', PURPOSE_STYLES[log.purpose] ?? PURPOSE_STYLES.unknown)}>
                      {PURPOSE_LABELS[log.purpose] ?? log.purpose}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span className={cn('text-[11px]', PROVIDER_COLORS[log.provider_kind])}>
                      {log.provider_kind}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-[11px]">{log.input_tokens.toLocaleString()}</td>
                  <td className={cn('px-3 py-2 text-right font-mono text-[11px]', log.request_status !== 'success' && 'text-destructive')}>
                    {log.output_tokens.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-[11px] text-muted-foreground">${log.total_cost_usd.toFixed(3)}</td>
                  <td className="px-3 py-2">
                    <span aria-label={expandedId === log.usage_log_id ? 'Collapse details' : 'Expand details'}>
                      <ChevronDown
                        className={cn(
                          'h-3 w-3 text-muted-foreground transition-transform',
                          expandedId === log.usage_log_id && 'rotate-180',
                        )}
                      />
                    </span>
                  </td>
                </tr>
                {expandedId === log.usage_log_id && (
                  <ExpandedRow usageLogId={log.usage_log_id} colSpan={8} />
                )}
              </Fragment>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-xs text-muted-foreground">
                  No usage logs found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="border-t px-4 py-3">
        <Pagination total={total} limit={limit} offset={offset} onChange={onOffsetChange} />
      </div>
    </div>
  );
}
