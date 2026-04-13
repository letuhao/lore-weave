import { useEffect, useState, useMemo, useCallback, type ReactNode } from 'react';
import { X, Save, Loader2, Link2, Languages, FileText, Tag, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import { type GlossaryEntity, type AttributeValue, type Translation } from '@/features/glossary/types';
import { Skeleton } from '@/components/shared/Skeleton';
import { AttrCard } from './AttrCard';
import { AttrTranslationRow } from './AttrTranslationRow';
import { getCardComponent, SHORT_TYPES } from './cardRegistry';
import { EvidenceTab } from './EvidenceTab';

type EditorTab = 'attributes' | 'evidences';

interface EntityEditorModalProps {
  bookId: string;
  entityId: string;
  bookGenreTags?: string[];
  kindGenreTags?: string[];
  bookOriginalLanguage?: string;
  onClose: () => void;
  onSaved: () => void;
  onDelete: () => void;
  initialTab?: EditorTab;
}

export function EntityEditorModal({ bookId, entityId, bookGenreTags = [], kindGenreTags = [], bookOriginalLanguage, onClose, onSaved, onDelete, initialTab = 'attributes' }: EntityEditorModalProps) {
  const { accessToken } = useAuth();
  const [entity, setEntity] = useState<GlossaryEntity | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [pendingChanges, setPendingChanges] = useState<Map<string, string>>(new Map());
  const [activeTab, setActiveTab] = useState<EditorTab>(initialTab);
  const [translationLang, setTranslationLang] = useState('');

  const load = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const e = await glossaryApi.getEntity(bookId, entityId, accessToken);
      setEntity(e);
      setPendingChanges(new Map());
    } catch (e) { toast.error((e as Error).message); }
    setLoading(false);
  }, [accessToken, bookId, entityId]);

  useEffect(() => { void load(); }, [load]);

  // Esc to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const handleChange = (attrValueId: string, value: string) => {
    setPendingChanges((prev) => new Map(prev).set(attrValueId, value));
  };

  const getValue = (attr: AttributeValue): string => {
    return pendingChanges.get(attr.attr_value_id) ?? attr.original_value ?? '';
  };

  const isDirty = pendingChanges.size > 0;

  const handleSave = async () => {
    if (!accessToken || !entity || !isDirty) return;
    setSaving(true);
    try {
      for (const [attrValueId, value] of pendingChanges) {
        await glossaryApi.patchAttributeValue(bookId, entityId, attrValueId, { original_value: value }, accessToken);
      }
      toast.success('Entity saved');
      setPendingChanges(new Map());
      onSaved();
      await load();
    } catch (e) { toast.error((e as Error).message); }
    setSaving(false);
  };

  const handleStatusChange = async (status: string) => {
    if (!accessToken || !entity) return;
    try {
      await glossaryApi.patchEntity(bookId, entityId, { status }, accessToken);
      toast.success(`Status changed to ${status}`);
      await load();
      onSaved();
    } catch (e) { toast.error((e as Error).message); }
  };

  const handleDiscard = () => {
    setPendingChanges(new Map());
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
      <>
        <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <div className="w-full max-w-3xl rounded-xl border bg-background shadow-2xl">
            {renderLoading()}
          </div>
        </div>
      </>
    );
  }

  if (!entity) return null;

  // Filter attributes by genre: show if attr has no genre_tags (universal) or matches book genres
  const genreMatch = (attr: AttributeValue) => {
    const tags = attr.attribute_def.genre_tags ?? [];
    return tags.length === 0 || tags.some((t) => bookGenreTags.includes(t));
  };

  const sortedAttrs = [...entity.attribute_values]
    .filter(genreMatch)
    .sort((a, b) => a.attribute_def.sort_order - b.attribute_def.sort_order);
  const sysAttrs = sortedAttrs.filter((a) => a.attribute_def.is_system);
  const usrAttrs = sortedAttrs.filter((a) => !a.attribute_def.is_system);

  // Collect unique languages: book's original language + all existing translation languages
  // Stable key: serialize translation language codes to avoid recalc on unrelated entity changes
  const translationLangKey = entity.attribute_values
    .flatMap((av) => av.translations.map((t) => t.language_code))
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
  const handleTranslationChanged = useCallback((attrValueId: string, updated: Translation | null, oldTranslationId?: string) => {
    setEntity((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        translation_count: prev.translation_count + (updated && !oldTranslationId ? 1 : !updated && oldTranslationId ? -1 : 0),
        attribute_values: prev.attribute_values.map((av) => {
          if (av.attr_value_id !== attrValueId) return av;
          let translations: Translation[];
          if (updated) {
            const idx = av.translations.findIndex((t) => t.translation_id === updated.translation_id);
            if (idx >= 0) {
              translations = [...av.translations];
              translations[idx] = updated;
            } else {
              translations = [...av.translations, updated];
            }
          } else {
            translations = av.translations.filter((t) => t.translation_id !== oldTranslationId);
          }
          return { ...av, translations };
        }),
      };
    });
    onSaved();
  }, [onSaved]);

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
        <div
          className="flex w-full max-w-3xl flex-col overflow-hidden rounded-xl border bg-background shadow-2xl"
          style={{ maxHeight: 'calc(100vh - 48px)' }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* ── Header ── */}
          <div className="flex items-center justify-between border-b bg-card px-6 py-4 flex-shrink-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="font-serif text-base font-semibold truncate">{entity.display_name || 'Untitled'}</span>
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium flex-shrink-0"
                style={{ backgroundColor: entity.kind.color + '18', color: entity.kind.color }}
              >
                {entity.kind.icon} {entity.kind.name}
              </span>
              {kindGenreTags.filter((t) => t !== 'universal').map((g) => (
                <span key={g} className="inline-flex items-center gap-1 rounded-full bg-violet-500/15 px-1.5 py-0.5 text-[9px] font-medium text-violet-400 flex-shrink-0">
                  {g}
                </span>
              ))}
              <select
                value={entity.status}
                onChange={(e) => void handleStatusChange(e.target.value)}
                className="rounded border bg-background px-2 py-0.5 text-[10px] font-medium focus:outline-none flex-shrink-0"
              >
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {isDirty && (
                <button onClick={handleDiscard} className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                  Discard
                </button>
              )}
              <button
                onClick={() => void handleSave()}
                disabled={saving || !isDirty}
                className="btn-glow inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all"
              >
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                Save
              </button>
              <button onClick={onClose} className="rounded p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* ── Meta bar ── */}
          <div className="flex items-center gap-4 border-b px-6 py-2.5 text-[11px] text-muted-foreground flex-shrink-0" style={{ background: 'rgba(24,20,18,0.4)' }}>
            <span className="inline-flex items-center gap-1"><Link2 className="h-3 w-3" />{entity.chapter_link_count} chapters</span>
            <span className="inline-flex items-center gap-1"><Languages className="h-3 w-3" />{entity.translation_count} translations</span>
            <button type="button" onClick={() => setActiveTab('evidences')} className="inline-flex items-center gap-1 hover:text-primary transition-colors"><FileText className="h-3 w-3" />{entity.evidence_count} evidences</button>
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
              Attributes
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
              Evidences
              {entity.evidence_count > 0 && (
                <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                  {entity.evidence_count}
                </span>
              )}
            </button>
            {/* Language selector — only visible on attributes tab */}
            {activeTab === 'attributes' && (
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
                    aria-label="Translation language"
                  >
                    <option value="">No translation</option>
                    {availableLanguages.map((lang) => (
                      <option key={lang} value={lang}>{lang.toUpperCase()}</option>
                    ))}
                    <option value="__new">+ Add language...</option>
                  </select>
                  {translationLang === '__new' && (
                    <input
                      autoFocus
                      type="text"
                      placeholder="e.g. en"
                      maxLength={5}
                      pattern="[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?"
                      className="w-16 rounded border border-blue-500/40 bg-background px-2 py-1 text-[10px] focus:outline-none"
                      onBlur={(e) => {
                        const v = e.target.value.trim().toLowerCase();
                        if (v && /^[a-z]{2,3}(-[a-z]{2,4})?$/.test(v)) {
                          setTranslationLang(v);
                        } else {
                          if (v) toast.error('Invalid language code (e.g. en, zh, zh-tw)');
                          setTranslationLang('');
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          (e.target as HTMLInputElement).blur();
                        } else if (e.key === 'Escape') {
                          setTranslationLang('');
                        }
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
                    <SectionLabel color="info">System Attributes</SectionLabel>
                    <AttrGrid
                      attrs={sysAttrs} getValue={getValue} onChange={handleChange}
                      pendingChanges={pendingChanges} translationLang={translationLang}
                      bookId={bookId} entityId={entityId} onTranslationChanged={handleTranslationChanged}
                    />
                  </>
                )}

                {/* User attributes */}
                {usrAttrs.length > 0 && (
                  <>
                    <SectionLabel color="primary">User Attributes</SectionLabel>
                    <AttrGrid
                      attrs={usrAttrs} getValue={getValue} onChange={handleChange}
                      pendingChanges={pendingChanges} translationLang={translationLang}
                      bookId={bookId} entityId={entityId} onTranslationChanged={handleTranslationChanged}
                    />
                  </>
                )}

                {sortedAttrs.length === 0 && (
                  <p className="py-8 text-center text-xs italic text-muted-foreground">No attributes defined for this entity kind.</p>
                )}
              </>
            )}

            {activeTab === 'evidences' && (
              <EvidenceTab
                bookId={bookId}
                entityId={entityId}
                bookOriginalLanguage={bookOriginalLanguage}
                onCountChange={(delta) => {
                  if (!entity) return;
                  setEntity({ ...entity, evidence_count: entity.evidence_count + delta });
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
                Move to Trash
              </button>
              <div className="flex items-center gap-2">
                <button onClick={onClose} className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors">
                  Cancel
                </button>
                <button
                  onClick={() => void handleSave()}
                  disabled={saving || !isDirty}
                  className="btn-glow inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all"
                >
                  {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                  Save Entity
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
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

function AttrGrid({ attrs, getValue, onChange, pendingChanges, translationLang, bookId, entityId, onTranslationChanged }: {
  attrs: AttributeValue[];
  getValue: (attr: AttributeValue) => string;
  onChange: (id: string, value: string) => void;
  pendingChanges: Map<string, string>;
  translationLang: string;
  bookId: string;
  entityId: string;
  onTranslationChanged: (attrValueId: string, updated: Translation | null, oldTranslationId?: string) => void;
}) {
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

    // Find existing translation for selected language
    const activeLang = translationLang && translationLang !== '__new' ? translationLang : '';
    const existingTranslation = activeLang
      ? attr.translations.find((t) => t.language_code === activeLang)
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
      >
        <CardComponent
          value={getValue(attr)}
          onChange={(v) => onChange(attr.attr_value_id, v)}
          options={def.options}
        />
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
