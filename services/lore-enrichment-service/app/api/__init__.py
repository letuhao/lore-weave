"""HTTP API layer (RAID C3 — contract freeze).

One router module per resource family (jobs, proposals, sources, templates),
mounted into `app.main`. These are STUB handlers: they return spec-valid
placeholder shapes (200/201/202) for reads and `501 Not Implemented` for
actions whose behaviour belongs to later cycles (C8/C9/C10/C13/C14). Behaviour
is NOT implemented here — shapes are the load-bearing deliverable.
"""
