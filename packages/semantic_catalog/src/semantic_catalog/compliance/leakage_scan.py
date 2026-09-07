"""Static leakage scan — T098 (FR-041; SC-013).

**SC-013 is proven by this scan, not by running scenarios.** A scenario shows
that one path does not leak. A scan shows that no artifact in the repository
contains the shapes at all — which is the claim SC-013 actually makes, and the
only one a reviewer can check without executing anything.

Seven categories, each with its own denylist and its own failure message, so a
hit tells the reader *what kind* of leak it is rather than "something matched":

``fact_row``          a raw result set travelling inside a governed artifact
``metric_value``      a computed figure where only definitions belong
``direct_pii``        email, CPF, phone — anything naming a person
``credential``        keys, tokens, passwords, private keys
``prompt_text``       the user's own words, which are never catalog content
``identity_claim``    a raw IdP subject or profile claim
``draft_definition``  a pending metric's unapproved definition, in a public artifact

Scanned: ``schemas/``, ``semantic/``, ``tests/fixtures/**``, the **serialised
public bundle**, and every **decision and audit payload** the caller hands in.
The last two matter most: they are generated at runtime, so a static file scan
alone would miss exactly the artifacts a consumer receives.

**Precision over breadth.** Every pattern is narrow enough that a hit is a real
finding. The tempting alternative — match ``records:`` or ``token`` anywhere and
allowlist the false positives — inverts the burden: the allowlist grows, nobody
re-reads it, and a genuine leak eventually lands on an allowlisted line. Where a
pattern must be broad, :data:`GOVERNED_IDENTIFIERS` allowlists the governed
vocabulary explicitly and nothing else.

Zero hits required. The scan is wired into CI by T100 as a blocking gate.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

__all__ = [
    "GOVERNED_IDENTIFIERS",
    "PENDING_STUB_FIELDS",
    "LeakCategory",
    "LeakFinding",
    "LeakageReport",
    "scan_paths",
    "scan_payload",
    "scan_repository",
    "scan_text",
]


class LeakCategory(StrEnum):
    """What kind of thing escaped. Each maps to one denylist."""

    FACT_ROW = "fact_row"
    METRIC_VALUE = "metric_value"
    DIRECT_PII = "direct_pii"
    CREDENTIAL = "credential"
    PROMPT_TEXT = "prompt_text"
    IDENTITY_CLAIM = "identity_claim"
    DRAFT_DEFINITION = "draft_definition"


#: Governed vocabulary that may appear anywhere. This is the **allowlist**, and
#: it is deliberately tiny: it holds field names the contracts define, not
#: values. Adding a value here would be allowlisting a leak.
GOVERNED_IDENTIFIERS: frozenset[str] = frozenset(
    {
        "catalog_release_id",
        "correlation_id",
        "data_revision_id",
        "decision_id",
        "metric_version_id",
        "policy_version",
        "principal_id",
        "snapshot_id",
        "source_commit",
        "supersedes_decision_id",
    }
)

#: Field names that carry a pending metric's unapproved definition. Their
#: presence in a *public* artifact is the leak; in the internal projection they
#: are the contract.
DRAFT_FIELDS: frozenset[str] = frozenset(
    {
        "calculation_basis",
        "source_view",
        "numerator",
        "denominator",
        "aggregation",
        "additivity",
        "grain",
        "unit",
        "time_dimension",
        "exclusions",
        "allowed_dimensions",
        "source_availability",
        "retention",
    }
)

#: The exhaustive public shape of a PENDING metric — `PendingStub`'s six fields.
#:
#: Written here rather than imported so this module keeps depending on nothing but the
#: serialised text, and **a test asserts this set still equals the dataclass's fields**,
#: so the copy cannot drift into permission by omission.
#:
#: A pending metric's entry may hold these and nothing else. That is stricter than
#: checking `DRAFT_FIELDS`: a definition field nobody thought to list is still not a
#: stub field, and it is still a leak.
PENDING_STUB_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "status",
        "missing_fields",
        "public_name",
        "owner",
        "expected_available_from",
    }
)

_PATTERNS: Mapping[LeakCategory, tuple[re.Pattern[str], ...]] = {
    # A raw result set. Narrow on purpose: `records:` is the governed shape of a
    # freshness observation and `rows` is a validation report's own field, so
    # matching either would train a reader to ignore this category.
    LeakCategory.FACT_ROW: (
        re.compile(r"\b(fact_rows|raw_rows|row_data|result_set|resultset|query_results)\b"),
        re.compile(r'"(select|from)\s+[a-z_.]+\s+(from|where)\b', re.IGNORECASE),
    ),
    # A computed figure where only a definition belongs.
    LeakCategory.METRIC_VALUE: (
        re.compile(r"\b(metric_value|computed_value|measure_value|figure)\s*[:=]\s*-?\d"),
        re.compile(r'"(value|total|count|amount)"\s*:\s*-?\d+(\.\d+)?\s*[,}\]]'),
    ),
    LeakCategory.DIRECT_PII: (
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),  # CPF
        re.compile(r"\+55\s?\(?\d{2}\)?\s?9?\d{4}[- ]?\d{4}\b"),  # BR phone
        re.compile(r"\b(full_name|first_name|last_name|birth_date|home_address)\b"),
    ),
    LeakCategory.CREDENTIAL: (
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token|refresh[_-]?token"
            r"|private[_-]?key|client[_-]?secret)\b\s*[:=]\s*['\"]?\S{8,}"
        ),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(r"(?i)\bauthorization\s*[:=]\s*['\"]?bearer\s+\S+"),
    ),
    # The user's own words. Never catalog content and never audit content.
    LeakCategory.PROMPT_TEXT: (
        re.compile(r'"(prompt|prompt_text|question|question_text|user_message|utterance)"\s*:'),
        re.compile(
            r"^\s*(prompt|prompt_text|question|question_text|user_message|utterance)\s*:",
            re.MULTILINE,
        ),
    ),
    # A raw IdP claim. `principal_id` is the governed pseudonymous form and is
    # allowlisted; these are the shapes it exists to replace.
    LeakCategory.IDENTITY_CLAIM: (
        re.compile(
            r'"(sub|upn|preferred_username|given_name|family_name'
            r"|idp_subject|oauth_subject|id_token)\"\s*:"
        ),
        re.compile(
            r"^\s*(upn|preferred_username|given_name|family_name"
            r"|idp_subject|oauth_subject|id_token)\s*:",
            re.MULTILINE,
        ),
    ),
}

_MESSAGES: Mapping[LeakCategory, str] = {
    LeakCategory.FACT_ROW: (
        "a raw result set inside a governed artifact; the catalog carries definitions, never rows"
    ),
    LeakCategory.METRIC_VALUE: "a computed figure where only a definition belongs (FR-041)",
    LeakCategory.DIRECT_PII: (
        "direct personal data; no personal data enters the catalog (FR-041, NG-10)"
    ),
    LeakCategory.CREDENTIAL: "a credential or token; the library holds none and must carry none",
    LeakCategory.PROMPT_TEXT: (
        "the requester's own words; prompt text is never catalog or audit content"
    ),
    LeakCategory.IDENTITY_CLAIM: (
        "a raw identity claim; principal_id is the governed pseudonymous form"
    ),
    LeakCategory.DRAFT_DEFINITION: "an unapproved definition in a public artifact (FR-018, FR-060)",
}


@dataclass(frozen=True, slots=True)
class LeakFinding:
    """One hit, named precisely enough to act on."""

    source: str
    line: int
    category: LeakCategory
    matched: str
    message: str

    def redacted(self) -> str:
        """The matched text, truncated. Never echo a suspected secret in full."""
        text = self.matched.strip()
        return text if len(text) <= 24 else f"{text[:21]}..."

    def render(self) -> str:
        return (
            f"{self.source}:{self.line} [{self.category.value}] {self.redacted()} — {self.message}"
        )


@dataclass(frozen=True, slots=True)
class LeakageReport:
    """Every hit across every scanned artifact. Empty is the only pass."""

    findings: tuple[LeakFinding, ...] = ()
    scanned: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.findings

    def by_category(self) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category.value] = counts.get(finding.category.value, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "clean": self.clean,
            "scanned": len(self.scanned),
            "counts": self.by_category(),
            "findings": [
                {
                    "source": f.source,
                    "line": f.line,
                    "category": f.category.value,
                    "matched": f.redacted(),
                    "message": f.message,
                }
                for f in self.findings
            ],
        }

    def render(self) -> Sequence[str]:
        header = (
            f"leakage scan: {'CLEAN' if self.clean else 'LEAK DETECTED'} "
            f"({len(self.scanned)} artifacts, {len(self.findings)} hits)"
        )
        return [header, *[f"  {f.render()}" for f in self.findings]]

    def merge(self, other: LeakageReport) -> LeakageReport:
        return LeakageReport(
            findings=self.findings + other.findings,
            scanned=self.scanned + other.scanned,
        )


def _allowlisted(line: str, matched: str) -> bool:
    """Whether the hit is a governed identifier rather than a leak.

    Only the field **name** is allowlisted, never its value: ``principal_id`` is
    governed, the string it holds is opaque by construction, and nothing here
    grants an exemption to a value that merely sits next to a governed name.
    """
    token = matched.strip().strip("\"':= ")
    return (
        token in GOVERNED_IDENTIFIERS
        or any(f'"{name}"' == token or name == token for name in GOVERNED_IDENTIFIERS)
        or any(f"{name}:" in line and token.startswith(name) for name in GOVERNED_IDENTIFIERS)
    )


def scan_text(text: str, source: str) -> tuple[LeakFinding, ...]:
    """Every denylist hit in one blob, with its line number."""
    findings: list[LeakFinding] = []
    lines = text.splitlines()
    for category, patterns in _PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                line = lines[line_number - 1] if line_number <= len(lines) else ""
                if _allowlisted(line, match.group(0)):
                    continue
                findings.append(
                    LeakFinding(
                        source=source,
                        line=line_number,
                        category=category,
                        matched=match.group(0),
                        message=_MESSAGES[category],
                    )
                )
    return tuple(findings)


def scan_paths(
    root: Path, patterns: Sequence[str] = ("**/*.yaml", "**/*.yml", "**/*.json")
) -> LeakageReport:
    """Scan every matching file under ``root``."""
    findings: list[LeakFinding] = []
    scanned: list[str] = []
    seen: set[Path] = set()
    for glob in patterns:
        for path in sorted(root.glob(glob)):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            relative = path.as_posix()
            scanned.append(relative)
            findings.extend(scan_text(path.read_text(encoding="utf-8"), relative))
    return LeakageReport(findings=tuple(findings), scanned=tuple(scanned))


def scan_payload(payload: Any, source: str) -> LeakageReport:
    """Scan a runtime payload — a decision, an audit event, a public bundle.

    Serialised first, so the scan sees exactly what a consumer would receive
    rather than a Python object graph a consumer never touches.
    """
    text = (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=1)
    )
    return LeakageReport(findings=scan_text(text, source), scanned=(source,))


def _draft_findings(public_bundle: str, pending: Iterable[str]) -> tuple[LeakFinding, ...]:
    """A PENDING metric's definition in the public projection.

    Checked against the serialised bundle rather than the object, because absence
    must be literal: a pending metric's definition is not written, not
    written-and-hidden (R-8).

    **The check is per metric, and it was not always.** The earlier form looked for
    draft FIELD NAMES anywhere in the bundle whenever any pending metric existed. That
    answered correctly for as long as **nothing at all was publishable** — the first
    metric to reach `published` put its own, entirely legitimate, definition into the
    public bundle and the scan called it a leak. A rule that only holds while the
    product ships nothing is a rule that fires when the product starts working.

    So the pending metric's own entry is what is inspected. A pending metric is
    projected as a stub — name, owner, status, and the fields it is missing — and
    **anything beyond that stub is the leak**, whether or not its name is in
    `DRAFT_FIELDS`. That is stricter than the name list and it cannot be widened by
    inventing a field the list does not know.

    If the bundle cannot be read as a mapping, the old literal text scan runs instead:
    an unreadable artefact must over-report rather than pass by being unparseable.
    """
    pending_ids = sorted(pending)
    if not pending_ids:
        return ()

    try:
        parsed: object = json.loads(public_bundle)
    except (TypeError, ValueError):
        parsed = None

    if not isinstance(parsed, dict):
        return _draft_findings_by_text(public_bundle)

    entries = cast("dict[str, object]", parsed)
    findings: list[LeakFinding] = []
    for metric_id in pending_ids:
        entry = entries.get(metric_id)
        if not isinstance(entry, dict):
            continue
        for field in sorted(set(cast("dict[str, object]", entry)) - PENDING_STUB_FIELDS):
            findings.append(
                LeakFinding(
                    source="public_bundle",
                    line=1,
                    category=LeakCategory.DRAFT_DEFINITION,
                    matched=f"{metric_id}.{field}",
                    message=_MESSAGES[LeakCategory.DRAFT_DEFINITION],
                )
            )
    return tuple(findings)


def _draft_findings_by_text(public_bundle: str) -> tuple[LeakFinding, ...]:
    """The fallback for a bundle that is not readable as a mapping.

    Kept deliberately blunt. It cannot tell whose definition it is looking at, so it
    reports every draft field name it sees — the behaviour the whole scan used to
    have, now reached only when the precise check cannot run at all.
    """
    findings: list[LeakFinding] = []
    for line_number, line in enumerate(public_bundle.splitlines() or [public_bundle], start=1):
        for field in sorted(DRAFT_FIELDS):
            if f'"{field}"' in line:
                findings.append(
                    LeakFinding(
                        source="public_bundle",
                        line=line_number,
                        category=LeakCategory.DRAFT_DEFINITION,
                        matched=field,
                        message=_MESSAGES[LeakCategory.DRAFT_DEFINITION],
                    )
                )
    return tuple(findings)


def scan_repository(
    repo_root: Path,
    *,
    public_bundle: str | None = None,
    pending_metrics: Sequence[str] = (),
    payloads: Mapping[str, Any] | None = None,
) -> LeakageReport:
    """The full SC-013 sweep: authored files, generated schemas, fixtures, payloads.

    ``public_bundle`` and ``payloads`` are supplied by the caller because they
    are produced at runtime. Scanning only what is on disk would leave the
    artifacts a consumer actually receives unscanned, which is the half that
    matters.
    """
    report = LeakageReport()
    for relative in ("schemas", "semantic", "packages/semantic_catalog/tests/fixtures"):
        target = repo_root / relative
        if target.is_dir():
            report = report.merge(scan_paths(target))

    if public_bundle is not None:
        report = report.merge(scan_payload(public_bundle, "public_bundle"))
        report = report.merge(
            LeakageReport(findings=_draft_findings(public_bundle, pending_metrics))
        )

    for name, payload in sorted((payloads or {}).items()):
        report = report.merge(scan_payload(payload, name))

    return report
