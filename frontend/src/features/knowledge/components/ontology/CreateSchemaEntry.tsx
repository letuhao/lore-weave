import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { FilePlus2, Copy, Download } from 'lucide-react';
import type { BlankSchemaCreate, CloneSchemaRequest, GraphSchemaSummary } from '../../types/ontology';

// The "no project schema yet" entry point (A2). Three ways to START authoring:
// create a BLANK schema, CLONE a template into an editable copy, or ADOPT a
// template (glossary-gated — lives on the book Ontology tab). Renders on the KG
// project surface so a human can define a schema from scratch (the core gap).

interface Props {
  bookId: string | null;
  templates: GraphSchemaSummary[];
  createBlank: (body: BlankSchemaCreate) => Promise<unknown>;
  clone: (body: CloneSchemaRequest) => Promise<unknown>;
  busy?: boolean;
}

export function CreateSchemaEntry({ bookId, templates, createBlank, clone, busy }: Props) {
  const { t } = useTranslation('knowledge');
  const [name, setName] = useState('');
  const [cloneId, setCloneId] = useState('');

  const guard = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast.success(ok);
    } catch (e) {
      const msg = (e as { status?: number }).status === 403
        ? t('schemaSection.forbidden')
        : (e as Error).message;
      toast.error(msg || t('schemaSection.createFailed'));
    }
  };

  return (
    <div className="space-y-3" data-testid="create-schema-entry">
      <p className="text-[12px] text-muted-foreground">{t('schemaSection.emptyHelp')}</p>

      <div className="grid gap-3 sm:grid-cols-3">
        {/* new blank */}
        <div className="space-y-2 rounded-lg border p-3">
          <h4 className="flex items-center gap-1.5 text-[12px] font-semibold">
            <FilePlus2 className="h-3.5 w-3.5" /> {t('schemaSection.newBlank')}
          </h4>
          <input value={name} onChange={(e) => setName(e.target.value)}
            placeholder={t('schemaSection.schemaNamePlaceholder')}
            className="w-full rounded-md border bg-input px-2 py-1 text-[12px]"
            data-testid="blank-schema-name" />
          <button type="button" disabled={busy || !name.trim()}
            onClick={() => { void guard(() => createBlank({ name: name.trim() }), t('schemaSection.created')); setName(''); }}
            className="w-full rounded-md bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground disabled:opacity-50"
            data-testid="create-blank-schema">{t('schemaSection.createBlankButton')}</button>
        </div>

        {/* clone template */}
        <div className="space-y-2 rounded-lg border p-3">
          <h4 className="flex items-center gap-1.5 text-[12px] font-semibold">
            <Copy className="h-3.5 w-3.5" /> {t('schemaSection.cloneTemplate')}
          </h4>
          <select value={cloneId} onChange={(e) => setCloneId(e.target.value)}
            className="w-full rounded-md border bg-input px-2 py-1 text-[12px]"
            data-testid="clone-template-select">
            <option value="">{t('schemaSection.pickTemplate')}</option>
            {templates.map((s) => (
              <option key={s.schema_id} value={s.schema_id}>{s.name} ({s.scope})</option>
            ))}
          </select>
          <button type="button" disabled={busy || !cloneId}
            onClick={() => { void guard(() => clone({ source_schema_id: cloneId }), t('schemaSection.cloned')); setCloneId(''); }}
            className="w-full rounded-md border px-3 py-1.5 text-[12px] font-medium disabled:opacity-50"
            data-testid="clone-template-button">{t('schemaSection.cloneButton')}</button>
        </div>

        {/* adopt (glossary-gated — on the book Ontology tab) */}
        <div className="space-y-2 rounded-lg border p-3">
          <h4 className="flex items-center gap-1.5 text-[12px] font-semibold">
            <Download className="h-3.5 w-3.5" /> {t('schemaSection.adoptTemplate')}
          </h4>
          <p className="text-[11px] text-muted-foreground">{t('schemaSection.adoptHelp')}</p>
          {bookId ? (
            <Link to={`/books/${bookId}/kg-ontology?view=adopt`}
              className="block w-full rounded-md border px-3 py-1.5 text-center text-[12px] font-medium hover:bg-muted/40"
              data-testid="adopt-template-cta">{t('schemaSection.adoptCta')}</Link>
          ) : (
            <p className="text-[11px] text-muted-foreground">{t('schemaSection.adoptBooklessHint')}</p>
          )}
        </div>
      </div>
    </div>
  );
}
