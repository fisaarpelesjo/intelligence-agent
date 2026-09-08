from __future__ import annotations

from datetime import date

from catalogo_semantico import Catalogo, decidir
from execucao_query import DataSource, Operator, QueryFilter, QueryRequest, QueryResult, executar

from .comparacao import ZeroBaselineError, percentage_change
from .modelos import (
    AnswerOutcome,
    ComparisonResult,
    LLMProvider,
    NarrationPayload,
    QuestionIntent,
    ResolvedPeriod,
)
from .vocabulario_periodo import resolve_period


def _decide_and_execute(
    intent: QuestionIntent,
    catalogo: Catalogo,
    period: ResolvedPeriod,
    data_source: DataSource,
    max_bytes: int,
    max_rows: int,
) -> QueryResult | str:
    decision = decidir(
        catalogo,
        intent.metric_id,
        intent.dimension_id,
        period.start,
        period.end,
        audit_sink=[],
    )
    if not decision.allowed:
        return decision.reason_code.value if decision.reason_code else "unknown_metric"

    query_filter = None
    if intent.dimension_id is not None:
        query_filter = QueryFilter(
            dimension_id=intent.dimension_id,
            operator=Operator.EQ,
            values=(intent.dimension_value or "",),
        )
    request = QueryRequest(
        decision=decision,
        filter=query_filter,
        period_start=period.start,
        period_end=period.end,
    )
    outcome = executar(request, data_source, max_bytes, max_rows)
    if not outcome.success or outcome.result is None:
        return outcome.reason_code.value if outcome.reason_code else "data_source_unavailable"
    return outcome.result


def responder(
    intent: QuestionIntent,
    catalogo: Catalogo,
    data_source: DataSource,
    llm_provider: LLMProvider,
    reference_today: date,
    max_bytes: int,
    max_rows: int,
) -> AnswerOutcome:
    period = resolve_period(intent.period_expression, reference_today)
    if period is None:
        return AnswerOutcome(success=False, reason_code="clarification_needed")

    baseline_period: ResolvedPeriod | None = None
    if intent.baseline_period_expression is not None:
        baseline_period = resolve_period(intent.baseline_period_expression, reference_today)
        if baseline_period is None:
            return AnswerOutcome(success=False, reason_code="clarification_needed")

    outcome = _decide_and_execute(intent, catalogo, period, data_source, max_bytes, max_rows)
    if isinstance(outcome, str):
        return AnswerOutcome(success=False, reason_code=outcome)
    result = outcome

    comparison: ComparisonResult | None = None
    if baseline_period is not None:
        if period.is_partial != baseline_period.is_partial:
            return AnswerOutcome(success=False, reason_code="not_comparable_window")

        baseline_outcome = _decide_and_execute(
            intent, catalogo, baseline_period, data_source, max_bytes, max_rows
        )
        if isinstance(baseline_outcome, str):
            return AnswerOutcome(success=False, reason_code=baseline_outcome)

        try:
            change = percentage_change(result.value, baseline_outcome.value)
        except ZeroBaselineError:
            return AnswerOutcome(success=False, reason_code="zero_baseline")
        comparison = ComparisonResult(
            current_value=result.value,
            baseline_value=baseline_outcome.value,
            percentage_change=change,
        )

    payload = NarrationPayload(
        metric_id=intent.metric_id,
        value=result.value,
        unit=result.unit,
        source_view=result.source_view,
        period_label=intent.period_expression,
        comparison=comparison,
    )
    sentences = llm_provider.narrar(payload)
    return AnswerOutcome(success=True, sentences=tuple(sentences), resolved_period=period)
