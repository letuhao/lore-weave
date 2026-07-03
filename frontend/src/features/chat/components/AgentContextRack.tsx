import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ToolSkillAddModal } from './ToolSkillAddModal';
import { RackServerGroups } from './RackServerGroups';
import type { AgentSurfaceState } from '../types';

interface AgentContextRackProps {
  enabledTools: string[];
  enabledSkills: string[];
  /** discovered (activated) tool names — grouped with the pins by server. */
  activatedTools: string[];
  /** W6: last agentSurface frame — drives the per-server live dots and the
   *  "N tools · M skills · X tok" summary chip. Optional: without it the rack
   *  degrades to pins-only grouping (muted dots, no token count). */
  surface?: AgentSurfaceState | null;
  token: string | null;
  onAddTool: (name: string) => void;
  onAddSkill: (id: string) => void;
  onRemoveTool: (name: string) => void;
  onRemoveSkill: (id: string) => void;
  onClearDiscovered: () => void;
  disabled?: boolean;
  /** W2: external "open the add modal" signal (the context breakdown panel's
   *  manage action). Controlled OR-ed with the rack's own + button state. */
  externalAddOpen?: boolean;
  onExternalAddClose?: () => void;
  /** W6: opens the ContextBreakdownPanel (the summary chip's click-through).
   *  Omitted on surfaces without the meter → the chip is a no-op tooltip. */
  onOpenBreakdown?: () => void;
}

/** W6 — summary chip math: tool count prefers the live advertised surface
 *  (what the model actually sees), falling back to pins + discovered.
 *
 *  A turn-OPENING agentSurface frame (Curated/SkillInjected) carries the
 *  tracker DEFAULTS — an all-empty `advertised` and a zero-zero
 *  `schema_tokens`. Those are NOT-measured, not "0 tools · 0 tok": tools fall
 *  back to the pins+discovered set and tokens report null (the component keeps
 *  the previous measured value). */
export function summarizeRack(
  surface: AgentSurfaceState | null | undefined,
  enabledTools: string[],
  activatedTools: string[],
  enabledSkills: string[],
): { tools: number; skills: number; tokens: number | null } {
  const adv = surface?.advertised;
  const advCount = adv ? adv.core.length + adv.frontend.length + adv.activated.length : 0;
  const tools = adv && advCount > 0
    ? advCount
    : new Set([...enabledTools, ...activatedTools]).size;
  // 0 injected skills is a REAL measurement (a turn may inject none) — only a
  // missing array falls back to the session pins (?? on the array, never || on
  // the length).
  const skills = (surface?.injected_skills ?? enabledSkills).length;
  const st = surface?.schema_tokens;
  const tokens = st && (st.frontend > 0 || st.mcp > 0) ? st.frontend + st.mcp : null;
  return { tools, skills, tokens };
}

export function AgentContextRack({
  enabledTools,
  enabledSkills,
  activatedTools,
  surface,
  token,
  onAddTool,
  onAddSkill,
  onRemoveTool,
  onRemoveSkill,
  onClearDiscovered,
  disabled,
  externalAddOpen,
  onExternalAddClose,
  onOpenBreakdown,
}: AgentContextRackProps) {
  const { t } = useTranslation('chat');
  const [modalOpen, setModalOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const hasPins = enabledTools.length > 0 || enabledSkills.length > 0;
  const measured = summarizeRack(surface, enabledTools, activatedTools, enabledSkills);

  // Rack-flash fix: a turn-opening frame carries the tracker defaults (see
  // summarizeRack) — hold the PREVIOUS measured values so the chip/dots don't
  // flash "0 tok"/muted for a frame. A surface with the field entirely ABSENT
  // (degraded/session reset/older backend) clears the memory instead.
  const lastTokensRef = useRef<number | null>(null);
  const st = surface?.schema_tokens;
  if (!st) lastTokensRef.current = null;
  else if (st.frontend > 0 || st.mcp > 0) lastTokensRef.current = st.frontend + st.mcp;
  const summary = { ...measured, tokens: measured.tokens ?? lastTokensRef.current };

  const lastServersRef = useRef<Record<string, { tools: number }> | undefined>(undefined);
  const sv = surface?.servers;
  if (!sv) lastServersRef.current = undefined;
  else if (Object.keys(sv).length > 0) lastServersRef.current = sv;
  const liveServers = sv && Object.keys(sv).length > 0 ? sv : lastServersRef.current;

  const summaryText = summary.tokens != null
    ? t('rack.summary', { tools: summary.tools, skills: summary.skills, tokens: summary.tokens.toLocaleString() })
    : t('rack.summary_no_tokens', { tools: summary.tools, skills: summary.skills });

  return (
    <div className="border-t border-border bg-muted/20 px-3 py-2" data-testid="agent-context-rack">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {t('rack.label')}
        </span>
        <button
          type="button"
          data-testid="agent-rack-summary"
          onClick={() => onOpenBreakdown?.()}
          title={t('rack.summary_tooltip')}
          className={`rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground ${
            onOpenBreakdown ? 'hover:border-accent hover:text-foreground' : 'cursor-default'
          }`}
        >
          {summaryText}
        </button>
        <RackServerGroups
          pinned={enabledTools}
          discovered={activatedTools}
          liveServers={liveServers}
          onRemoveTool={onRemoveTool}
          disabled={disabled}
        />
        {enabledSkills.map((id) => (
          <span
            key={`s-${id}`}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[10px]"
          >
            <span className="text-muted-foreground">✦</span>
            {id}
            {!disabled && (
              <button type="button" onClick={() => onRemoveSkill(id)} className="text-muted-foreground hover:text-foreground" aria-label={t('rack.remove')}>
                ×
              </button>
            )}
          </span>
        ))}
        {!disabled && (
          <button
            type="button"
            data-testid="agent-rack-add"
            onClick={() => setModalOpen(true)}
            className="rounded-full border border-dashed border-border px-2 py-0.5 text-[10px] text-muted-foreground hover:border-accent hover:text-foreground"
          >
            + {t('rack.add')}
          </button>
        )}
        {activatedTools.length > 0 && (
          <span className="text-[10px] text-muted-foreground">
            {t('rack.discovered', { count: activatedTools.length })}
          </span>
        )}
        <div className="relative ml-auto">
          <button
            type="button"
            disabled={disabled || !hasPins && activatedTools.length === 0}
            onClick={() => setMenuOpen((v) => !v)}
            className="text-[10px] text-muted-foreground hover:text-foreground disabled:opacity-40"
          >
            ⋯
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 min-w-[10rem] rounded-md border border-border bg-card py-1 shadow-lg">
              <button
                type="button"
                data-testid="agent-rack-clear-discovered"
                className="block w-full px-3 py-1.5 text-left text-xs hover:bg-muted/60"
                onClick={() => {
                  onClearDiscovered();
                  setMenuOpen(false);
                }}
              >
                {t('rack.clear_discovered')}
              </button>
            </div>
          )}
        </div>
      </div>
      <ToolSkillAddModal
        open={modalOpen || !!externalAddOpen}
        onClose={() => { setModalOpen(false); onExternalAddClose?.(); }}
        token={token}
        onAddTool={onAddTool}
        onAddSkill={onAddSkill}
        existingTools={enabledTools}
        existingSkills={enabledSkills}
      />
    </div>
  );
}
