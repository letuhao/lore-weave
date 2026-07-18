import { useEffect, useState, useMemo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Save, Loader2, Link2, Languages, FileText, Tag, Trash2, History, MapPin } from 'lucide-react';
import { toast } from 'sonner';
import { useGlossaryEntity } from '@/features/glossary/hooks/useGlossaryEntity';
import { _setGlossaryEntityBinding, registerGlossaryEntityDocumentProvider } from '@/features/glossary/documents/entityDocument';
import { isDisplayingTranslation, resolveEntityDisplayName } from '@/features/glossary/lib/resolveDisplayValue';
import { type AttributeValue, type Translation } from '@/features/glossary/types';
import { getLanguageName } from '@/lib/languages';
import { Skeleton } from '@/components/shared/Skeleton';
import { LanguagePicker } from '@/components/shared';
import { AttrCard } from './AttrCard';
import { AddAttributeValueSection } from './AddAttributeValueSection';
import { SummarizeAttrBody } from './SummarizeAttrBody';
import { AttrTranslationRow } from './AttrTranslationRow';
import { getCardComponent, SHORT_TYPES } from './cardRegistry';
import { EvidenceTab } from './EvidenceTab';
import { EntityHistoryPanel } from '@/features/glossary/components/EntityHistoryPanel';

type EditorTab = 'attributes' | 'evidences' | 'history';

interface EntityEditorModalProps {
  bookId: string;
  entityId: string;
  bookGenreTags?: string[];
  kindGenreTags?: string[];
  bookOriginalLanguage?: string;
  displayLanguage?: string;
  onClose: () => void;
  onSaved: () => void;
  onDelete: () => void;
  initialTab?: EditorTab;
}

