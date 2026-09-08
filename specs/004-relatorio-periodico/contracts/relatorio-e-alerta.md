# Contratos: relatorio e alerta

## `gerar_relatorio_diario(kpis, catalogo, data_source, reference_today, max_bytes, max_rows) -> DailyReport`

Para cada `KpiDefinition` em `kpis`, na ordem dada:

1. `report_date = reference_today - 1 dia`.
2. Chamar `catalogo_semantico.decidir(catalogo, kpi.metric_id, kpi.dimension_id, report_date, report_date, audit_sink=[])`.
3. Se `allowed=False` -> `KpiResult(metric_id=kpi.metric_id, available=False, reason_code=decision.reason_code)`.
4. Senao, montar `QueryRequest` e chamar `execucao_query.executar(...)`.
5. Se `success=False` -> `KpiResult(available=False, reason_code=outcome.reason_code)`.
6. Se `success=True` -> `KpiResult(available=True, value=..., unit=..., source_view=...)`.

Nenhuma excecao de `decidir`/`executar` propaga — ja sao tratadas internamente por essas funcoes (retornam recusa nomeada, nao levantam excecao).

Retorna `DailyReport(report_date=report_date, kpi_results=[...])`, sempre com o mesmo numero de resultados que `len(kpis)`.

## `avaliar_alertas(rules, catalogo, data_source, reference_today, max_bytes, max_rows) -> AlertBundle`

Para cada `AlertRule` em `rules`:

1. `evaluation_date = reference_today - 1 dia`.
2. Repetir os passos 2-5 de `gerar_relatorio_diario` para `rule.metric_id` (sem dimensao).
3. Se indisponivel -> `AlertResult(metric_id=rule.metric_id, evaluated=False, triggered=False, reason_code=...)`.
4. Se disponivel -> comparar `value` contra `rule.threshold` na `rule.direction` (`above`: dispara se `value > threshold`; `below`: dispara se `value < threshold`) -> `AlertResult(evaluated=True, triggered=..., value=...)`.

Retorna `AlertBundle(evaluation_date=evaluation_date, alert_results=[...])`, sempre com o mesmo numero de resultados que `len(rules)`.

Nenhuma das duas funcoes chama a outra; nao existe uma terceira funcao que combine os dois retornos (FR-005).
