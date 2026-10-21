"""Domain route modules extracted from the fullworkbench aggregate.

Each module exposes a ``*_routes(*, factory)`` builder that returns Starlette
``Route`` objects bound to the Core session factory. Paths and methods must stay
identical to the frozen baseline in ``verification/api_contract/inventory.json``.
"""
