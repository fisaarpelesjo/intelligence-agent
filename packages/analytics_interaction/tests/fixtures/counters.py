"""Counted collaborators for the six cost surfaces — T046 (FR-089; SC-050).

`FR-089` is explicit that the zero-call property is **measured by call count
against each surface, not asserted by inspection**. That wording is the whole
reason this file exists: a source scan proves a module does not *import* the
catalog, and proves nothing about whether some other path reached it at runtime.
Counting proves the thing that actually matters.

Six surfaces, from `intake-contract.md` §6:

| Surface | Why it costs |
|---|---|
| Catalog | `001` reads and evaluates; a read is work performed for the caller |
| Model | tokens, billed per call once `D-20` is declared |
| Candidate resolution | search and ranking over the access-filtered surface |
| Clarification issuance | produces a sealed artifact the caller can transport |
| Execution port | the warehouse bill, via `002` |
| Limit disclosure | discloses governed policy, which is a `D-19` value |

Every collaborator here is **fail-loud on use, not on construction**: calling one
increments its counter and then returns a fixture answer or raises. A collaborator
that raised on construction could never demonstrate that it *would* have been
counted, and a test asserting zero against a thing that cannot be called at all
proves nothing.

TEST-ONLY. None of these reaches a catalog, a model, a warehouse or a key, and
none is ever evidence for an external record.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analytics_interaction.contracts.intake import PrincipalContext

__all__ = [
    "SURFACES",
    "CountingClarificationIssuer",
    "CountingExecutionPort",
    "CountingLimitDiscloser",
    "CountingModelPort",
    "CountingResolver",
    "Surfaces",
]

#: The six surfaces, in the order `intake-contract.md` §6 lists them. Named once
#: so a test asserting "zero across all six" cannot quietly check five.
SURFACES: tuple[str, ...] = (
    "catalog",
    "model",
    "candidates",
    "clarification",
    "execution",
    "limit_disclosure",
)


@dataclass
class Surfaces:
    """One counter per cost surface, plus the collaborators that increment them.

    A single object rather than six loose counters, so a test can assert the
    whole vector at once — ``surfaces.counts() == dict.fromkeys(SURFACES, 0)``
    fails if a seventh surface is added and left unchecked, which six separate
    assertions would not.
    """

    catalog: int = 0
    model: int = 0
    candidates: int = 0
    clarification: int = 0
    execution: int = 0
    limit_disclosure: int = 0

    #: Every principal_ref the resolver was asked about, in order. Recorded
    #: because "the resolver was called once, about the right principal" is a
    #: different claim from "the resolver was called".
    resolver_calls: list[str] = field(default_factory=list[str])

    def counts(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in SURFACES}

    def all_zero(self) -> bool:
        return all(count == 0 for count in self.counts().values())

    def touched(self) -> list[str]:
        """Surfaces with a non-zero count, for a legible assertion message."""
        return [name for name, count in self.counts().items() if count]

    # --- the counted collaborators -------------------------------------------

    def catalog_surface(self) -> _CountingCatalog:
        return _CountingCatalog(self)

    def model_port(self) -> CountingModelPort:
        return CountingModelPort(self)

    def clarification_issuer(self) -> CountingClarificationIssuer:
        return CountingClarificationIssuer(self)

    def execution_port(self) -> CountingExecutionPort:
        return CountingExecutionPort(self)

    def limit_discloser(self) -> CountingLimitDiscloser:
        return CountingLimitDiscloser(self)


@dataclass
class _CountingCatalog:
    """The catalog surface: evaluation, and candidate discovery.

    Two counters rather than one, because `FR-089` enumerates *catalog reads* and
    *resolved candidates* separately — a design that read the catalog only to
    search would otherwise show a zero where work was done.
    """

    surfaces: Surfaces

    def evaluate(self, *_args: object, **_kwargs: object) -> object:
        self.surfaces.catalog += 1
        raise AssertionError("the fixture catalog performs no evaluation")

    def search(self, *_args: object, **_kwargs: object) -> object:
        self.surfaces.catalog += 1
        self.surfaces.candidates += 1
        raise AssertionError("the fixture catalog resolves no candidates")

    def get_metric(self, *_args: object, **_kwargs: object) -> object:
        self.surfaces.catalog += 1
        raise AssertionError("the fixture catalog holds no metric")


@dataclass
class CountingModelPort:
    """The narrowing-only model port. Unreachable while `D-20` is undeclared."""

    surfaces: Surfaces

    def narrow(self, *_args: object, **_kwargs: object) -> object:
        self.surfaces.model += 1
        raise AssertionError("no model provider is declared")


@dataclass
class CountingClarificationIssuer:
    """Clarification issuance. Unreachable while `D-21` is undeclared."""

    surfaces: Surfaces

    def issue(self, *_args: object, **_kwargs: object) -> object:
        self.surfaces.clarification += 1
        raise AssertionError("no seal key is declared")


@dataclass
class CountingExecutionPort:
    """The `ADR 0010` execution port. One call per side, never speculative."""

    surfaces: Surfaces

    def submit(self, *_args: object, **_kwargs: object) -> object:
        self.surfaces.execution += 1
        raise AssertionError("the fixture execution port reaches no warehouse")


@dataclass
class CountingLimitDiscloser:
    """Governed-limit disclosure — permitted at step 4, never at steps 1-2."""

    surfaces: Surfaces

    def disclose(self, *_args: object, **_kwargs: object) -> object:
        self.surfaces.limit_disclosure += 1
        raise AssertionError("no governed policy is resolvable")


@dataclass
class CountingResolver:
    """An ``AuthorizationContextResolver`` that records what it was asked.

    ``answer`` is the context to return; ``None`` models an unknown principal and
    ``raises`` models an identity system that failed. All three are real states a
    deployment can be in, and each must reach the same refusal.
    """

    surfaces: Surfaces
    answer: PrincipalContext | None = None
    raises: BaseException | None = None

    def resolve(self, principal_ref: str) -> PrincipalContext | None:
        self.surfaces.resolver_calls.append(principal_ref)
        if self.raises is not None:
            raise self.raises
        return self.answer
