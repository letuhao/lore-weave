import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PersonaPicker } from '../components/PersonaPicker';
import type { InterviewSetup } from '../hooks/useInterviewSetup';
import type { SessionTemplate } from '../types';
import type { UserModel } from '@/features/ai-models/api';

function tpl(over: Partial<SessionTemplate> = {}): SessionTemplate {
  return {
    template_id: 't1',
    owner_user_id: null,
    tier: 'system',
    code: 'faang_swe',
    name: 'FAANG SWE Interview',
    description: 'A senior SWE loop',
    system_prompt: 'You are an interviewer',
    model_source: null,
    model_ref: null,
    scenario: { goal: 'g', phases: ['warmup', 'coding', 'wrap'], checklist: ['a', 'b'], time_budget_min: 45, language: 'en' },
    rubric: null,
    is_active: true,
    created_at: '',
    updated_at: '',
    ...over,
  };
}

function model(over: Partial<UserModel> = {}): UserModel {
  return {
    user_model_id: 'm1',
    provider_credential_id: 'c1',
    provider_kind: 'lm_studio',
    provider_model_name: 'qwen2.5-7b',
    alias: 'Qwen 7B',
    is_active: true,
    is_favorite: false,
    tags: [],
    created_at: '',
    ...over,
  };
}

function makeSetup(over: Partial<InterviewSetup> = {}): InterviewSetup {
  return {
    templates: [tpl()],
    models: [model()],
    loading: false,
    selectedTemplateId: 't1',
    selectedModelId: 'm1',
    selectTemplate: vi.fn(),
    selectModel: vi.fn(),
    starting: false,
    canStart: true,
    start: vi.fn(),
    ...over,
  };
}

describe('PersonaPicker', () => {
  it('lists templates with a default badge for System tier', () => {
    render(<PersonaPicker setup={makeSetup()} onStart={vi.fn()} />);
    expect(screen.getByText('FAANG SWE Interview')).toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText(/3 phases · 2 checkpoints · ~45 min/)).toBeInTheDocument();
  });

  it('selecting a template calls the controller', () => {
    const setup = makeSetup({ templates: [tpl(), tpl({ template_id: 't2', name: 'Behavioral', tier: 'user', owner_user_id: 'u' })] });
    render(<PersonaPicker setup={setup} onStart={vi.fn()} />);
    fireEvent.click(screen.getByText('Behavioral'));
    expect(setup.selectTemplate).toHaveBeenCalledWith('t2');
  });

  it('disables Start until canStart and fires onStart', () => {
    const onStart = vi.fn();
    const { rerender } = render(<PersonaPicker setup={makeSetup({ canStart: false })} onStart={onStart} />);
    const btn = screen.getByText('Start practice').closest('button')!;
    expect(btn).toBeDisabled();
    rerender(<PersonaPicker setup={makeSetup({ canStart: true })} onStart={onStart} />);
    fireEvent.click(screen.getByText('Start practice'));
    expect(onStart).toHaveBeenCalledOnce();
  });

  it('shows the no-model hint when the user has no chat model', () => {
    render(<PersonaPicker setup={makeSetup({ models: [], selectedModelId: null })} onStart={vi.fn()} />);
    expect(screen.getByText(/No chat-capable model/)).toBeInTheDocument();
  });

  it('renders a loading state', () => {
    render(<PersonaPicker setup={makeSetup({ loading: true })} onStart={vi.fn()} />);
    expect(screen.getByText(/Loading personas/)).toBeInTheDocument();
  });
});
