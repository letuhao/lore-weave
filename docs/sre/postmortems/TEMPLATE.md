<!--
  docs/sre/postmortems/TEMPLATE.md — L7.D.10 (RAID cycle 37)

  SR04 postmortem template. postmortem-bot copies this file to
  docs/sre/postmortems/<incident-id>.md on incident close, substituting the
  {{...}} placeholders it can fill automatically (id, severity, timeline
  bounds). The remaining sections are filled by the IC during the
  blameless review.

  Root cause MUST be exactly one id from contracts/postmortems/root_cause_enum.yaml.
  This is a BLAMELESS postmortem: describe systems and decisions, not people.
-->

# Postmortem: {{INCIDENT_ID}}

| Field | Value |
|---|---|
| Incident ID | {{INCIDENT_ID}} |
| Severity | {{SEVERITY}} |
| Title | {{TITLE}} |
| Declared at | {{DECLARED_AT}} |
| Resolved at | {{RESOLVED_AT}} |
| Duration | {{DURATION}} |
| Incident Commander | {{IC}} |
| Status | draft |

## 1. Summary

<!-- 2-3 sentence customer-safe summary of what happened and the impact. -->

## 2. Impact

<!-- Who/what was affected, for how long, and how severely. Quantify where
     possible: affected users, requests dropped, SLO budget consumed. -->

## 3. Timeline

<!-- All times UTC. Start at first symptom, end at resolution. -->

| Time (UTC) | Event |
|---|---|
| {{DECLARED_AT}} | Incident declared ({{SEVERITY}}) |
| | |
| {{RESOLVED_AT}} | Incident resolved |

## 4. Root cause

<!-- Choose EXACTLY ONE id from contracts/postmortems/root_cause_enum.yaml.
     postmortem-bot validates this value. Then explain. -->

- **Root cause class:** `unknown`  <!-- replace with one of the 12 enum ids -->
- **Explanation:**

## 5. Detection

<!-- How was it detected? Alert / customer report / manual? Was detection
     timely? If not, file an observability_gap action item. -->

## 6. Resolution

<!-- What actions resolved the incident? -->

## 7. Action items

<!-- Concrete, owned, tracked. Each item links to an issue. -->

| ID | Action | Owner | Due | Issue |
|---|---|---|---|---|
| AI-1 | | | | |

## 8. Lessons learned

### What went well

### What went poorly

### Where we got lucky

## 9. Follow-up

<!-- Schedule the action-item review. SEV0/SEV1 postmortems require sign-off
     before this doc moves from status: draft → status: published. -->
