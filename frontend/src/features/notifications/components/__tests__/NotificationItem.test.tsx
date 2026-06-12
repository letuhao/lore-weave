import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { NotificationItem } from '../NotificationItem';
import type { Notification } from '../api';

// Mock i18n with a small dictionary + interpolation so we can assert the
// client-side localization (not the stored English title).
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) => {
      const dict: Record<string, string> = {
        'event.operation.entity_extraction': 'エンティティ抽出',
        'event.status.completed': '完了',
      };
      if (k === 'event.title') return `${opts?.op}${opts?.status}`;
      if (k === 'notif.translation.complete') return `翻訳完了 — ${opts?.count}章「${opts?.book}」`;
      if (k in dict) return dict[k];
      return (opts?.defaultValue as string) ?? k;
    },
  }),
}));

const mk = (over: Partial<Notification> = {}): Notification => ({
  id: '1', category: 'system', title: 'STORED EN TITLE', body: '', metadata: {},
  read: true, created_at: new Date().toISOString(), ...over,
});

describe('NotificationItem — client-side i18n', () => {
  it('Phase 1: localizes title from metadata.operation + status (ignores stored EN)', () => {
    render(<NotificationItem notification={mk({ metadata: { operation: 'entity_extraction', status: 'completed' } })} />);
    expect(screen.getByText('エンティティ抽出完了')).toBeTruthy();
    expect(screen.queryByText('STORED EN TITLE')).toBeNull();
  });

  it('unknown operation falls back to humanized op (defaultValue)', () => {
    render(<NotificationItem notification={mk({ metadata: { operation: 'mystery_op', status: 'completed' } })} />);
    // op key missing → humanize('mystery_op')='Mystery op'; status 'completed' → '完了'
    expect(screen.getByText('Mystery op完了')).toBeTruthy();
  });

  it('Phase 2: prefers metadata.i18n_key with params', () => {
    render(<NotificationItem notification={mk({ metadata: { i18n_key: 'notif.translation.complete', i18n_params: { count: 5, book: 'Dracula' } } })} />);
    expect(screen.getByText('翻訳完了 — 5章「Dracula」')).toBeTruthy();
  });

  it('no metadata → falls back to the stored title', () => {
    render(<NotificationItem notification={mk({ title: 'Plain title' })} />);
    expect(screen.getByText('Plain title')).toBeTruthy();
  });
});
