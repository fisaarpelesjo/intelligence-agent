"""Freshness approvals — T112 (FR-021, FR-076, FR-077; D-1).

A source file declares a **candidate** inventory: expected refresh interval,
delay tolerance, reporting time zone, earliest available date. Those values are
authored, reviewed and structurally valid — and none of them is authoritative
until a matching approval in ``semantic/governance/freshness-approvals.yaml``
says the business signed them off (D-1).

Why a separate governed file rather than a flag in the source: a boolean inside
``sources/{id}.yaml`` would be self-asserted by whoever edits the tolerance,
which is the review bypass the approval exists to prevent. Approvals are routed
to a different CODEOWNERS group, exactly as pending-visibility approvals are
(ADR 0003 §3).

**Comments are not controls.** The state of a source's inventory is a resolved
value here, readable by the loader, the validators and every consumer — not a
sentence in a YAML comment that ``yaml.safe_load`` discards.

Every failure resolves to **unpublishable**: missing, rejected, expired,
role-invalid, commit-mismatched, or approving values that no longer match the
candidate. There is no fallback and no default: an unapproved source keeps its
candidate values, and those values are barred from every decision.

An approval **never supplies and never modifies** a value. It restates the four
decision-bearing candidate fields and is valid only while they match, so a later
edit to the tolerance invalidates the approval instead of silently inheriting
it. The first approval that resolves establishes the governed baseline; every
decision-bearing change after that goes through the ordinary semantic-review and
versioning route (FR-033, SC-021).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictInt, field_validator, model_validator

from ._base import CatalogModel, Identifier, IsoDuration, PtBrText
from .source import Outage, Restatement, Source

__all__ = [
    "FreshnessApproval",
    "FreshnessApprovalRegistry",
    "FreshnessApprovalStatus",
    "FreshnessDenial",
]


class FreshnessApprovalStatus(StrEnum):
    """Machine-readable. ``rejected`` is a decision, not an absence."""

    APPROVED = "approved"
    REJECTED = "rejected"


class FreshnessDenial(StrEnum):
    """Why a source is unpublishable. Every member fails closed."""

    NO_APPROVAL = "no_approval"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ROLE_NOT_PERMITTED = "role_not_permitted"
    COMMIT_MISMATCH = "commit_mismatch"
    CANDIDATE_CHANGED = "candidate_changed"


class FreshnessApproval(CatalogModel):
    """One D-1 sign-off, for one source's decision-bearing inventory."""

    source_id: Identifier
    approval_status: FreshnessApprovalStatus

    # The approved values, restated. NOT a source of values: resolution compares
    # them with the candidate and refuses on any difference, so an approval can
    # never introduce, default or silently amend an inventory figure.
    expected_refresh_interval: IsoDuration
    delay_tolerance: IsoDuration
    reporting_time_zone: str
    earliest_available_date: date

    approved_by_role: Identifier = Field(
        description="A role from the ownership registry. Never an individual.",
    )
    approved_at: date
    source_commit: str = Field(min_length=7, description="Binds the approval to approved content.")
    expires_at: date | None = None

    limitations: tuple[PtBrText, ...] = ()
    known_outages: tuple[Outage, ...] = ()
    known_restatements: tuple[Restatement, ...] = ()

    @field_validator("reporting_time_zone")
    @classmethod
    def _known_iana_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"{value!r} is not a known IANA time zone") from exc
        return value

    @model_validator(mode="after")
    def _expiry_after_approval(self) -> FreshnessApproval:
        if self.expires_at is not None and self.expires_at < self.approved_at:
            raise ValueError(
                f"approval for {self.source_id} expires {self.expires_at} before it was "
                f"granted {self.approved_at}"
            )
        return self

    def matches_candidate(self, source: Source) -> bool:
        """Whether the approved values still equal the authored candidate."""
        return (
            self.expected_refresh_interval == source.expected_refresh_interval
            and self.delay_tolerance == source.delay_tolerance
            and self.reporting_time_zone == source.reporting_timezone
            and self.earliest_available_date == source.earliest_available_date
        )


