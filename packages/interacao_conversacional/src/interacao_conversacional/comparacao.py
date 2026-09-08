from __future__ import annotations


class ZeroBaselineError(Exception):
    """Levantada quando o periodo baseline de uma comparacao tem valor zero."""


def percentage_change(current: float, baseline: float) -> float:
    if baseline == 0:
        raise ZeroBaselineError("baseline zero: variacao percentual indefinida")
    return (current - baseline) / baseline * 100
