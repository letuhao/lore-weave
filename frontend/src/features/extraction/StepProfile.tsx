import { useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { extractionApi } from './api';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';
import type { ExtractionProfileKind, ExtractionProfile, AttributeAction } from './types';
import { cn } from '@/lib/utils';

interface StepProfileProps {
  bookId: string;
  profile: ExtractionProfile;
  modelRef: string;
  onProfileChange: (profile: ExtractionProfile) => void;
  onModelChange: (modelRef: string) => void;
  onClose: () => void;
}

export function StepProfile({
  bookId,
  profile,
  modelRef,
  onProfileChange,
  onModelChange,
  onClose,
}: StepProfileProps) {
  const { t } = useTranslation('extraction');
  const { accessToken } = useAuth();
  const [kinds, setKinds] = useState<ExtractionProfileKind[]>([]);
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedKinds, setExpandedKinds] = useState<Set<string>>(new Set());

  // Load extraction profile + models on mount
  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    Promise.all([
      extractionApi.getProfile(bookId, accessToken),
      aiModelsApi.listUserModels(accessToken).catch(() => ({ items: [] as UserModel[] })),
    ])
      .then(([profileResp, modelsResp]) => {
        setKinds(profileResp.kinds);
        setUserModels(modelsResp.items.filter((m) => m.is_active));

        // Initialize profile from auto_selected if profile is empty
        if (Object.keys(profile).length === 0) {
          const initial: ExtractionProfile = {};
          for (const kind of profileResp.kinds) {
            if (!kind.auto_selected) continue;
            const attrs: Record<string, AttributeAction> = {};
            for (const attr of kind.attributes) {
              attrs[attr.code] = attr.auto_selected ? 'fill' : 'skip';
            }
            initial[kind.code] = attrs;
          }
          onProfileChange(initial);
        }
      })
      .finally(() => setLoading(false));
  }, [accessToken, bookId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Group models by provider
  const modelsByProvider = useMemo(() => {
    const map = new Map<string, UserModel[]>();
    for (const m of userModels) {
      if (!map.has(m.provider_kind)) map.set(m.provider_kind, []);
      map.get(m.provider_kind)!.push(m);
    }
    return map;
  }, [userModels]);

  const toggleKind = (kindCode: string, kind: ExtractionProfileKind) => {
    const next = { ...profile };
    if (next[kindCode]) {
      delete next[kindCode];
    } else {
      const attrs: Record<string, AttributeAction> = {};
      for (const attr of kind.attributes) {
        attrs[attr.code] = 'fill';
      }
      next[kindCode] = attrs;
    }
    onProfileChange(next);
  };

  const setAttrAction = (kindCode: string, attrCode: string, action: AttributeAction) => {
    const next = { ...profile };
    if (!next[kindCode]) return;
    next[kindCode] = { ...next[kindCode], [attrCode]: action };
    onProfileChange(next);
  };

  const bulkAction = (kindCode: string, action: AttributeAction) => {
    const next = { ...profile };
    if (!next[kindCode]) return;
    const kind = kinds.find((k) => k.code === kindCode);
    if (!kind) return;
    const updated: Record<string, AttributeAction> = {};
    for (const attr of kind.attributes) {
      updated[attr.code] = attr.is_required ? 'fill' : action;
    }
    next[kindCode] = updated;
    onProfileChange(next);
  };

  const toggleExpand = (kindCode: string) => {
    setExpandedKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kindCode)) next.delete(kindCode);
      else next.add(kindCode);
      return next;
    });
  };

  const enabledKindsCount = Object.keys(profile).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Model selector */}
      <div>
        <label className="mb-1 block text-xs font-medium">{t('profile.model')}</label>
        {userModels.length === 0 ? (
          <div className="flex h-9 items-center rounded-md border border-dashed bg-background px-3 text-[11px] text-muted-foreground">
            {t('profile.noModels')}{' '}
            <Link to="/settings" onClick={onClose} className="ml-1 text-primary hover:underline">
              {t('profile.addInSettings')}
            </Link>
          </div>
        ) : (
          <select
            value={modelRef}
            onChange={(e) => onModelChange(e.target.value)}
            className="h-9 w-full rounded-md border bg-background px-3 text-[13px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          >
            <option value="">{t('profile.selectModel')}</option>
            {Array.from(modelsByProvider.entries()).map(([provider, models]) => (
              <optgroup key={provider} label={provider}>
                {models.map((m) => (
                  <option key={m.user_model_id} value={m.user_model_id}>
                    {m.alias || m.provider_model_name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        )}
      </div>

      {/* Kinds header */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {t('profile.kindsSelected', { count: enabledKindsCount })}
        </p>
      </div>

      {/* Kind list */}
      <div className="max-h-[400px] overflow-y-auto space-y-1 rounded-md border">
        {kinds.map((kind) => {
          const isEnabled = !!profile[kind.code];
          const isExpanded = expandedKinds.has(kind.code);
          const activeAttrs = isEnabled
            ? Object.values(profile[kind.code]).filter((a) => a !== 'skip').length
            : 0;

          return (
            <div key={kind.kind_id} className="border-b last:border-b-0">
              {/* Kind row */}
              <div className="flex items-center justify-between px-3 py-2 hover:bg-card/50">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    onChange={() => toggleKind(kind.code, kind)}
                    className="h-3.5 w-3.5 rounded border-border accent-primary"
                  />
                  <span className="text-base">{kind.icon}</span>
                  <span className="text-sm font-medium">{kind.name}</span>
                  {isEnabled && (
                    <span className="text-[10px] text-muted-foreground">
                      {t('profile.attrsSelected', { count: activeAttrs })}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  {isEnabled && (
                    <>
                      <button
                        onClick={() => bulkAction(kind.code, 'fill')}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {t('profile.allFill')}
                      </button>
                      <button
                        onClick={() => bulkAction(kind.code, 'overwrite')}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {t('profile.allOverwrite')}
                      </button>
                    </>
                  )}
                  {isEnabled && (
                    <button
                      onClick={() => toggleExpand(kind.code)}
                      className="p-0.5 rounded hover:bg-secondary text-muted-foreground"
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-3.5 w-3.5" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5" />
                      )}
                    </button>
                  )}
                </div>
              </div>

              {/* Attribute rows (expanded) */}
              {isEnabled && isExpanded && (
                <div className="ml-9 mr-3 mb-2 space-y-0.5">
                  {kind.attributes.map((attr) => {
                    const action = profile[kind.code]?.[attr.code] || 'skip';
                    return (
                      <div
                        key={attr.code}
                        className={cn(
                          'flex items-center justify-between py-1 px-2 rounded text-xs',
                          action !== 'skip' ? 'bg-card/50' : 'opacity-60',
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <span>{attr.name}</span>
                          {attr.is_required && (
                            <span className="text-[9px] px-1 py-px rounded bg-primary/10 text-primary font-medium">
                              {t('profile.required')}
                            </span>
                          )}
                          <span className="text-[10px] text-muted-foreground">{attr.field_type}</span>
                        </div>
                        <select
                          value={action}
                          onChange={(e) =>
                            setAttrAction(kind.code, attr.code, e.target.value as AttributeAction)
                          }
                          disabled={attr.is_required}
                          className={cn(
                            'rounded border bg-background px-1.5 py-0.5 text-[11px] focus:border-ring focus:outline-none',
                            attr.is_required && 'opacity-50 cursor-not-allowed',
                          )}
                        >
                          <option value="fill">{t('profile.actionFill')}</option>
                          <option value="overwrite">{t('profile.actionOverwrite')}</option>
                          <option value="skip">{t('profile.actionSkip')}</option>
                        </select>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