def _covers(approved: str, actual: str | None) -> bool:
    """Whether the approved commit id names the commit the content is at.

    **Prefix, not equality, and the direction is the whole safety of it.** The
    approved id must be a PREFIX of the resolved one, never the reverse: a
    seven-character id in an approval is how a person writes a commit — the schema
    admits seven — while Git resolves a file's history to a full forty. Demanding
    equality would leave every hand-written approval inert, which is the same class
    of defect ADR 0033 exists to remove, arriving through a different door.

    Reversing it would be the unsafe direction: a full id in the approval would
    then be "covered" by any short prefix somebody happened to pass.

    ``None`` never covers. The caller could not say what commit the content is at,
    and an unknown is not a match.

    **This is an implementation choice made while executing ADR 0033, and it is
    declared rather than buried.** The ADR authorized changing the comparand; a
    comparand of a different length turned out to be part of that. Seven hex
    characters is the schema's own floor, so the ambiguity this admits is exactly
    the ambiguity the schema already admits.
    """
    if actual is None:
        return False
    return actual.startswith(approved)


class FreshnessApprovalRegistry(CatalogModel):
    """``semantic/governance/freshness-approvals.yaml`` — deny-by-default.

    Seeded **empty**, which is the correct initial state while D-1 is open: with
    no approvals, every source is unpublishable and no candidate tolerance can
    reach a decision or a user-facing refusal.
    """

    catalog_schema_version: StrictInt
    kind: Literal["freshness_approvals"]
    approvals: tuple[FreshnessApproval, ...] = ()

    @model_validator(mode="after")
    def _one_approval_per_source(self) -> FreshnessApprovalRegistry:
        seen: set[str] = set()
        for approval in self.approvals:
            if approval.source_id in seen:
                raise ValueError(
                    f"two freshness approvals for {approval.source_id!r}; ambiguous approval "
                    "is never resolved by preference"
                )
            seen.add(approval.source_id)
        return self

    def get(self, source_id: str) -> FreshnessApproval | None:
        return next((a for a in self.approvals if a.source_id == source_id), None)

    def evaluate(
        self,
        source: Source,
        *,
        source_content_commit: str | None,
        on: date,
        permitted_roles: frozenset[str] | None = None,
    ) -> FreshnessDenial | None:
        """``None`` means the source is publishable; a denial means it is not.

        Checked in order of decreasing bluntness so the reported reason is the
        most actionable one. No branch returns a value, a default or a repaired
        candidate — the only outcomes are "approved as authored" and "refused".

        **``source_content_commit`` is the commit that last modified THIS SOURCE'S
        OWN FILE**, and the parameter is named for what it is because the old name
        is what caused ADR 0033. It used to be ``current_commit`` — the commit the
        caller was publishing — so the promise in
        ``semantic/governance/freshness-approvals.yaml`` was *binds to the content
        it approved* while the implementation bound to repository state. Measured:
        an approval was inert from the commit after the one it named, and neither
        caller ever passed that one.

        **``None`` denies, and denying is the honest answer rather than a
        conservative one.** It means the caller could not determine which commit
        last touched the file — so whether the approved content still stands is
        *unknown*, and an unknown is not an approval. It is also what preserves
        today's observable behaviour for a caller that supplies nothing: such a
        caller was already getting ``COMMIT_MISMATCH`` on every real commit.
        """
        approval = self.get(source.id)
        if approval is None:
            return FreshnessDenial.NO_APPROVAL
        if approval.approval_status is FreshnessApprovalStatus.REJECTED:
            return FreshnessDenial.REJECTED
        if approval.expires_at is not None and on > approval.expires_at:
            return FreshnessDenial.EXPIRED
        if permitted_roles is not None and approval.approved_by_role not in permitted_roles:
            return FreshnessDenial.ROLE_NOT_PERMITTED
        if not _covers(approval.source_commit, source_content_commit):
            return FreshnessDenial.COMMIT_MISMATCH
        if not approval.matches_candidate(source):
            return FreshnessDenial.CANDIDATE_CHANGED
        return None

    def is_publishable(
        self,
        source: Source,
        *,
        source_content_commit: str | None,
        on: date,
        permitted_roles: frozenset[str] | None = None,
    ) -> bool:
        """Convenience predicate over :meth:`evaluate`. False on every failure."""
        return (
            self.evaluate(
                source,
                source_content_commit=source_content_commit,
                on=on,
                permitted_roles=permitted_roles,
            )
            is None
        )
