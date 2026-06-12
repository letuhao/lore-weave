import type { AttributeValue, Translation } from '../types';

/** Resolve attribute text for glossary display: translation if non-empty, else original. */
export function resolveAttrValue(
  attr: Pick<AttributeValue, 'original_value' | 'translations'>,
  displayLang: string | undefined,
  originalLang: string | undefined,
): string {
  if (!displayLang || !originalLang || displayLang === originalLang) {
    return attr.original_value ?? '';
  }
  const tr = attr.translations.find(
    (t) => t.language_code === displayLang && t.value.trim() !== '',
  );
  return tr?.value ?? attr.original_value ?? '';
}

/** Resolve entity display name from name/term attributes. */
export function resolveEntityDisplayName(
  attributeValues: AttributeValue[],
  displayLang: string | undefined,
  originalLang: string | undefined,
): string {
  const nameAttr = attributeValues.find((av) =>
    ['name', 'term'].includes(av.attribute_def.code),
  );
  if (!nameAttr) return '';
  return resolveAttrValue(nameAttr, displayLang, originalLang);
}

/** True when a non-empty translation exists for the display language. */
export function hasTranslationForLang(
  translations: Translation[],
  displayLang: string,
): boolean {
  return translations.some(
    (t) => t.language_code === displayLang && t.value.trim() !== '',
  );
}
