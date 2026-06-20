// API layer for the System-tier standards admin (glossary-service via gateway /v1).
// All writes require an admin Bearer token; reads are normal authed GETs.
import { apiJson } from '@/api';
import type {
  AttributeCreate,
  AttributeUpdate,
  GenreCreate,
  GenreUpdate,
  KindCreate,
  KindUpdate,
  SystemAttribute,
  SystemGenre,
  SystemKind,
} from './types';

type Token = string | null;

// ---- Genres -------------------------------------------------------------

export async function listSystemGenres(token: Token): Promise<SystemGenre[]> {
  const res = await apiJson<{ items: SystemGenre[] }>(
    '/v1/glossary/genres?include_user=false',
    { token },
  );
  return (res.items ?? []).filter((g) => g.tier === undefined || g.tier === 'system');
}

export function createSystemGenre(token: Token, body: GenreCreate): Promise<SystemGenre> {
  return apiJson<SystemGenre>('/v1/glossary/system-genres', {
    method: 'POST',
    token,
    body: JSON.stringify(body),
  });
}

export function updateSystemGenre(
  token: Token,
  genreId: string,
  body: GenreUpdate,
): Promise<SystemGenre> {
  return apiJson<SystemGenre>(`/v1/glossary/system-genres/${genreId}`, {
    method: 'PATCH',
    token,
    body: JSON.stringify(body),
  });
}

export function deleteSystemGenre(token: Token, genreId: string): Promise<void> {
  return apiJson<void>(`/v1/glossary/system-genres/${genreId}`, {
    method: 'DELETE',
    token,
  });
}

// ---- Kinds --------------------------------------------------------------

export function listSystemKinds(token: Token): Promise<SystemKind[]> {
  // The kinds read returns a bare array.
  return apiJson<SystemKind[]>('/v1/glossary/kinds', { token });
}

export function createSystemKind(token: Token, body: KindCreate): Promise<SystemKind> {
  return apiJson<SystemKind>('/v1/glossary/system-kinds', {
    method: 'POST',
    token,
    body: JSON.stringify(body),
  });
}

export function updateSystemKind(
  token: Token,
  kindId: string,
  body: KindUpdate,
): Promise<SystemKind> {
  return apiJson<SystemKind>(`/v1/glossary/system-kinds/${kindId}`, {
    method: 'PATCH',
    token,
    body: JSON.stringify(body),
  });
}

export function deleteSystemKind(token: Token, kindId: string): Promise<void> {
  return apiJson<void>(`/v1/glossary/system-kinds/${kindId}`, {
    method: 'DELETE',
    token,
  });
}

// ---- Attributes ---------------------------------------------------------

export async function listSystemAttributes(
  token: Token,
  kindId: string,
  genreId: string,
): Promise<SystemAttribute[]> {
  const res = await apiJson<{ items: SystemAttribute[] }>(
    `/v1/glossary/system-attributes?kind_id=${encodeURIComponent(kindId)}&genre_id=${encodeURIComponent(genreId)}`,
    { token },
  );
  return res.items ?? [];
}

export function createSystemAttribute(
  token: Token,
  body: AttributeCreate,
): Promise<SystemAttribute> {
  return apiJson<SystemAttribute>('/v1/glossary/system-attributes-admin', {
    method: 'POST',
    token,
    body: JSON.stringify(body),
  });
}

export function updateSystemAttribute(
  token: Token,
  attrId: string,
  body: AttributeUpdate,
): Promise<SystemAttribute> {
  return apiJson<SystemAttribute>(`/v1/glossary/system-attributes-admin/${attrId}`, {
    method: 'PATCH',
    token,
    body: JSON.stringify(body),
  });
}

export function deleteSystemAttribute(token: Token, attrId: string): Promise<void> {
  return apiJson<void>(`/v1/glossary/system-attributes-admin/${attrId}`, {
    method: 'DELETE',
    token,
  });
}
