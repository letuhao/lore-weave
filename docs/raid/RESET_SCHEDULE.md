# Anthropic Quota Reset Schedule (Max 20x subscription)

> **Purpose:** Per RAID_WORKFLOW.md §14.5-6 / Q5-Q6, document known reset windows so
> user knows when to manually re-invoke `/raid <N>` after a quota block.

## Reset windows

### 5-hour rolling window
- **Resets:** ~5 hours from first message of a session
- **Capacity:** ~900 messages (~2M tokens equivalent) per Max 20x plan
- **Behavior:** When hit, subsequent tool calls blocked until reset

### Weekly cap
- **Resets:** Rolling 7-day window from first message of week
- **Capacity:** Anthropic does not publish exact weekly token count for Max 20x;
  estimated 8-10× the 5h window
- **Behavior:** Even if 5h window has reset, weekly cap may still block

### Monthly session cap
- **Limit:** 50 sessions / month soft guideline (~250 hours of usage)
- **Tracking:** `scripts/raid/session-counter.py` reads CYCLE_LOG.md
- **Behavior:** Warning at 40 sessions; halt at 48 (2-session buffer)

## Cross-verification

User should periodically check **https://claude.ai/usage** (or the in-app usage page)
to cross-verify RAID's quota estimates against Anthropic's authoritative counter.

If RAID's estimate diverges > 20% from Anthropic's counter:
1. Note discrepancy in this file
2. Tune `quota-profile.yaml` multipliers
3. Re-run `quota-summary.py` to validate

## Known reset events (auto-appended)

<!-- Auto-appended by orchestrator when quota_block detected and reset estimated -->
