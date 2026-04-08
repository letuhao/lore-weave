import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { glossaryApi } from '@/features/glossary/api';
import type { GlossaryEntity } from '@/features/glossary/types';

type Props = {
  bookId: string;
};

export function GlossaryTooltip({ bookId }: Props) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('glossaryEditor');
  const [tooltip, setTooltip] = useState<{
    entityId: string;
    x: number;
    y: number;
    entity?: GlossaryEntity;
    loading: boolean;
  } | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout>>();
  const tooltipRef = useRef<HTMLDivElement>(null);

  const handleMouseOver = useCallback(
    (e: MouseEvent) => {
      const target = (e.target as HTMLElement).closest('.glossary-mark') as HTMLElement | null;
      if (!target) return;

      clearTimeout(hideTimer.current);
      const entityId = target.dataset.entityId;
      if (!entityId) return;

      const rect = target.getBoundingClientRect();
      setTooltip({ entityId, x: rect.left, y: rect.top - 8, loading: true });

      if (accessToken) {
        glossaryApi
          .getEntity(bookId, entityId, accessToken)
          .then((entity) => {
            setTooltip((prev) =>
              prev?.entityId === entityId ? { ...prev, entity, loading: false } : prev,
            );
          })
          .catch(() => {
            setTooltip((prev) =>
              prev?.entityId === entityId ? { ...prev, loading: false } : prev,
            );
          });
      }
    },
    [bookId, accessToken],
  );

  const handleMouseOut = useCallback((e: MouseEvent) => {
    const related = e.relatedTarget as HTMLElement | null;
    if (related?.closest('.glossary-tooltip') || related?.closest('.glossary-mark')) return;
    hideTimer.current = setTimeout(() => setTooltip(null), 200);
  }, []);

  useEffect(() => {
    document.addEventListener('mouseover', handleMouseOver);
    document.addEventListener('mouseout', handleMouseOut);
    return () => {
      document.removeEventListener('mouseover', handleMouseOver);
      document.removeEventListener('mouseout', handleMouseOut);
      clearTimeout(hideTimer.current);
    };
  }, [handleMouseOver, handleMouseOut]);

  if (!tooltip) return null;

  const { entity, loading, x, y } = tooltip;
  const kindColor = entity?.kind?.color || '#9e9488';

  // Find the "name" attribute value for translation display
  const nameAttr = entity?.attribute_values?.find(
    (av) => av.attribute_def?.code === 'name',
  );
  const translations = nameAttr?.translations || [];

  // Get first 3 non-name attributes for preview
  const previewAttrs = (entity?.attribute_values || [])
    .filter((av) => av.attribute_def?.code !== 'name' && av.original_value)
    .slice(0, 3);

  return (
    <div
      ref={tooltipRef}
      className="glossary-tooltip fixed z-[100] w-[300px] rounded-lg border bg-card shadow-xl"
      style={{ left: x, top: y, transform: 'translateY(-100%)' }}
      onMouseEnter={() => clearTimeout(hideTimer.current)}
      onMouseLeave={() => setTooltip(null)}
    >
      {loading ? (
        <div className="p-4 text-center text-xs text-muted-foreground">{t('loading')}</div>
      ) : entity ? (
        <div className="p-3.5">
          <div className="flex gap-2.5 items-start">
            {/* Kind icon */}
            <div
              className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[10px]"
              style={{ background: `${kindColor}15`, color: kindColor }}
            >
              {entity.kind?.icon || '?'}
            </div>
            <div className="flex-1 min-w-0">
              {/* Name + kind badge */}
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-sm font-semibold truncate">{entity.display_name}</span>
                <span
                  className="text-[10px] px-1.5 py-px rounded"
                  style={{ background: `${kindColor}15`, color: kindColor }}
                >
                  {entity.kind?.name}
                </span>
              </div>

              {/* Translation names */}
              {translations.length > 0 && (
                <p className="text-[11px] text-muted-foreground mb-2">
                  {translations.map((tr) => tr.value).join(' · ')}
                </p>
              )}

              {/* Key attributes */}
              {previewAttrs.length > 0 && (
                <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px]">
                  {previewAttrs.map((av) => (
                    <React.Fragment key={av.attr_value_id}>
                      <span className="text-muted-foreground">{av.attribute_def?.name}</span>
                      <span className="truncate">{av.original_value}</span>
                    </React.Fragment>
                  ))}
                </div>
              )}

              {/* Chapter appearances */}
              {entity.chapter_links && entity.chapter_links.length > 0 && (
                <div className="mt-2 pt-2 border-t flex items-center gap-1.5 text-[10px] text-muted-foreground flex-wrap">
                  <span>{t('appearsIn')}:</span>
                  {entity.chapter_links.slice(0, 5).map((cl) => (
                    <span
                      key={cl.link_id}
                      className="px-1 py-px rounded bg-secondary font-mono"
                    >
                      {cl.chapter_title || `Ch.${cl.chapter_index ?? '?'}`}
                    </span>
                  ))}
                  {entity.chapter_links.length > 5 && (
                    <span className="px-1 py-px rounded bg-secondary font-mono">
                      +{entity.chapter_links.length - 5}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
