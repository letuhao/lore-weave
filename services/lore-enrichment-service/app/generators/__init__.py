"""Generators — the L2 half of the pipeline (`PPB-A6`).

Everything here consumes a FROZEN pool through :class:`app.pool.consume.PoolView`
and nothing else. A generator that imports `app.pool.loop`, `app.pool.criteria` or
another generator has crossed the freeze, and a test in
`tests/test_generator_boundary.py` reds when one does.
"""
