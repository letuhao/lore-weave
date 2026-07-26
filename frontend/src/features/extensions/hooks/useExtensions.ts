// Controller hook (MVC) — owns skills + proposals state & logic, no JSX.
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { agentRegistryHealth } from '@/lib/agentRegistryHealth';
import { extensionsApi } from '../api';
import { useExtensionScope } from '../context/ExtensionScope';
import type { Skill, Proposal, UsageCounters } from '../types';

export function useSkills() {
  const { accessToken } = useAuth();
  const { bookId } = useExtensionScope();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [tier, setTier] = useState('');
  const [sort, setSort] = useState('updated');
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const limit = 20;

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extensionsApi.listSkills(accessToken, { q, tier, sort, limit, offset: page * limit, book_id: bookId ?? undefined });
      setSkills(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load skills');
    } finally {
      setLoading(false);
    }
  }, [accessToken, q, tier, sort, page, bookId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggle = useCallback(
    async (skill: Skill, enabled: boolean) => {
      if (!accessToken) return;
      await extensionsApi.setSkillEnabled(accessToken, skill.skill_id, enabled);
    },
    [accessToken],
  );

  const remove = useCallback(
    async (skill: Skill) => {
      if (!accessToken) return;
      await extensionsApi.deleteSkill(accessToken, skill.skill_id);
      await refresh();
    },
    [accessToken, refresh],
  );

  return {
    skills, total, loading, error,
    q, setQ, tier, setTier, sort, setSort,
    page, setPage, limit,
    refresh, toggle, remove,
  };
}

export function useProposals() {
  const { accessToken } = useAuth();
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('pending');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extensionsApi.listProposals(accessToken, { status, limit: 50 });
      setProposals(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load proposals');
    } finally {
      setLoading(false);
    }
  }, [accessToken, status]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const approve = useCallback(
    async (p: Proposal) => {
      if (!accessToken) return;
      await extensionsApi.approveProposal(accessToken, p.proposal_id);
      await refresh();
    },
    [accessToken, refresh],
  );

  const reject = useCallback(
    async (p: Proposal, reason = '') => {
      if (!accessToken) return;
      await extensionsApi.rejectProposal(accessToken, p.proposal_id, reason);
      await refresh();
    },
    [accessToken, refresh],
  );

  return { proposals, total, status, setStatus, loading, error, refresh, approve, reject };
}

export function useUsage(): { usage: UsageCounters | null; unavailable: boolean } {
  const { accessToken } = useAuth();
  const [usage, setUsage] = useState<UsageCounters | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    if (!accessToken) return;
    // F12 — if the registry just failed, skip the slow 504 round-trip on this
    // (re)mount and surface "unavailable" instead of re-hammering a down service.
    if (agentRegistryHealth.likelyDown()) {
      setUnavailable(true);
      return;
    }
    let cancelled = false;
    void extensionsApi.usage(accessToken).then((u) => {
      if (!cancelled) {
        setUsage(u);
        setUnavailable(false);
        agentRegistryHealth.noteUp();
      }
    }).catch(() => {
      if (!cancelled) {
        setUnavailable(true);
        agentRegistryHealth.noteDown();
      }
    });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);
  return { usage, unavailable };
}
