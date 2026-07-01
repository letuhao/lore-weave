import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ToolSkillAddModal } from './ToolSkillAddModal';

interface AgentContextRackProps {
  enabledTools: string[];
  enabledSkills: string[];
  activatedCount: number;
  token: string | null;
  onAddTool: (name: string) => void;
  onAddSkill: (id: string) => void;
  onRemoveTool: (name: string) => void;
  onRemoveSkill: (id: string) => void;
  onClearDiscovered: () => void;
  disabled?: boolean;
}

export function AgentContextRack({
  enabledTools,
  enabledSkills,
  activatedCount,
  token,
  onAddTool,
  onAddSkill,
  onRemoveTool,
  onRemoveSkill,
  onClearDiscovered,
  disabled,
}: AgentContextRackProps) {
  const { t } = useTranslation('chat');
  const [modalOpen, setModalOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const hasPins = enabledTools.length > 0 || enabledSkills.length > 0;

  return (
    <div className="border-t border-border bg-muted/20 px-3 py-2" data-testid="agent-context-rack">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          {t('rack.label', { defaultValue: 'Context' })}
        </span>
        {enabledTools.map((name) => (
          <span
            key={`t-${name}`}
            data-testid={`agent-rack-chip-tool-${name}`}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[10px]"
          >
            <span className="text-muted-foreground">🔧</span>
            {name}
            {!disabled && (
              <button type="button" onClick={() => onRemoveTool(name)} className="text-muted-foreground hover:text-foreground" aria-label="Remove">
                ×
              </button>
            )}
          </span>
        ))}
        {enabledSkills.map((id) => (
          <span
            key={`s-${id}`}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[10px]"
          >
            <span className="text-muted-foreground">✦</span>
            {id}
            {!disabled && (
              <button type="button" onClick={() => onRemoveSkill(id)} className="text-muted-foreground hover:text-foreground" aria-label="Remove">
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
            + {t('rack.add', { defaultValue: 'Add' })}
          </button>
        )}
        {activatedCount > 0 && (
          <span className="text-[10px] text-muted-foreground">
            {t('rack.discovered', { defaultValue: '{{count}} discovered', count: activatedCount })}
          </span>
        )}
        <div className="relative ml-auto">
          <button
            type="button"
            disabled={disabled || !hasPins && activatedCount === 0}
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
                {t('rack.clear_discovered', { defaultValue: 'Clear discovered tools' })}
              </button>
            </div>
          )}
        </div>
      </div>
      <ToolSkillAddModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        token={token}
        onAddTool={onAddTool}
        onAddSkill={onAddSkill}
        existingTools={enabledTools}
        existingSkills={enabledSkills}
      />
    </div>
  );
}
