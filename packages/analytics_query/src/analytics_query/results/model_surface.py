"""The model-facing boundary — T100 (FR-039, FR-054, FR-055, FR-056; SC-007).

What may cross to a language model, and what may not.

**May cross**: aggregated figures that already passed suppression, their
governed column identifiers, declared units, and the reason codes and caveats
that qualify them.

**May not cross**: fact rows, personal data, credentials, unrestricted query
text — and the ability to widen a governed request into an ungoverned one.

`FR-039` is enforced by absence rather than by rule: **no language-model client
exists anywhere in this package**, so no code path can hand a model a figure to
restate. A static import test asserts it. That is the only form of the guarantee
that survives a refactor — a rule saying "do not ask the model to compute"
depends on everyone remembering, while an absent dependency depends on nothing.

The row bound is separate from the governed row ceiling and stricter. A payload
crossing to a model surface is bounded because a model that receives a thousand
rows can be induced to emit them, and the surface is not a place to discover
that a payload was larger than intended.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts._base import ContractViolation
from ..contracts.reason_codes import AnalyticsReasonCode
from .completeness import ResultKind, classify_result

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..contracts.policy import QueryPolicy
    from ..contracts.result import AnalyticsResult

__all__ = ["ModelPayload", "to_model_payload"]

#: Field names that must never appear in a model-facing payload.
FORBIDDEN_KEYS = (
    "sql",
    "query_text",
    "statement",
    "credential",
    "token",
    "principal_ref",
    "email",
    "name",
    "raw_rows",
    "fact_rows",
)


class ModelPayload(dict[str, object]):
    """A plain mapping, deliberately.

    Not a rich object: anything a model surface receives should be inspectable
    by the denylist scan without knowing its type, and a `dict` cannot carry
    behaviour that quietly reaches back into the request.
    """


def to_model_payload(
    result: AnalyticsResult,
    policy: QueryPolicy,
    *,
    limitations: tuple[str, ...] = (),
) -> ModelPayload:
    """Build the bounded, aggregated payload a model surface may receive.

    Refuses rather than trimming when the result exceeds the bound. Trimming
    would hand a model a silently narrower table — the same substitution
    `FR-024` refuses at the query layer, reintroduced one step later.

    A fully withheld result yields no payload at all: there is nothing a model
    could say about it that would not be inference over suppressed figures.
    """
    disposition = classify_result(result)
    if disposition.kind is ResultKind.FULLY_WITHHELD:
        raise ContractViolation(
            AnalyticsReasonCode.RESULT_FULLY_SUPPRESSED,
            "no aggregated evidence remains that a model surface may receive",
        )

    if len(result.rows) > policy.maximum_rows:
        raise ContractViolation(
            AnalyticsReasonCode.QUERY_ROW_LIMIT_EXCEEDED,
            "the payload exceeds the governed row bound for a model-facing surface",
        )

    rows: list[list[object]] = []
    for row in result.rows:
        # Labels first, matching the declared column order: dimension columns
        # precede metric columns in a governed breakdown.
        rendered: list[object] = list(row.labels)
        for cell in row.cells:
            # A suppressed cell crosses as an explicit marker, never as a blank
            # or a zero — a model reading a blank will narrate it as absence.
            rendered.append(
                {"suppressed": True, "reason": cell.suppression_reason.value}
                if cell.suppressed and cell.suppression_reason is not None
                else str(cell.value)
                if cell.value is not None
                else None
            )
        rows.append(rendered)

    return ModelPayload(
        columns=[
            {"identifier": c.identifier, "unit": c.unit, "is_metric": c.is_metric}
            for c in result.columns
        ],
        rows=rows,
        completeness=result.completeness.value,
        limitations=list(limitations),
    )
