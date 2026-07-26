// Skill editor dock panel (§13b · PANEL-1) — singleton; retargets via params
// {skillId} (json-editor precedent). Hidden from palette + outside the agent enum:
// opened only by an "Edit skill" affordance. Minimal P1 editor (description + body).
import { useEffect, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useAuth } from '@/auth';
import { extensionsApi } from '@/features/extensions/api';
import type { Skill, SkillStatus } from '@/features/extensions/types';
import { useStudioPanel } from './useStudioPanel';

export function SkillEditorPanel(props: IDockviewPanelProps) {
  useStudioPanel('skill-editor', props.api);
  const { accessToken } = useAuth();
  const skillId = (props.params as { skillId?: string } | undefined)?.skillId ?? '';
  const [skill, setSkill] = useState<Skill | null>(null);
  const [desc, setDesc] = useState('');
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || !skillId) return;
    let cancelled = false;
    void extensionsApi.listSkills(accessToken, { limit: 100 }).then((res) => {
      const found = res.items.find((s) => s.skill_id === skillId) ?? null;
      if (!cancelled && found) {
        setSkill(found);
        setDesc(found.description);
        setBody(found.body_md);
      }
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [accessToken, skillId]);

  const save = async (status?: SkillStatus) => {
    if (!accessToken || !skill) return;
    setSaving(true);
    setMsg(null);
    try {
      await extensionsApi.patchSkill(accessToken, skill.skill_id, { description: desc, body_md: body, ...(status ? { status } : {}) });
      setMsg(status === 'published' ? 'Published' : 'Saved');
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'save failed');
    } finally {
      setSaving(false);
    }
  };

  if (!skillId) {
    return <div data-testid="studio-skill-editor-panel" className="p-4 text-xs text-muted-foreground">Open a skill from the Extensions panel to edit it.</div>;
  }

  return (
    <div data-testid="studio-skill-editor-panel" className="flex h-full min-h-0 flex-col gap-2 p-3">
      <div className="text-sm font-medium">{skill ? skill.slug : 'Loading…'}</div>
      <label className="text-xs text-muted-foreground">Description</label>
      <input value={desc} onChange={(e) => setDesc(e.target.value)} data-testid="skill-editor-desc"
        className="rounded-md border bg-background px-2 py-1.5 text-xs" />
      <label className="text-xs text-muted-foreground">Body (markdown)</label>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} data-testid="skill-editor-body"
        className="min-h-0 flex-1 rounded-md border bg-background p-2 font-mono text-xs" />
      <div className="flex items-center gap-2">
        <button disabled={saving || !skill} onClick={() => void save()} className="rounded border px-3 py-1 text-xs">Save draft</button>
        <button disabled={saving || !skill} onClick={() => void save('published')} className="rounded bg-primary px-3 py-1 text-xs text-primary-foreground">Publish</button>
        {msg && <span className="text-xs text-muted-foreground">{msg}</span>}
      </div>
    </div>
  );
}
