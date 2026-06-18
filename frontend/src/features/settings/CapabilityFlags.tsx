import { useTranslation } from 'react-i18next';
import { RERANK_CAPABILITY } from './api';

// C1 (BL-1): `rerank` is registered via the canonical RERANK_CAPABILITY token —
// the SAME value RerankModelPicker/ModelRolePicker filter on — so a hand-tagged
// rerank model surfaces in those pickers. Referencing the constant (not a
// literal) keeps the register form and the pickers from drifting apart again
// (the C0 rerank/reranker reconcile).
const KNOWN_FLAGS = ['chat', 'vision', 'tool_calling', 'extended_thinking', 'json_mode', 'reasoning', 'tts', 'stt', 'image_gen', 'video_gen', 'embedding', RERANK_CAPABILITY, 'moderation'] as const;

type Props = {
  flags: Record<string, boolean>;
  onChange: (flags: Record<string, boolean>) => void;
};

export function CapabilityFlags({ flags, onChange }: Props) {
  const { t } = useTranslation('settings');
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium">{t('capability.label')}</label>
      <div className="flex flex-wrap gap-3">
        {KNOWN_FLAGS.map((f) => (
          <label key={f} className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input
              type="checkbox"
              checked={flags[f] ?? false}
              onChange={(e) => onChange({ ...flags, [f]: e.target.checked })}
              className="accent-primary"
            />
            {t(`capability.flag.${f}`)}
          </label>
        ))}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {t('capability.hint')}
      </p>
    </div>
  );
}

export { KNOWN_FLAGS };
