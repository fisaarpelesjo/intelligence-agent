# Recovery Protocol

Depois de interrupcao, execute `uv run python scripts/resume.py` e `uv run python scripts/reconcile.py`. Se houver divergencia material entre Git, estado e checkpoint, pare antes de implementar e registre a decisao necessaria.

Para interrupcoes durante entrega Git, execute `uv run python scripts/delivery.py status` antes de repetir `prepare`, `commit`, `publish` ou `merge --auto`.
