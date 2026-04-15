"""Offline maintenance jobs for knowledge-service.

Every module in this package is an async function (or set of
functions) designed to run outside of the request path: on a
scheduler, from a CLI, or manually from an SRE session. None
should be called from HTTP handlers.

Current jobs:
  - reconcile_evidence_count (K11.9): drift detector for the
    cached `evidence_count` on `:Entity|:Event|:Fact` nodes.
"""
