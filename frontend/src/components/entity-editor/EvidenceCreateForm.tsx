import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { EvidenceType, EvidenceFilterOption, CreateEvidencePayload } from '@/features/glossary/types';

const EVIDENCE_TYPES: EvidenceType[] = ['quote', 'summary', 'reference'];

interface EvidenceCreateFormProps {
  availAttrs: EvidenceFilterOption[];
  saving: boolean;
  onSave: (attrValueId: string, payload: CreateEvidencePayload) => Promise<boolean | undefined>;
  onCancel: () => void;
}

export function EvidenceCreateForm({ availAttrs, saving, onSave, onCancel }: EvidenceCreateFormProps) {
  const [attrValueId, setAttrValueId] = useState(availAttrs[0]?.attr_value_id ?? '');
  const [form, setForm] = useState<CreateEvidencePayload>({
    evidence_type: 'quote',
    original_text: '',
    block_or_line: '',
  });

  const handleSave = async () => {
    const ok = await onSave(attrValueId, form);
    if (ok) {
      setForm({ evidence_type: 'quote', original_text: '', block_or_line: '' });
    }
  };

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="text-xs font-semibold text-primary">New Evidence</div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] text-muted-foreground">Attribute *</label>
          <select
            value={attrValueId}
            onChange={(e) => setAttrValueId(e.target.value)}
            className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
            aria-label="Attribute for new evidence"
          >
            {availAttrs.map((a) => (
              <option key={a.attr_value_id} value={a.attr_value_id}>{a.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-[10px] text-muted-foreground">Type</label>
          <select
            value={form.evidence_type}
            onChange={(e) => setForm({ ...form, evidence_type: e.target.value as EvidenceType })}
            className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
            aria-label="Evidence type"
          >
            {EVIDENCE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="text-[10px] text-muted-foreground">Original Text *</label>
        <textarea
          value={form.original_text}
          onChange={(e) => setForm({ ...form, original_text: e.target.value })}
          rows={3}
          className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none resize-y"
          placeholder="Paste the source text..."
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] text-muted-foreground">Block / Line</label>
          <input
            value={form.block_or_line ?? ''}
            onChange={(e) => setForm({ ...form, block_or_line: e.target.value })}
            className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
            placeholder="e.g. p.42"
          />
        </div>
        <div>
          <label className="text-[10px] text-muted-foreground">Note</label>
          <input
            value={form.note ?? ''}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
            className="w-full rounded border bg-background px-2 py-1.5 text-xs focus:outline-none"
            placeholder="Optional note"
          />
        </div>
      </div>
      <div className="flex items-center gap-2 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border px-3 py-1 text-xs text-muted-foreground hover:bg-secondary transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={saving || !form.original_text?.trim()}
          className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving && <Loader2 className="h-3 w-3 animate-spin" />}
          Create
        </button>
      </div>
    </div>
  );
}