export function EntityEditorModal({ bookId, entityId, bookGenreTags = [], kindGenreTags = [], bookOriginalLanguage, displayLanguage, onClose, onSaved, onDelete, initialTab = 'attributes' }: EntityEditorModalProps) {
  const { t } = useTranslation('entityEditor');
  // Tier-4 hoist (docs/standards/dockable-gui.md DOCK-10) — shared with the
  // `loreweave.glossary-entity.v1` JSON document provider (13_glossary_panels.md A2).
  const glossaryEntity = useGlossaryEntity(bookId, entityId);
  const { entity, loading, saving, isDirty, pendingChanges, getValue, discard } = glossaryEntity;
  const [activeTab, setActiveTab] = useState<EditorTab>(initialTab);
  const [translationLang, setTranslationLang] = useState('');
  // /review-impl MED fix (2026-07-09): scope_label is now a CONTROLLED input, synced
  // to the loaded entity (mount, entity switch, or post-save reload — a genuine
  // synchronization case, not event-handling). Previously it was uncontrolled
  // (defaultValue), so a REJECTED edit (e.g. a scope collision) left the input
  // showing the failed value as if it had stuck, with no re-render to correct it
  // until the whole modal remounted.
  const [scopeLabelDraft, setScopeLabelDraft] = useState('');
  useEffect(() => {
    setScopeLabelDraft(entity?.scope_label ?? '');
  }, [entity?.scope_label, entityId]);

  // 13_glossary_panels.md A2 — publish the live hook instance for the
  // `loreweave.glossary-entity.v1` JSON document provider (modal-scoped, mirrors
  // manuscript-unit's R2 binding-bridge; no persistent Tier-4 provider exists for entities).
  useEffect(() => {
    registerGlossaryEntityDocumentProvider();
    _setGlossaryEntityBinding({ api: glossaryEntity, entityId });
    return () => _setGlossaryEntityBinding(null);
  }, [glossaryEntity, entityId]);

  const viewTranslationMode = isDisplayingTranslation(displayLanguage, bookOriginalLanguage);

  useEffect(() => {
    if (viewTranslationMode && displayLanguage) {
      setTranslationLang(displayLanguage);
    }
  }, [viewTranslationMode, displayLanguage]);

  // Radix Dialog.Root handles Escape + outside-click → onOpenChange(false) → onClose below;
  // no manual keydown listener needed (DOCK-9 adoption also buys us this for free).

  const handleChange = (attrValueId: string, value: string) => glossaryEntity.setValue(attrValueId, value);

  // S-06 — remove a value ROW entirely (confirmed; distinct from blanking it to empty). The hook
  // reloads the entity so the card drops; onSaved refreshes the parent list snapshot.
  const handleRemoveAttr = async (attrValueId: string) => {
    if (!window.confirm(t('modal.remove_attr_confirm', { defaultValue: 'Remove this attribute value? You can add it again later.' }))) return;
    try {
      await glossaryEntity.removeAttributeValue(attrValueId);
      toast.success(t('modal.remove_attr_success', { defaultValue: 'Attribute value removed' }));
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const handleSave = async () => {
    try {
      await glossaryEntity.save();
      toast.success(t('modal.toast.saved'));
      onSaved();
    } catch (e) { toast.error((e as Error).message); }
  };

  const handleStatusChange = async (status: string) => {
    try {
      await glossaryEntity.setStatus(status);
      toast.success(t('modal.toast.status_changed', { status }));
      onSaved();
    } catch (e) { toast.error((e as Error).message); }
  };

  // D-GLOSSARY-ENTITY-SCOPE — commits on blur (not per-keystroke); a no-op when
  // the value is unchanged. A colliding scope surfaces the backend's specific
  // GLOSS_DUPLICATE_NAME message via the toast, same posture as save()/setStatus.
  // /review-impl MED fix (2026-07-09): on failure, revert the draft to the entity's
  // actual (unchanged) scope_label — the input must never keep showing a value
  // that was never actually persisted.
  const handleScopeLabelBlur = async (value: string) => {
    if (!entity || value === (entity.scope_label ?? '')) return;
    try {
      await glossaryEntity.setScopeLabel(value);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
      setScopeLabelDraft(entity.scope_label ?? '');
    }
  };

  const handleDiscard = () => discard();

  // Collect unique languages: book's original language + all existing translation languages.
  // Stable key: serialize translation language codes to avoid recalc on unrelated entity changes.
  // NOTE: these hooks MUST stay above the early returns below — moving them after a conditional
  // return crashes with "Rendered more hooks than during the previous render" (entity loads
  // null→data, so the early return is taken on the first render only). Null-safe on `entity`.
  const translationLangKey = (entity?.attribute_values ?? [])
    .flatMap((av) => av.translations.map((tr) => tr.language_code))
    .sort().join(',');
  const availableLanguages = useMemo(() => {
    const langs = new Set<string>();
    if (bookOriginalLanguage) langs.add(bookOriginalLanguage);
    for (const code of translationLangKey.split(',')) {
      if (code) langs.add(code);
    }
    return Array.from(langs).sort();
  }, [translationLangKey, bookOriginalLanguage]);

  // Update entity state when a translation is created/updated/deleted
  const handleTranslationChanged = (attrValueId: string, updated: Translation | null, oldTranslationId?: string) => {
    glossaryEntity.applyTranslationChange(attrValueId, updated, oldTranslationId);
    onSaved();
  };

  // ── Render ──

  const renderLoading = () => (
    <div className="p-6 space-y-4">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-8 w-full" />
    </div>
  );

  if (!entity && loading) {
    return (
      <Dialog.Root open onOpenChange={(next) => { if (!next) onClose(); }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 rounded-xl border bg-background shadow-2xl">
            <Dialog.Title className="sr-only">{t('modal.untitled')}</Dialog.Title>
            <Dialog.Description className="sr-only">{t('modal.untitled')}</Dialog.Description>
            {renderLoading()}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );
  }

  if (!entity) return null;

  // Filter attributes by genre: show if attr has no genre_tags (universal) or matches book genres
  const genreMatch = (attr: AttributeValue) => {
    const tags = attr.attribute_def.genre_tags ?? [];
    return tags.length === 0 || tags.some((gt) => bookGenreTags.includes(gt));
  };

  const sortedAttrs = [...entity.attribute_values]
    .filter(genreMatch)
    .sort((a, b) => a.attribute_def.sort_order - b.attribute_def.sort_order);
  const sysAttrs = sortedAttrs.filter((a) => a.attribute_def.is_system);
  const usrAttrs = sortedAttrs.filter((a) => !a.attribute_def.is_system);

  const headerTitle = viewTranslationMode
    ? resolveEntityDisplayName(entity.attribute_values, displayLanguage, bookOriginalLanguage)
    : entity.display_name;

  return (
    <Dialog.Root open onOpenChange={(next) => { if (!next) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 flex w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border bg-background shadow-2xl"
          style={{ maxHeight: 'calc(100vh - 48px)' }}
        >
          <Dialog.Title className="sr-only">{headerTitle || t('modal.untitled')}</Dialog.Title>
          <Dialog.Description className="sr-only">{headerTitle || t('modal.untitled')}</Dialog.Description>
          {/* ── Header ── */}
          <div className="flex items-center justify-between border-b bg-card px-6 py-4 flex-shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="font-serif text-base font-semibold truncate">{headerTitle || t('modal.untitled')}</span>
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium flex-shrink-0"
                style={{ backgroundColor: entity.kind.color + '18', color: entity.kind.color }}
              >
                {entity.kind.icon} {entity.kind.name}
              </span>
              {kindGenreTags.filter((gt) => gt !== 'universal').map((g) => (
                <span key={g} className="inline-flex items-center gap-1 rounded-full bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-medium text-violet-400 flex-shrink-0">
                  {g}
                </span>
              ))}
              <select
                value={entity.status}
                onChange={(e) => void handleStatusChange(e.target.value)}
                className="rounded border bg-background px-2 py-0.5 text-[10px] font-medium focus:outline-none flex-shrink-0"
              >
                <option value="draft">{t('modal.status.draft')}</option>
                <option value="active">{t('modal.status.active')}</option>
                <option value="inactive">{t('modal.status.inactive')}</option>
              </select>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {isDirty && (
                <button onClick={handleDiscard} className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                  {t('modal.discard')}
                </button>
              )}
              <button
                onClick={() => void handleSave()}
                disabled={saving || !isDirty}
                className="btn-glow inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all"
              >
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                {t('modal.save')}
              </button>
              <button onClick={onClose} className="rounded p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* ── Meta bar ── */}
          <div className="flex items-center gap-4 border-b px-6 py-2.5 text-[11px] text-muted-foreground flex-shrink-0" style={{ background: 'rgba(24,20,18,0.4)' }}>
            {viewTranslationMode && displayLanguage && (
              <span className="inline-flex items-center gap-1 text-blue-400">
                <Languages className="h-3 w-3" />
                {t('modal.viewing_in_language', { lang: getLanguageName(displayLanguage) })}
              </span>
            )}
            <span className="inline-flex items-center gap-1"><Link2 className="h-3 w-3" />{t('modal.meta.chapters', { count: entity.chapter_link_count })}</span>
            <span className="inline-flex items-center gap-1"><Languages className="h-3 w-3" />{t('modal.meta.translations', { count: entity.translation_count })}</span>
            <button type="button" onClick={() => setActiveTab('evidences')} className="inline-flex items-center gap-1 hover:text-primary transition-colors"><FileText className="h-3 w-3" />{t('modal.meta.evidences', { count: entity.evidence_count })}</button>
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              <input
                type="text"
                value={scopeLabelDraft}
                onChange={(e) => setScopeLabelDraft(e.target.value)}
                placeholder={t('modal.scope_label.placeholder')}
                aria-label={t('modal.scope_label.aria')}
                // Mirrors the backend's scopeLabelMaxLen (entity_attribute_edit_tools.go) —
                // /review-impl MED fix: this field had no length bound anywhere before.
                maxLength={200}
                onBlur={(e) => void handleScopeLabelBlur(e.target.value.trim())}
                className="w-40 rounded border-none bg-transparent px-1 py-0.5 text-[11px] text-muted-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
            </span>
            {entity.tags.length > 0 && (
              <>
                <span className="flex-1" />
                <span className="inline-flex items-center gap-1 text-primary"><Tag className="h-3 w-3" />{entity.tags.join(', ')}</span>
              </>
            )}
          </div>

          {/* ── Tab bar ── */}
          <div className="flex items-center gap-1 border-b px-6 flex-shrink-0">
            <button
              type="button"
              onClick={() => setActiveTab('attributes')}
              className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                activeTab === 'attributes'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t('modal.tab.attributes')}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('evidences')}
              className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                activeTab === 'evidences'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t('modal.tab.evidences')}
              {entity.evidence_count > 0 && (
                <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                  {entity.evidence_count}
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('history')}
              className={`inline-flex items-center gap-1 px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                activeTab === 'history'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <History className="h-3 w-3" />
              {t('modal.tab.history')}
            </button>
            {/* Language selector — only visible on attributes tab */}
            {activeTab === 'attributes' && !viewTranslationMode && (
              <>
                <span className="flex-1" />
                <div className="flex items-center gap-1.5">
                  <Languages className="h-3 w-3 text-muted-foreground" />
                  <select
                    value={translationLang}
                    onChange={(e) => setTranslationLang(e.target.value)}
                    className={`rounded border bg-background px-2 py-1 text-[10px] font-medium focus:outline-none transition-colors ${
                      translationLang && translationLang !== '__new' ? 'border-blue-500/40 text-blue-400' : 'text-muted-foreground'
                    }`}
                    aria-label={t('modal.translation_lang_aria')}
                  >
                    <option value="">{t('modal.no_translation')}</option>
                    {availableLanguages.map((lang) => (
                      <option key={lang} value={lang}>{lang.toUpperCase()}</option>
                    ))}
                    <option value="__new">{t('modal.add_language')}</option>
                  </select>
                  {translationLang === '__new' && (
                    <LanguagePicker
                      value=""
                      exclude={availableLanguages}
                      placeholder={t('modal.lang_placeholder')}
                      aria-label={t('modal.translation_lang_aria')}
                      className="w-28 rounded border border-blue-500/40 bg-background px-2 py-1 text-[10px] focus:outline-none"
                      onChange={(code) => {
                        if (code) setTranslationLang(code);
                        else setTranslationLang('');
                      }}
                    />
                  )}
                </div>
              </>
            )}
          </div>

          {/* ── Body (scrollable) ── */}
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
            {activeTab === 'attributes' && (
              <>
                {/* System attributes */}
                {sysAttrs.length > 0 && (
                  <>
                    <SectionLabel color="info">{t('modal.system_attrs')}</SectionLabel>
                    <AttrGrid
                      attrs={sysAttrs} getValue={getValue} onChange={handleChange}
                      pendingChanges={pendingChanges} translationLang={translationLang}
                      viewTranslationMode={viewTranslationMode}
                      displayLanguage={displayLanguage}
                      bookOriginalLanguage={bookOriginalLanguage}
                      bookId={bookId} entityId={entityId} onTranslationChanged={handleTranslationChanged}
                    />
                  </>
                )}

                {/* User attributes */}
                {usrAttrs.length > 0 && (
                  <>
                    <SectionLabel color="primary">{t('modal.user_attrs')}</SectionLabel>
                    <AttrGrid
                      attrs={usrAttrs} getValue={getValue} onChange={handleChange}
                      pendingChanges={pendingChanges} translationLang={translationLang}
                      viewTranslationMode={viewTranslationMode}
                      displayLanguage={displayLanguage}
                      bookOriginalLanguage={bookOriginalLanguage}
                      bookId={bookId} entityId={entityId} onTranslationChanged={handleTranslationChanged}
                      onRemove={handleRemoveAttr}
                    />
                  </>
                )}

                {/* S-06 — add a value for an attr-def the entity is missing (add-later). */}
                {!viewTranslationMode && entity && (
                  <AddAttributeValueSection
                    bookId={bookId}
                    entity={entity}
                    onAdd={glossaryEntity.addAttributeValue}
                    onAdded={onSaved}
                  />
                )}

                {sortedAttrs.length === 0 && (
                  <p className="py-8 text-center text-xs italic text-muted-foreground">{t('modal.no_attributes')}</p>
                )}
              </>
            )}

            {activeTab === 'evidences' && (
              <EvidenceTab
                bookId={bookId}
                entityId={entityId}
                bookOriginalLanguage={bookOriginalLanguage}
                defaultDisplayLanguage={viewTranslationMode ? displayLanguage : undefined}
                onCountChange={(delta) => {
                  glossaryEntity.bumpEvidenceCount(delta);
                  onSaved();
                }}
              />
            )}

            {activeTab === 'history' && (
              <EntityHistoryPanel
                bookId={bookId}
                entityId={entityId}
                embedded
                onRestored={() => {
                  // Restore reconciled the live entity server-side → re-fetch it,
                  // and notify the list so its row reflects the rolled-back state.
                  void glossaryEntity.reload();
                  onSaved();
                }}
              />
            )}
          </div>

          {/* ── Footer (only for attributes tab) ── */}
          {activeTab === 'attributes' && (
            <div className="flex items-center justify-between border-t bg-card px-6 py-3.5 flex-shrink-0">
              <button
                onClick={onDelete}
                className="inline-flex items-center gap-1.5 text-xs text-destructive hover:bg-destructive/8 rounded-md px-3 py-1.5 transition-colors"
              >
                <Trash2 className="h-3 w-3" />
                {t('modal.move_to_trash')}
              </button>
              <div className="flex items-center gap-2">
                <button onClick={onClose} className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                  {t('modal.cancel')}
                </button>
                <button
                  onClick={() => void handleSave()}
                  disabled={saving || !isDirty}
                  className="btn-glow inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all"
                >
                  {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                  {t('modal.save_entity')}
                </button>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// ── Helpers ──

function SectionLabel({ color, children }: { color: 'info' | 'primary'; children: ReactNode }) {
  const dotColor = color === 'info' ? 'bg-info' : 'bg-primary';
  const textColor = color === 'info' ? 'text-info' : 'text-primary';
  return (
    <div className={`flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider ${textColor}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      {children}
      <span className="flex-1 h-px bg-border" />
    </div>
  );
}

function AttrGrid({ attrs, getValue, onChange, pendingChanges, translationLang, viewTranslationMode, displayLanguage, bookOriginalLanguage, bookId, entityId, onTranslationChanged, onRemove }: {
  attrs: AttributeValue[];
  getValue: (attr: AttributeValue) => string;
  onChange: (id: string, value: string) => void;
  pendingChanges: Map<string, string>;
  translationLang: string;
  viewTranslationMode: boolean;
  displayLanguage?: string;
  bookOriginalLanguage?: string;
  bookId: string;
  entityId: string;
  onTranslationChanged: (attrValueId: string, updated: Translation | null, oldTranslationId?: string) => void;
  // S-06 — remove a value row (non-system attrs only). Absent ⇒ no remove button.
  onRemove?: (attrValueId: string) => void;
}) {
  const { t } = useTranslation('entityEditor');
  const rendered: ReactNode[] = [];
  let shortBuffer: ReactNode[] = [];

  const flushShort = () => {
    if (shortBuffer.length > 0) {
      rendered.push(
        <div key={`grid-${rendered.length}`} className="grid grid-cols-2 gap-4">
          {shortBuffer}
        </div>,
      );
      shortBuffer = [];
    }
  };

  for (const attr of attrs) {
    const def = attr.attribute_def;
    const CardComponent = getCardComponent(def.field_type);
    const isShort = SHORT_TYPES.has(def.field_type);
    const modified = pendingChanges.has(attr.attr_value_id);
    const hasTranslations = attr.translations.length > 0;

    const activeLang = viewTranslationMode && displayLanguage
      ? displayLanguage
      : translationLang && translationLang !== '__new'
        ? translationLang
        : '';
    const existingTranslation = activeLang
      ? attr.translations.find((tr) => tr.language_code === activeLang)
      : undefined;

    const translationSlot = activeLang ? (
      <AttrTranslationRow
        key={`${attr.attr_value_id}-${activeLang}`}
        bookId={bookId}
        entityId={entityId}
        attrValueId={attr.attr_value_id}
        language={activeLang}
        translation={existingTranslation}
        translationHint={def.translation_hint}
        attrCode={def.code}
        sourceOriginal={viewTranslationMode ? (getValue(attr) || undefined) : undefined}
        sourceOriginalLang={viewTranslationMode ? (bookOriginalLanguage ?? attr.original_language) : undefined}
        onChanged={(updated) => {
          onTranslationChanged(attr.attr_value_id, updated, existingTranslation?.translation_id);
        }}
      />
    ) : undefined;

    const card = (
      <AttrCard
        key={attr.attr_value_id}
        name={def.name}
        code={def.code}
        fieldType={def.field_type}
        isSystem={def.is_system}
        isRequired={def.is_required}
        modified={modified}
        hasTranslations={hasTranslations}
        translationSlot={translationSlot}
        // S-06 — only non-system attrs are removable (name/description etc. are structural).
        onRemove={!def.is_system && onRemove ? () => onRemove(attr.attr_value_id) : undefined}
      >
        {!viewTranslationMode && (
          def.merge_strategy === 'summarize' ? (
            <SummarizeAttrBody
              canonicalValue={attr.canonical_value}
              canonicalDirty={attr.canonical_dirty}
              rawValue={getValue(attr)}
              rawCard={
                <CardComponent
                  value={getValue(attr)}
                  onChange={(v) => onChange(attr.attr_value_id, v)}
                  options={def.options}
                />
              }
            />
          ) : (
            <CardComponent
              value={getValue(attr)}
              onChange={(v) => onChange(attr.attr_value_id, v)}
              options={def.options}
            />
          )
        )}
      </AttrCard>
    );

    // When translation is active, cards with translation slots go full-width;
    // short fields without a translation slot can still pair in 2-col.
    if (isShort && !translationSlot) {
      shortBuffer.push(card);
    } else {
      flushShort();
      rendered.push(card);
    }
  }
  flushShort();
  return <>{rendered}</>;
}
