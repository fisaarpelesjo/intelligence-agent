# Contrato: funcao de decisao

Interface publica do pacote `catalogo_semantico`, usada por pacotes consumidores (ex.: execucao de query governada, interacao conversacional).

## `decidir(catalogo, metric_id, dimension_id, period_start, period_end) -> AccessDecision`

Pura, sincrona, sem I/O de rede ou banco (SC-004). Emite exatamente um `AuditEvent` como efeito colateral obrigatorio antes de retornar (FR-009, FR-010).

**Entradas**:
- `catalogo`: instancia de catalogo ja carregado e validado (ver `carregar_catalogo`).
- `metric_id`: texto.
- `dimension_id`: texto ou `None`.
- `period_start`, `period_end`: datas (o periodo pedido).

**Saida**: `AccessDecision` (ver `data-model.md`).

**Regras** (mapeiam para FR-001..FR-007 da spec):

1. Se `metric_id` nao existe no catalogo -> `allowed=false`, `reason_code=unknown_metric`.
2. Se `dimension_id` fornecida e nao esta em `allowed_dimensions` da versao resolvida (ou nao ha versao resolvida) -> `allowed=false`, `reason_code=dimension_not_allowed`.
3. Resolver a(s) versao(oes) de `MetricDefinition` cuja janela cobre `[period_start, period_end]`:
   - Nenhuma versao cobre o periodo -> `allowed=false`, `reason_code=no_metric_version_for_period`.
   - O periodo cruza a fronteira de duas versoes (nenhuma versao cobre o intervalo inteiro, mas mais de uma cobre partes dele) -> `allowed=false`, `reason_code=period_spans_version_boundary`.
   - Exatamente uma versao cobre o periodo inteiro -> prossegue.
4. Se todas as checagens acima passarem -> `allowed=true`, `resolved_metric_version` preenchida.

## `carregar_catalogo(caminho) -> Catalogo`

Carrega os arquivos YAML do catalogo e valida integridade antes de retornar. Lanca uma excecao especifica (nao generica) quando:

- Dois `MetricDefinition` compartilham o mesmo `id` (FR-008).
- Duas `MetricDefinitionVersion` da mesma metrica tem janelas de vigencia sobrepostas (FR-008).

Nunca retorna um catalogo parcialmente invalido silenciosamente.

## `emitir_evento(decisao, metric_id, dimension_id, period_start, period_end) -> AuditEvent`

Cria e retorna o `AuditEvent` correspondente. Chamada internamente por `decidir` antes do retorno; exposta publicamente para permitir inspecao/teste direto (US3 da spec).
