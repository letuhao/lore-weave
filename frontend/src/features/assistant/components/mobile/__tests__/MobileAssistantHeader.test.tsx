// DF2 — the mobile assistant header: greeting + the "noticed" chips from the shared capture rail.
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/auth', () => ({ useAuth: () => ({ user: { display_name: 'Hao', email: 'hao@x.dev' } }) }));

const captureRail = { entities: [] as unknown[], loading: false, refresh: vi.fn() };
vi.mock('../../../context/AssistantContext', () => ({ useAssistant: () => ({ captureRail }) }));

import { MobileAssistantHeader } from '../MobileAssistantHeader';

describe('MobileAssistantHeader', () => {
  it('renders the greeting with the user name', () => {
    captureRail.entities = [];
    render(<MobileAssistantHeader />);
    expect(screen.getByText(/, Hao/)).toBeTruthy();
    expect(screen.getByText('Assistant')).toBeTruthy();
  });

  it('shows the noticed chips when the capture rail has entities', () => {
    captureRail.entities = [
      { entity_id: 'e1', display_name: 'Minh', kind: { code: 'colleague', name: 'Colleague' } },
      { entity_id: 'e2', display_name: 'Q3 Billing', kind: { code: 'project', name: 'Project' } },
    ];
    render(<MobileAssistantHeader />);
    expect(screen.getByTestId('assistant-noticed-strip')).toBeTruthy();
    expect(screen.getByText('Minh')).toBeTruthy();
    expect(screen.getByText('Q3 Billing')).toBeTruthy();
  });

  it('omits the noticed strip when nothing is captured', () => {
    captureRail.entities = [];
    render(<MobileAssistantHeader />);
    expect(screen.queryByTestId('assistant-noticed-strip')).toBeNull();
  });
});
