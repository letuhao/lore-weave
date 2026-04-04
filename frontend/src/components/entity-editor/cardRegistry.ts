import type { ComponentType } from 'react';
import type { AttrFieldProps } from './AttrTextCard';
import { AttrTextCard } from './AttrTextCard';
import { AttrTextareaCard } from './AttrTextareaCard';
import { AttrNumberCard } from './AttrNumberCard';
import { AttrDateCard } from './AttrDateCard';
import { AttrSelectCard } from './AttrSelectCard';
import { AttrBooleanCard } from './AttrBooleanCard';
import { AttrUrlCard } from './AttrUrlCard';
import { AttrTagsCard } from './AttrTagsCard';

/**
 * Map field_type → card component.
 * To add a new attribute type, create AttrXxxCard and add it here.
 * Unknown types fall back to AttrTextCard.
 */
export const CARD_REGISTRY: Record<string, ComponentType<AttrFieldProps>> = {
  text: AttrTextCard,
  textarea: AttrTextareaCard,
  number: AttrNumberCard,
  date: AttrDateCard,
  select: AttrSelectCard,
  boolean: AttrBooleanCard,
  url: AttrUrlCard,
  tags: AttrTagsCard,
};

/** Types that render narrow and can pair in 2-column grids */
export const SHORT_TYPES = new Set(['text', 'number', 'date', 'select', 'boolean', 'url']);

export function getCardComponent(fieldType: string): ComponentType<AttrFieldProps> {
  return CARD_REGISTRY[fieldType] ?? AttrTextCard;
}
