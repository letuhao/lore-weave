"""Public /v1/knowledge/* routers (K7).

Every route in this package authenticates via
`Depends(get_current_user)` from app.middleware.jwt_auth. The user_id
is sourced exclusively from the JWT sub claim — never from query
parameters or request body.
"""
