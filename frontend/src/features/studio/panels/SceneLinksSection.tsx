// 22-C3 (Links) — the scene-inspector's causal-edge section. Reuses the SAME data + mutations as
// the Scene Graph canvas (`useSceneLinks`/`useOutline`/`useOutlineMutations`, DOCK-2 no fork): a
// setup→payoff/custom edge (`scene_link`) authored inline while you edit a scene's plan, rather
// than only in the spatial graph. Read (in/out, resolved to titles) + add + delete; OCC-free (edges
// have no version — create is 409-guarded on the natural key, delete is idempotent).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useOutline, useOutlineMutations, useSceneLinks } from '@/features/composition/hooks/useOutline';
import type { SceneLink, SceneLinkKind } from '@/features/composition/types';

const shortId = (id: string) => `${id.slice(0, 8)}…`;

// Module-level (NOT declared in the parent's render body) so React keeps row identity stable across
// parent re-renders — an inline component remounts the whole list every render (focus loss + churn).
function LinkRow({ link, dir, title, onRemove, kindLabel, removeLabel }: {
  link: SceneLink; dir: 'out' | 'in'; title: string; onRemove: () => void; kindLabel: string; removeLabel: string;
}) {
  return (
    <li data-testid="scene-links-row" className="flex items-center gap-1 text-[11px]">
      <span className="text-muted-foreground">{dir === 'out' ? '→' : '←'}</span>
      <span className="min-w-0 flex-1 truncate" title={title}>{title}</span>
      <span className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">{kindLabel}</span>
      {link.label && <span className="truncate text-[10px] italic text-muted-foreground">“{link.label}”</span>}
      <button
        type="button" data-testid={`scene-links-remove-${link.id}`}
        className="text-muted-foreground hover:text-destructive"
        onClick={onRemove} aria-label={removeLabel}
      >×</button>
    </li>
  );
}

export function SceneLinksSection({ projectId, token, sceneId }: { projectId: string; token: string | null; sceneId: string }) {
  const { t } = useTranslation('studio');
  const linksQ = useSceneLinks(projectId, token);
  const outlineQ = useOutline(projectId, token);
  const m = useOutlineMutations(projectId, token);
  const [target, setTarget] = useState('');
  const [kind, setKind] = useState<SceneLinkKind>('setup_payoff');
  const [label, setLabel] = useState('');

  // `||` (not `??`) so an empty-title scene (decompiled/imported leaves can have title='') degrades
  // to a short-id like the picker below, never a blank label (review: titleOf consistency).
  const titleOf = (id: string) => outlineQ.data?.find((n) => n.id === id)?.title || shortId(id);
  const links = linksQ.data ?? [];
  const outgoing = links.filter((l) => l.from_node_id === sceneId);
  const incoming = links.filter((l) => l.to_node_id === sceneId);
  // Exclude a target only for the SAME kind — the BE uniqueness is (from,to,kind), so s1→s2
  // setup_payoff and s1→s2 custom are both valid (review: don't over-exclude across kinds). A
  // true same-kind dup that slips through is caught by the 409 handler below.
  const outgoingSameKind = new Set(outgoing.filter((l) => l.kind === kind).map((l) => l.to_node_id));
  const targets = (outlineQ.data ?? []).filter(
    (n) => n.kind === 'scene' && !n.is_archived && n.id !== sceneId && !outgoingSameKind.has(n.id),
  );

  const add = () => {
    if (!target) return;
    m.createSceneLink.mutate(
      { from_node_id: sceneId, to_node_id: target, kind, label: label.trim() },
      {
        onSuccess: () => { setTarget(''); setLabel(''); },
        onError: (e) => {
          const status = (e as { status?: number }).status;
          toast.error(status === 409
            ? t('panels.scene-inspector.links.dup', { defaultValue: 'A link of that kind already exists between these scenes.' })
            : t('panels.scene-inspector.links.failed', { defaultValue: 'Could not create the link.' }));
        },
      },
    );
  };

  const kindLabel = (k: SceneLink['kind']) =>
    k === 'setup_payoff'
      ? t('panels.scene-inspector.links.setup', { defaultValue: 'setup→payoff' })
      : t('panels.scene-inspector.links.custom', { defaultValue: 'custom' });
  const removeLabel = t('panels.scene-inspector.links.remove', { defaultValue: 'Remove link' });
  const row = (l: SceneLink, dir: 'out' | 'in') => (
    <LinkRow key={l.id} link={l} dir={dir} kindLabel={kindLabel(l.kind)} removeLabel={removeLabel}
      title={titleOf(dir === 'out' ? l.to_node_id : l.from_node_id)}
      onRemove={() => m.deleteSceneLink.mutate(l.id)} />
  );

  return (
    <div data-testid="scene-inspector-links" className="space-y-2">
      {/* Gate on THIS scene's edges, not the project-wide `links` — else the hint vanishes as soon
          as the project has any link between two other scenes (review: scene-scoped empty state). */}
      {outgoing.length === 0 && incoming.length === 0 && (
        <p className="text-[11px] text-muted-foreground">{t('panels.scene-inspector.links.empty', { defaultValue: 'No causal links yet.' })}</p>
      )}
      {outgoing.length > 0 && <ul className="space-y-1">{outgoing.map((l) => row(l, 'out'))}</ul>}
      {incoming.length > 0 && <ul className="space-y-1">{incoming.map((l) => row(l, 'in'))}</ul>}

      {/* Add a link FROM this scene → another scene. */}
      <div className="flex flex-wrap items-center gap-1">
        <select
          data-testid="scene-links-target" value={target} onChange={(e) => setTarget(e.target.value)}
          aria-label={t('panels.scene-inspector.links.target', { defaultValue: 'Link to scene' })}
          className="min-w-0 flex-1 rounded border bg-background px-1 py-0.5 text-[11px]"
        >
          <option value="">{t('panels.scene-inspector.links.pick', { defaultValue: 'Link to…' })}</option>
          {targets.map((n) => <option key={n.id} value={n.id}>{n.title || shortId(n.id)}</option>)}
        </select>
        <select
          data-testid="scene-links-kind" value={kind} onChange={(e) => setKind(e.target.value as SceneLinkKind)}
          aria-label={t('panels.scene-inspector.links.kind', { defaultValue: 'Link kind' })}
          className="rounded border bg-background px-1 py-0.5 text-[11px]"
        >
          <option value="setup_payoff">{t('panels.scene-inspector.links.setup', { defaultValue: 'setup→payoff' })}</option>
          <option value="custom">{t('panels.scene-inspector.links.custom', { defaultValue: 'custom' })}</option>
        </select>
        <input
          data-testid="scene-links-label" value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder={t('panels.scene-inspector.links.label', { defaultValue: 'label' })}
          className="w-20 rounded border bg-background px-1 py-0.5 text-[11px]"
        />
        <button
          type="button" data-testid="scene-links-add"
          disabled={!target || m.createSceneLink.isPending}
          onClick={add}
          className="rounded bg-primary px-2 py-0.5 text-[11px] text-primary-foreground disabled:opacity-50"
        >+ {t('panels.scene-inspector.links.add', { defaultValue: 'link' })}</button>
      </div>
    </div>
  );
}
