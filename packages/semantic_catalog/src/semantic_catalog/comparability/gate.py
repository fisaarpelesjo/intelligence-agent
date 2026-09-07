"""Gate 6 (comparability) — T082 (FR-029, FR-030).

**Absence of a rule is not permission.** That single sentence is the gate. Two
metrics that look alike across sources usually are not — store-reported downloads
and device-reported installs are near-synonyms in conversation and different
events in reality — and the failure mode is a chart that is plausible, confident
and wrong.

So a combination is permitted only when a **governed rule authored by a human**
says so. Nothing is inferred from:

* similar **names** — ``downloads`` and ``installs`` read as synonyms;
* matching **grain** — both being day-grained says nothing about what they count;
* matching **unit** — two things measured in ``events`` are not the same event;
* sharing a **source** — one system can emit unrelated measures.

Three governed relations, each mapping to exactly one outcome:

``combinable``              → passes
``comparable_with_caveat``  → ``COMPARABLE_WITH_CAVEAT``, caveat attached (T083)
``not_comparable``          → ``METRICS_NOT_COMPARABLE``, with the business reason

and their absence → ``COMPARABILITY_RULE_MISSING``, which is a denial.

**Operand order is irrelevant.** A rule relating A to B governs the request that
names B and A. Authoring both directions would be two rules that can disagree.

Runs **after** authorisation (Gate 3), so a refusal here never discloses that two
metrics the requester may not see are related at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations

from ..contracts.comparability import ComparabilityRule, Relation, RuleSubject
from ..contracts.reason_codes import ReasonCode

__all__ = [
    "ComparabilityCheck",
    "PairKind",
    "check_comparability",
    "find_rule",
    "pairs_requiring_a_rule",
]


@dataclass(frozen=True, slots=True)
class PairKind:
    """One unordered pair that needs governed authorisation."""

    left: str
    right: str
    subject: RuleSubject

    @property
    def key(self) -> tuple[str, str]:
        """Unordered. ``(a, b)`` and ``(b, a)`` are the same pair."""
        return (self.left, self.right) if self.left <= self.right else (self.right, self.left)

    def describe(self) -> str:
        a, b = self.key
        return f"{a} + {b}"


@dataclass(frozen=True, slots=True)
class ComparabilityCheck:
    """The verdict for one pair, and the authored rule behind it."""

    pair: PairKind
    rule: ComparabilityRule | None
    reason_code: ReasonCode | None

    @property
    def permitted(self) -> bool:
        return self.reason_code is None or self.reason_code is ReasonCode.COMPARABLE_WITH_CAVEAT

    @property
    def is_caveat(self) -> bool:
        return self.reason_code is ReasonCode.COMPARABLE_WITH_CAVEAT


def pairs_requiring_a_rule(
    metrics: tuple[str, ...], sources: tuple[str, ...]
) -> tuple[PairKind, ...]:
    """Every unordered pair the request puts side by side.

    A single metric on a single source needs no rule: there is nothing to
    compare it with. Two of either is a comparison, whether or not the caller
    meant it as one — and a caller who did not mean it is exactly who a silent
    wrong answer would mislead.
    """
    pairs: list[PairKind] = []
    for left, right in combinations(sorted(set(metrics)), 2):
        pairs.append(PairKind(left=left, right=right, subject=RuleSubject.METRIC_PAIR))
    for left, right in combinations(sorted(set(sources)), 2):
        pairs.append(PairKind(left=left, right=right, subject=RuleSubject.SOURCE_PAIR))
    return tuple(pairs)


def find_rule(rules: Mapping[str, ComparabilityRule], pair: PairKind) -> ComparabilityRule | None:
    """The governed rule for ``pair``, in either operand order.

    Matching is by identifier and subject only. No fuzzy match, no fallback to a
    rule about a *similar* pair: a rule that nobody wrote for this pair does not
    govern this pair.
    """
    for rule in rules.values():
        if rule.subject is not pair.subject:
            continue
        candidate = (rule.left, rule.right) if rule.left <= rule.right else (rule.right, rule.left)
        if candidate == pair.key:
            return rule
    return None


#: Governed relation to outcome. ``combinable`` is absent because it produces no
#: code at all — it simply passes.
_RELATION_TO_REASON = {
    Relation.NOT_COMPARABLE: ReasonCode.METRICS_NOT_COMPARABLE,
    Relation.COMPARABLE_WITH_CAVEAT: ReasonCode.COMPARABLE_WITH_CAVEAT,
}


def check_comparability(
    rules: Mapping[str, ComparabilityRule],
    metrics: tuple[str, ...],
    sources: tuple[str, ...],
) -> tuple[ComparabilityCheck, ...]:
    """Check every pair the request forms. Deny-by-default on a missing rule."""
    checks: list[ComparabilityCheck] = []
    for pair in pairs_requiring_a_rule(metrics, sources):
        rule = find_rule(rules, pair)
        if rule is None:
            checks.append(
                ComparabilityCheck(
                    pair=pair, rule=None, reason_code=ReasonCode.COMPARABILITY_RULE_MISSING
                )
            )
            continue
        checks.append(
            ComparabilityCheck(
                pair=pair, rule=rule, reason_code=_RELATION_TO_REASON.get(rule.relation)
            )
        )
    return tuple(checks)
