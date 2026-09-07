# Implementation Plan: Catalogo semantico — decisao de autorizacao

**Branch**: `001-catalogo-semantico` | **Date**: 2026-09-07 | **Spec**: `specs/001-catalogo-semantico/spec.md`

**Input**: Feature specification from `specs/001-catalogo-semantico/spec.md`

## Summary

Construir uma biblioteca Python pura (sem I/O de rede ou banco) que decide, para uma tupla (metrica, dimensao opcional, periodo), se a pergunta e autorizada — retornando a definicao de metrica resolvida quando permitido, ou uma negacao com motivo nomeado quando nao. A biblioteca carrega um catalogo declarativo (metricas, dimensoes, versoes com janela de vigencia), valida sua integridade na carga (sem IDs duplicados, sem sobreposicao de versao), resolve a versao correta de uma metrica para o periodo perguntado, e emite um evento de auditoria para cada decisao antes de retorna-la ao chamador. Nao executa nenhuma query real — essa e a responsabilidade do proximo pacote do pipeline (execucao de query governada), que consumira a saida desta biblioteca.

## Technical Context

**Language/Version**: Python 3.12+ (fixado pela Constitution)

**Primary Dependencies**: `pydantic` (ou `dataclasses` + validacao manual — decisao de implementacao, ver Complexity Tracking se pydantic for adotado) para modelar Metric Definition / Dimension Definition / Access Decision / Audit Event; `pyyaml` (ja dependencia do engineering-playbook, reutilizavel) para carregar o catalogo declarativo em YAML.

**Storage**: Arquivos YAML versionados no proprio pacote (`packages/catalogo_semantico/catalog/*.yaml`) — nao ha banco de dados nesta feature; o catalogo e dado estatico carregado em memoria na inicializacao.

**Testing**: `pytest`, seguindo o padrao ja estabelecido pelo engineering-playbook (`uv run pytest`, `uv run ruff`, `uv run pyright`).

**Target Platform**: Biblioteca Python standalone, consumida por outros pacotes do pipeline (nenhuma implantacao propria nesta feature).

**Project Type**: Library (pacote Python independente dentro de um monorepo `packages/`).

**Performance Goals**: Decisao de autorizacao deve ser da ordem de microssegundos (operacao em memoria, sem I/O) — nao ha requisito de performance material alem de "nao bloquear em rede/disco durante a decisao" (SC-004 da spec).

**Constraints**: Zero chamada de rede ou banco de dados durante a decisao (Constitution Principio I; SC-004); catalogo invalido (IDs duplicados, versoes sobrepostas) deve falhar na carga, nunca silenciosamente na decisao.

**Scale/Scope**: Catalogo inicial pequeno, de exemplo (poucas metricas sinteticas: `signups`, `monthly_recurring_revenue`, `active_users`, cada uma com 1-2 versoes) — suficiente para exercitar autorizacao, versionamento, negacao e auditoria conforme a spec.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Verificacao | Status |
|---|---|---|
| I. Governed Semantic Access | Esta feature NAO le nenhum dado de negocio real — so decide autorizacao sobre um catalogo declarativo. Deny-by-default e o comportamento central testado (spec User Story 1, cenario 4). | PASS |
| II. Deterministic First | A decisao e 100% deterministica (sem LLM envolvido nesta feature). | PASS |
| III. Provenance or Abstention | Nao aplicavel diretamente nesta feature (nao ha "resposta" ao usuario final aqui, apenas decisao de autorizacao) — a definicao de metrica retornada e o insumo de proveniencia que o proximo pacote usara. N/A justificado. | PASS (N/A) |
| IV. Least Privilege | Nenhuma escrita de dado de negocio; a unica "escrita" e o evento de auditoria, que e o proprio requisito de rastreabilidade. | PASS |
| V. Idempotent, Auditable Delivery | Nao ha entrega/mensageria nesta feature (isso e escopo de pacotes posteriores); o requisito relevante aqui e auditabilidade da decisao (FR-009, FR-010), coberto. | PASS (parcial, entrega fora de escopo) |

Nenhuma violacao identificada. Nenhum item em Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-catalogo-semantico/
├── plan.md              # Este arquivo
├── spec.md              # Especificacao (ja escrita)
├── data-model.md         # A gerar na Fase 1 (entidades detalhadas)
├── quickstart.md         # A gerar na Fase 1
├── contracts/            # A gerar na Fase 1 (assinatura da funcao de decisao, schema do catalogo)
└── tasks.md              # A gerar por /speckit-tasks (Fase 2)
```

### Source Code (repository root)

```text
packages/
└── catalogo_semantico/
    ├── pyproject.toml
    ├── README.md
    ├── catalog/
    │   ├── metrics.yaml        # Definicoes de metrica (versionadas, com janela de vigencia)
    │   ├── dimensions.yaml     # Definicoes de dimensao
    │   └── owners.yaml         # Ownership de cada metrica (rastreabilidade)
    ├── src/
    │   └── catalogo_semantico/
    │       ├── __init__.py
    │       ├── modelos.py       # Metric Definition, Dimension Definition, Access Decision, Audit Event
    │       ├── carregamento.py  # Carrega e valida o catalogo (FR-008)
    │       ├── decisao.py       # Funcao pura de decisao (FR-001..FR-007)
    │       └── auditoria.py     # Emissao de evento de auditoria (FR-009, FR-010)
    └── tests/
        ├── unit/
        │   ├── test_decisao_permite.py
        │   ├── test_decisao_nega.py
        │   ├── test_versionamento.py
        │   ├── test_catalogo_invalido.py
        │   └── test_auditoria.py
        └── fixtures/
            └── catalogo_exemplo/   # Catalogo YAML minimo usado nos testes
```

**Structure Decision**: monorepo `packages/` com um pacote Python independente por etapa do pipeline (consistente com a arquitetura descrita no PRD e na Constitution — fronteiras de dependencia unidirecional testaveis). Esta feature cria o primeiro pacote, `packages/catalogo_semantico/`, com seu proprio `pyproject.toml` (adicionado como membro de um workspace `uv` na raiz do repositorio). O `src/intelligence_agent/` criado pelo scaffold inicial do engineering-playbook permanece como pacote raiz do projeto (metadados/versao), sem logica de dominio — a logica de dominio vive inteiramente em `packages/*`.

## Complexity Tracking

Nenhuma violacao da Constitution identificada nesta feature. Tabela nao aplicavel.
