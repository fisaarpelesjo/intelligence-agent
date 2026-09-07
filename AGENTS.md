# AGENTS.md

Leia sempre:

- `ENGINEERING.md`
- `.project/project.yml`
- `.project/state.yml`
- a specification, plan e tasks ativos
- `docs/requirements/project-requirements.md` quando existir ou quando a tarefa envolver requisitos de produto

Use `uv run python scripts/resume.py` antes de continuar trabalho interrompido. Use `uv run python scripts/verify.py` e `uv run python scripts/doctor.py` para validar estrutura e saude. Antes de parar, execute `uv run python scripts/checkpoint.py`.

Nao faca commit, push, merge, tag, release, force push, operacoes remotas ou destruicao de dados sem autorizacao humana explicita. Nao armazene transcricoes completas, chain-of-thought, secrets, tokens ou dados pessoais. Nao invente testes, benchmarks, citacoes, autoria ou coautoria.

Para entrega Git, use `uv run python scripts/delivery.py`. `prepare` e `status` sao seguros localmente; `publish` e `merge --auto` exigem autorizacao explicita e nao devem ser executados por inferencia.

O Project Requirements Document — PRD e a fonte mestre do produto. Antes de executar `specify`, `plan`, `tasks` ou `implement`, leia o PRD, verifique contradicoes, lacunas e requisitos nao testaveis, preserve IDs e rastreabilidade, e mantenha informacoes ausentes como `TODO`, `ASSUMPTION` ou `QUESTION`. Nenhum agente pode marcar PRD como `approved` ou preencher aprovacao humana inexistente.

Adaptadores devem apontar para este arquivo e para `ENGINEERING.md`; nao duplique regras canonicas extensas.
