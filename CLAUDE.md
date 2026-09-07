# Claude Code Adapter

Use `AGENTS.md` como entrada principal e `ENGINEERING.md` como processo canonico. Leia o PRD quando existir antes de `specify`, `plan`, `tasks` ou `implement`. Antes de agir, execute leitura de contexto via `uv run python scripts/resume.py`. Ao concluir, valide com `uv run python scripts/verify.py`, `uv run python scripts/doctor.py` e testes aplicaveis, depois gere checkpoint.

Nao execute operacoes remotas, commits, merges, tags, releases ou acoes destrutivas sem autorizacao explicita.
