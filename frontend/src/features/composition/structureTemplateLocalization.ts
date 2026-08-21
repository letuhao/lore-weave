import type { TFunction } from 'i18next';
import type { Beat, StructureTemplate } from './types';

export function localizedTemplateName(t: TFunction, template: Pick<StructureTemplate, 'name' | 'kind' | 'owner_user_id'>): string {
  if (template.owner_user_id != null) return template.name;
  return t('structureTemplates.templates.' + (template.kind ?? ''), { defaultValue: template.name });
}

export function localizedTemplateKind(t: TFunction, template: Pick<StructureTemplate, 'kind' | 'owner_user_id'>): string {
  if (template.owner_user_id != null) return template.kind ?? '';
  return t('structureTemplates.kinds.' + (template.kind ?? ''), { defaultValue: template.kind ?? '' });
}

export function localizedBeat(t: TFunction, template: Pick<StructureTemplate, 'kind' | 'owner_user_id'>, beat: Beat): Beat {
  if (template.owner_user_id != null) return beat;
  const base = 'structureTemplates.beats.' + (template.kind ?? '') + '.' + beat.key;
  return {
    ...beat,
    label: t(base + '.label', { defaultValue: beat.label ?? beat.key }),
    purpose: t(base + '.purpose', { defaultValue: beat.purpose ?? '' }),
  };
}
