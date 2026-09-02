import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ListChecks, X } from 'lucide-react';
import { useChatStream } from '../providers';
import type { ToolCallRecord } from '../types';

// DQ-T76 — the pick-one card.
//
// 🔴 WHY A HUMAN AND NOT THE AGENT. A tool that needs an id it was not given used to get a
// refusal naming the tool that supplies it. Measured on the corpus: of 605 (session, tool)
// pairs that failed this way — supplier declared, supplier NAMED in the refusal — only 51
// (8%) ever succeeded with that tool again in the same session. Telling the model where the
// id comes from is a mechanism that fires and does not matter.
//
// 🔴 AND FETCHING IT AUTOMATICALLY IS NOT THE ANSWER EITHER. Replayed over real recorded
// supplier results, exactly one candidate comes back for ~6%; 76% return MANY rows. When the
// author says "delete the map" and the account holds twelve, no amount of fetching says which
// one — the information is not in the request. So the server fetches the rows and the AUTHOR
// chooses: the W3C Entity Reconciliation contract's `match: false` arm.
//
// The server executes on resume; this card performs NO API call of its own.

interface Props {
  record: ToolCallRecord;
}

interface Candidate {
  id: string;
  name?: string;
}

interface DisambiguationArgs {
  kind?: string;
  tool?: string;
  param?: string;
  supplier?: string;
  candidates?: Candidate[];
  truncated?: boolean;
  total?: number;
}

/** True when a pending tool record is the DQ-T76 disambiguation suspension. */
export function isDisambiguationRecord(tc: ToolCallRecord): boolean {
  return (
    tc.pending === true &&
    !!tc.args &&
    typeof tc.args === 'object' &&
    (tc.args as DisambiguationArgs).kind === 'disambiguation'
  );
}

export function DisambiguationCard({ record }: Props) {
  const { t } = useTranslation('chat');
  const { submitToolResult } = useChatStream();
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const args = (record.args ?? {}) as DisambiguationArgs;
  const tool = args.tool ?? record.tool;
  const param = args.param ?? '';
  const candidates = Array.isArray(args.candidates) ? args.candidates : [];

  async function choose(id: string | null) {
    if (busy || picked) return;
    setBusy(true);
    setPicked(id ?? 'cancelled');
    try {
      if (record.runId && record.toolCallId) {
        // The id rides `applied_text`; the outcome stays a closed-set literal.
        if (id) await submitToolResult(record.runId, record.toolCallId, 'disambiguated', id);
        else await submitToolResult(record.runId, record.toolCallId, 'cancelled');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      data-testid="disambiguation-card"
      data-tool={tool}
      data-param={param}
      className="mt-1.5 rounded-md border border-sky-500/40 bg-sky-500/5 p-2 text-xs"
    >
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-sky-500">
        <ListChecks className="h-3 w-3" />
        {t('disambiguation.label', {
          defaultValue: 'Which one did you mean?',
        })}
        <span className="ml-auto font-mono text-[9px] text-sky-500/70">{tool}</span>
      </div>

      {candidates.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">
          {t('disambiguation.empty', { defaultValue: 'No options were returned.' })}
        </p>
      ) : (
        <ul className="mb-1 flex flex-col gap-0.5">
          {candidates.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                data-testid="disambiguation-option"
                disabled={busy || picked !== null}
                onClick={() => choose(c.id)}
                className={
                  'w-full rounded px-1.5 py-1 text-left transition-colors ' +
                  (picked === c.id
                    ? 'bg-sky-500/20 text-foreground'
                    : 'hover:bg-sky-500/10 disabled:opacity-50')
                }
              >
                {/* The NAME is the choice; the id is shown small because it is what the tool
                    actually needs and a person may need to recognise it. A row with no name
                    still appears — hiding it would remove a valid choice. */}
                <span
                  data-testid={c.name?.trim() ? 'disambiguation-name' : 'disambiguation-unnamed'}
                  className="text-[11px] text-foreground/90"
                >
                  {c.name?.trim() ||
                    t('disambiguation.unnamed', { defaultValue: '(unnamed)' })}
                </span>
                <span className="ml-1.5 font-mono text-[9px] text-muted-foreground">
                  {c.id.slice(0, 8)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {args.truncated && (
        <p data-testid="disambiguation-truncated" data-total={args.total ?? candidates.length}
           className="mb-1 text-[10px] text-muted-foreground">
          {/* Says so rather than showing a prefix as if it were all of them. */}
          {t('disambiguation.truncated', {
            defaultValue: 'Showing {{shown}} of {{total}} — narrow your request to see others.',
            shown: candidates.length,
            total: args.total ?? candidates.length,
          })}
        </p>
      )}

      <button
        type="button"
        data-testid="disambiguation-cancel"
        disabled={busy || picked !== null}
        onClick={() => choose(null)}
        className="flex items-center gap-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
      >
        <X className="h-2.5 w-2.5" />
        {t('disambiguation.cancel', { defaultValue: 'None of these' })}
      </button>
    </div>
  );
}
