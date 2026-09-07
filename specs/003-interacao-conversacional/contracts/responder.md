# Contrato: funcao de resposta

## `responder(intent, catalogo, data_source, llm_provider, reference_today, max_bytes, max_rows) -> AnswerOutcome`

**Ordem das checagens** (curto-circuito):

1. Resolver `intent.period_expression` via vocabulario fechado -> se desconhecida, `clarification_needed`.
2. Se `intent.baseline_period_expression` presente, resolver tambem -> se desconhecida, `clarification_needed`.
3. Chamar `catalogo_semantico.decidir(catalogo, intent.metric_id, intent.dimension_id, period.start, period.end, audit_sink=[])` -> se `allowed=False`, repassar `reason_code` (traduzido 1:1).
4. Montar `QueryRequest` (de `execucao_query`) e chamar `executar(...)` -> se `success=False`, repassar `reason_code` (traduzido 1:1).
5. Se ha comparacao (`baseline_period_expression` presente):
   a. Se `period.is_partial != baseline_period.is_partial` -> `not_comparable_window`.
   b. Repetir os passos 3-4 para o periodo baseline.
   c. Se o valor baseline for `0` -> `zero_baseline`.
   d. Calcular `percentage_change = (current - baseline) / baseline * 100`.
6. Montar `NarrationPayload` (somente campos fechados, per `data-model.md`) a partir do(s) resultado(s) ja calculados.
7. Chamar `llm_provider.narrar(payload) -> list[ClaimSentence]`. O provider narra o payload fechado; nao recebe a pergunta original nem calcula nada (FR-008).
8. Retornar `AnswerOutcome(success=True, sentences=..., resolved_period=...)`.

`llm_provider.narrar` e chamado no maximo uma vez, e somente apos todas as checagens 1-5 passarem.

## `LLMProvider` (Protocol)

`narrar(payload: NarrationPayload) -> list[ClaimSentence]` — unico metodo. Recebe apenas o `NarrationPayload` fechado (nunca a `QuestionIntent` original).
