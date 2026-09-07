# Engineering Playbook

Playbook reutilizavel para desenvolvimento assistido por agentes em projetos independentes de portfolio. O repositorio e a memoria canonica: especificacoes, planos, tarefas, decisoes, checkpoints e evidencias vivem aqui, nao no historico de chat.

O nucleo de SDD e o GitHub Spec Kit fixado em `v1.0.4`. Este repositorio nao reimplementa os comandos do Spec Kit; ele governa como usa-los junto com TDD seletivo, MADR, revisao independente, estado versionado, retomada, reconciliacao, CI e governanca de Git.

## Uso

1. Instale dependencias: `uv sync --locked`.
2. Leia o contexto: `uv run python scripts/resume.py`.
3. Valide o playbook: `uv run python scripts/verify.py`.
4. Diagnostique o ambiente: `uv run python scripts/doctor.py`.
5. Ao interromper ou trocar agente: `uv run python scripts/checkpoint.py`.

## Entrega Git

Use `uv run python scripts/delivery.py` para conduzir entregas em etapas: `start`, `prepare`, `commit`, `publish`, `merge --auto` e `status`. Operacoes remotas exigem `--yes-remote` e nao sao executadas por `prepare` ou `status`. A documentacao completa esta em `docs/delivery/README.md`.

## Project Requirements Document — PRD

Antes de executar o fluxo do GitHub Spec Kit, preencha `docs/requirements/project-requirements.md` a partir de `templates/project/requirements.md`. O PRD e a fonte mestre de requisitos do produto; o Spec Kit transforma recortes aprovados em specification, plan, tasks, implementation, validation e convergence.

Use `uv run python scripts/bootstrap.py` para criar a copia editavel quando ela ainda nao existir. O bootstrap nao sobrescreve PRD existente.

## Fluxo

- `lite`: documentacao, manutencao trivial e configuracao reversivel.
- `standard`: funcionalidades normais, correcoes nao criticas e refatoracoes delimitadas.
- `strict`: arquitetura, seguranca, persistencia, performance critica, CUDA, contratos publicos ou mudancas caras de reverter.

Produtos derivados deste playbook nao devem consumir APIs de LLM nem incorporar modelos de linguagem locais. IA pode auxiliar o desenvolvimento, mas nao vira dependencia do produto.

## Projetos suportados

O playbook governa projetos separados em Python, C++, CUDA, Rust, Go, TypeScript, Java, C#, Kotlin, Swift, R, Julia e SQL. Ele nao transforma essas stacks em um monorepo.

## Limitacoes

Este repositorio fornece governanca, templates, validadores e perfis. Ele nao instala OpenSpec, BMAD ou Agent OS, nao publica releases e nao executa operacoes remotas sem autorizacao humana explicita.
