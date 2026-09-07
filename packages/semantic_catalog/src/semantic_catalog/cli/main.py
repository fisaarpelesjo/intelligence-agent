"""Steward CLI — T096 (FR-013, FR-033; SC-011; library-and-cli-contract §2).

SC-011 requires a steward to add or amend a metric and see it validated **within
one working day with no engineering change**. That is only true if they can run
the same checks CI runs, locally, before opening a pull request. This is that
command, and every subcommand delegates to the library rather than re-deciding
anything: a second implementation of "valid" would eventually disagree with the
first, and the disagreement would surface as a CLI that passes while CI fails.

**No command writes catalog content.** Authoring is editing YAML in a branch and
opening a pull request — that is what makes Git the change record (R-1, FR-037).
The only writes any subcommand performs are to a **release ledger** the steward
names explicitly with ``--ledger``, and to a schema directory under ``schema
export``. Neither is catalog content, and neither has a default that would let a
write happen unasked.

**Three exit codes** (``library-and-cli-contract.md §4``: ``0`` clean, ``1``
violations, ``2`` usage error). The line between 1 and 2 is not "how bad is it"
— it is **whether the command got to do its job**:

``0``  the work was done and the answer is yes
``1``  the work was done and the answer is no — *governed content is wrong*
``2``  the work never started — *the call is wrong*

**Exit 1 covers governed, version-controlled content**: the catalog at any layer
(L1-L4), the generated schemas, the governed readiness record, the release
ledger's own integrity, a release-validation refusal, and a governed decision
denial. A catalog file that will not parse at all belongs here too, and that is
the contract's answer rather than a judgement call: L1 exists to turn an
unloadable file into a *finding* rather than an exception, precisely so a broken
file is reported instead of silently skipped. A steward whose YAML does not
parse has a violation to fix, not a command they typed wrong.

**Exit 2 covers the invocation**: an unknown subcommand, a missing or invalid
argument, a path that does not exist, or a caller-supplied evidence file — a
freshness snapshot, an observed-coverage export, a release ledger — that will
not load. Nothing was validated, so **nothing is printed on stdout**: a verdict
beside a usage error would read as a result.

Collapsing the two would leave CI unable to tell "the catalog has a problem"
from "the pipeline is broken", and a broken pipeline reporting a catalog
violation sends the steward to edit a file that is fine.

**Fail closed everywhere.** A malformed catalog, schema drift, an L1-L4 failure,
a failed release validation, a missing approval, or fixture evidence standing in
for a capability already declared ready — all refuse. Nothing degrades to a
partial answer, no default stands in for a value nobody approved, and no
traceback escapes: a crash is not a verdict.

**No SQL, no warehouse, no credentials.** The CLI reads authored YAML and
caller-supplied fixture snapshots. It opens no connection and dereferences no
``source_view``. ``diff`` shells out to Git, which is the one repository fact the
CLI layer is allowed to know; the library still opens no repository.

Human-facing output is the governed pt-BR wording the catalog already holds,
printed verbatim — never translated, summarised or regenerated here (FR-055).
``--format json`` uses ``ensure_ascii=False`` so that wording survives the round
trip instead of degrading into escape sequences.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError

from ..compliance.leakage_scan import scan_repository
from ..compliance.readiness import Capability, GuardMode, ReadinessError, guard, load_readiness
from ..compliance.report import compliance_report
from ..contracts._base import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from ..contracts.access_tag import PrincipalType
from ..contracts.export import check_drift, export_all
from ..contracts.policy import PolicyUnresolvableError
from ..freshness.external import load_snapshot
from ..loader.bundle import Bundle, build_bundle, serialise_public
from ..loader.load import CatalogLoadError, LoadedCatalog, load_catalog
from ..loader.projection import PendingStub
from ..loader.release_state import (
    ActivationEvent,
    CatalogRelease,
    EventKind,
    ReleaseLedger,
    ReleaseState,
    ReleaseStateError,
)
from ..resolution.as_of import resolve_as_of
from ..resolution.fingerprint import version_fingerprint
from ..validation.decision import CatalogValidationRequest, DateRange
from ..validation.l1_schema import validate_tree
from ..validation.l3_reconciliation import ObservedCoverageSet, load_observed_coverage
from ..validation.l4_version import FingerprintBaseline, moved_fields
from ..validation.matrix import allowed_combinations
from ..validation.pipeline import evaluate
from ..validation.release import validate_release
from ..validation.result import (
    Severity,
    Subject,
    ValidationFinding,
    ValidationLayer,
    ValidationReport,
)

__all__ = ["EXIT_INVOCATION", "EXIT_OK", "EXIT_VIOLATION", "build_parser", "main"]

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_INVOCATION = 2


class _InvocationError(Exception):
    """The **call** is wrong. Exit 2, never 1.

    Exit 2 means "I could not begin": an unknown subcommand, a missing or
    invalid argument, a path that does not exist, or a caller-supplied evidence
    file that will not load. Nothing was validated, so no verdict is printed.
    """


class _CatalogError(Exception):
    """The **governed content** is wrong. Exit 1, never 2.

    Exit 1 means "I did the work and the answer is no". Version-controlled
    content that exists and is invalid belongs here — including a catalog file
    that will not parse at all.

    That last point is the contract's, not a judgement call. L1 exists to turn
    an unloadable file into a *finding* rather than an exception, precisely so a
    broken file is reported instead of silently skipped, and
    ``library-and-cli-contract.md §4`` classifies exit 1 as "violations" against
    exit 2 as "usage error". A steward whose YAML does not parse has a violation
    to fix, not a command they typed wrong.
    """

    def __init__(self, report: ValidationReport, summary: str) -> None:
        super().__init__(summary)
        self.report = report
        self.summary = summary

    @classmethod
    def of(cls, subject: str, detail: str, *, rule: str, kind: str = "catalog") -> _CatalogError:
        """A single-finding violation, for content with no layer of its own."""
        report = ValidationReport.from_findings(
            [
                ValidationFinding(
                    layer=ValidationLayer.L1_SCHEMA,
                    rule=rule,
                    severity=Severity.ERROR,
                    subject=Subject(kind=kind, identifier=subject),
                    message=detail,
                )
            ]
        )
        return cls(report, detail)


# --- shared helpers ---------------------------------------------------------


def _emit(payload: dict[str, Any], lines: Sequence[str], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    for line in lines:
        print(line)


def _on(value: str | None) -> date:
    if value is None:
        return datetime.now(tz=UTC).date()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _InvocationError(f"not a date: {value!r} ({exc})") from exc


def _evaluated_at(value: str | None) -> datetime | None:
    """The instant to stamp on the decision, when the caller pins one.

    ``None`` means "now", which is correct for an interactive run and makes the
    output non-reproducible by construction — the stamp is a real timestamp, not
    a derived one, and pretending otherwise would put a fiction in the audit
    trail. A caller who needs byte-identical output supplies the instant.
    """
    if value is None:
        return None
    try:
        stamped = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _InvocationError(f"not a timestamp: {value!r} ({exc})") from exc
    return stamped if stamped.tzinfo else stamped.replace(tzinfo=UTC)


def _catalog_root(value: str) -> Path:
    root = Path(value)
    if not root.is_dir():
        raise _InvocationError(f"catalog path is not a directory: {root}")
    return root


def _load(root: Path) -> LoadedCatalog:
    """Load a catalog, or raise the L1 report explaining why it will not load.

    The report comes from ``validate_tree`` rather than from the exception,
    because L1 already knows how to describe an unloadable file: it names the
    file, the rule and the reason. Re-wording the exception here would give the
    steward a second, worse account of the same problem.
    """
    try:
        return load_catalog(root)
    except (CatalogLoadError, ValidationError) as exc:
        report = validate_tree(root)
        if report.is_valid():
            # L1 saw nothing, yet the load failed — a duplicate identifier
            # across two well-formed files, for instance. Still a violation.
            raise _CatalogError.of(
                root.as_posix(), f"{root} does not load: {exc}", rule="catalog_does_not_load"
            ) from exc
        raise _CatalogError(report, f"{root} does not load") from exc


def _source_files(root: Path) -> dict[str, Path]:
    """Source id -> the file that declares it, read rather than assumed.

    Not ``sources/<id>.yaml``: the loader buckets by the ``kind`` field, so the
    filename is a convention and not a contract. A mapping built from the
    convention would silently miss a source declared in a differently named file
    — and missing means denied, which would look like a governance decision.
    """
    found: dict[str, Path] = {}
    directory = root / "sources"
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue
        # The same shape `_lagging_schema_versions` uses thirty lines below, and for the same
        # reason: `yaml.safe_load` answers `Any`, so every value taken out of the document is
        # untyped and strict mode reports it at each USE rather than at the read. Declaring the
        # shape where the file ENTERS is the rule this repository already applies to a figure.
        document = cast("dict[str, object]", raw)
        if document.get("kind") == "source":
            identifier = document.get("id")
            if isinstance(identifier, str) and identifier:
                found[identifier] = path
    return found


def _source_commits_from_git(root: Path) -> dict[str, str]:
    """The commit that last modified each source's own file — ADR 0033.

    Read HERE rather than in the library, because reading Git is a repository act
    and `001` holds no repository handle by design. ADR 0033 says the caller
    supplies it; this is the caller.

    **A source whose file has uncommitted changes is OMITTED, and omission
    denies.** Its content is not any commit, so no approval can be said to still
    cover it — ``git log`` would answer the last committed state and quietly
    approve an edit nobody reviewed.

    A git failure omits too, for the same reason: an approval that survives an
    unreadable repository is an approval nobody can check.
    """
    repo = root.resolve().parent
    commits: dict[str, str] = {}
    for identifier, path in _source_files(root).items():
        try:
            relative = path.resolve().relative_to(repo).as_posix()
        except ValueError:
            continue
        try:
            if _git(repo, "status", "--porcelain", "--", relative).strip():
                continue
            head = _git(repo, "log", "-1", "--format=%H", "--", relative).strip()
        except _InvocationError:
            continue
        if head:
            commits[identifier] = head
    return commits


def _declared_source_commits(values: list[str] | None) -> dict[str, str]:
    """``--source-commit id=sha``, parsed. Repeatable, and last wins on a repeat.

    **This exists because a catalog is not always a Git tree, and only the caller
    knows that.** The fixtures under `tests/fixtures/` declare approvals naming
    invented commits — `fixture0` — which no real file history can equal. Under
    content binding they would be permanently denied, and that would be the
    binding being wrong about them rather than them being unapproved.

    So the caller states the mapping when it knows it, and Git answers for the
    rest. No contract changed to make that possible: ADR 0033 already said
    resolving the commit belongs to whoever invokes.
    """
    declared: dict[str, str] = {}
    for value in values or ():
        identifier, separator, commit = value.partition("=")
        if not separator or not identifier.strip() or not commit.strip():
            raise _InvocationError(f"--source-commit expects <source_id>=<commit>, got {value!r}")
        declared[identifier.strip()] = commit.strip()
    return declared


def _bundle(root: Path, commit: str, on: date, declared: list[str] | None = None) -> Bundle:
    """**Explicit beats resolved, and resolved beats nothing.**

    A source named on the command line takes the stated commit; every other source
    takes what Git says about its file. That order is the only one that is safe:
    the caller is the party that knows whether a catalog is versioned at all, and
    silently letting Git override an explicit statement would make the flag a
    suggestion.
    """
    stated = _declared_source_commits(declared)
    resolved = _source_commits_from_git(root)
    try:
        return build_bundle(
            _load(root),
            current_commit=commit,
            on=on,
            source_commits={**resolved, **stated},
        )
    except PolicyUnresolvableError as exc:
        raise _InvocationError(f"no governed policy is effective on {on}: {exc}") from exc


def _snapshot(value: str | None):
    """Observed external state, supplied by the caller. Never fetched.

    ``None`` is not "healthy": the coverage and freshness gates treat an absent
    snapshot as an unknown state and refuse.
    """
    if value is None:
        return None
    path = Path(value)
    if not path.is_file():
        raise _InvocationError(f"freshness snapshot not found: {path}")
    try:
        return load_snapshot(path)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        # yaml.YAMLError is not a ValueError, so omitting it here let a parse
        # error escape as a traceback instead of an exit code.
        raise _InvocationError(f"freshness snapshot does not load: {exc}") from exc


def _coverage(value: str | None) -> ObservedCoverageSet | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_file():
        raise _InvocationError(f"observed coverage not found: {path}")
    try:
        return load_observed_coverage(path)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise _InvocationError(f"observed coverage does not load: {exc}") from exc


def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _schema_version_findings(root: Path) -> tuple[str, ...]:
    """Authored files whose schema version is not the current one.

    The loader already refuses anything outside ``SUPPORTED_SCHEMA_VERSIONS`` by
    raising, so this reports the softer case: a file on ANY accepted version below
    the current one — it loads today and stops loading at some later bump. The
    window is three wide today, so "below current" is not a single version.

    Reading the raw payload rather than the model is deliberate — the model has
    already been upgraded in memory by then.
    """
    lagging: list[str] = []
    for path in sorted(root.glob("**/*.yaml")):
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        version = cast("dict[str, object]", raw).get("catalog_schema_version")
        if isinstance(version, int) and version != SCHEMA_VERSION:
            lagging.append(
                f"{path.as_posix()}: catalog_schema_version {version} (current {SCHEMA_VERSION})"
            )
    return tuple(lagging)


# --- validate ---------------------------------------------------------------


def _cmd_validate(args: argparse.Namespace) -> int:
    root = _catalog_root(args.path)
    on = _on(args.on)
    # T109/D-12 (ciclo 539): --coverage-live le semantic.metric_availability VIVO pelo
    # caminho do proprio pacote (identidade dedicada; is_fixture=False) — o unico modo em
    # que a limitation eterna do validate morre com verdade em vez de com um arquivo.
    if getattr(args, "coverage_live", False):
        if args.coverage:
            raise _InvocationError("--coverage and --coverage-live are two sources; pick one")
        if not args.credentials:
            raise _InvocationError(
                "--coverage-live needs --credentials FILE; this package knows no "
                "environment variable by design (the d_15 scope rule)"
            )
        from ..freshness.warehouse_read import (
            WarehouseUnreachable,
            client_from_credentials,
            read_observed_coverage,
        )

        try:
            coverage = read_observed_coverage(client_from_credentials(args.credentials))
        except WarehouseUnreachable as unreachable:
            raise _InvocationError(str(unreachable)) from unreachable
    else:
        coverage = _coverage(args.coverage)
    as_json = args.format == "json"

    if args.release:
        validation = validate_release(
            root,
            commit=args.commit,
            on=on,
            codeowners=Path(args.codeowners) if args.codeowners else None,
            observed=coverage,
        )
        _emit(
            {
                "commit": validation.commit,
                "valid": validation.valid,
                "errors": len(validation.errors),
                "findings": list(validation.report.render()),
            },
            [
                f"release validation for {validation.commit}: "
                f"{'VALID' if validation.valid else 'INVALID'}",
                *[f"  {line}" for line in validation.report.render()],
            ],
            as_json=as_json,
        )
        return EXIT_OK if validation.valid else EXIT_VIOLATION

    # L1 first. A tree that does not load has findings to report, and running
    # the later layers over a half-loaded catalog would report consequences
    # instead of the cause.
    schema_report = validate_tree(root)
    if not schema_report.is_valid():
        _emit(
            {
                "path": root.as_posix(),
                "strict": args.strict,
                "valid": False,
                "errors": len(schema_report.errors),
                "warnings": len(schema_report.warnings),
                "schema_version_findings": [],
                "findings": list(schema_report.render()),
                "limitations": [],
            },
            [
                f"validate {root}: FAIL ({len(schema_report.errors)} error(s), "
                f"{len(schema_report.warnings)} warning(s))",
                *[f"  {line}" for line in schema_report.render()],
            ],
            as_json=as_json,
        )
        return EXIT_VIOLATION

    lagging = _schema_version_findings(root) if args.check_schema_version else ()
    report = compliance_report(
        root,
        current_commit=args.commit,
        on=on,
        coverage=coverage,
        codeowners=Path(args.codeowners) if args.codeowners else None,
    )
    validation = report.validation
    failed = (
        not validation.is_valid() or bool(lagging) or (args.strict and bool(validation.warnings))
    )
    _emit(
        {
            "path": root.as_posix(),
            "strict": args.strict,
            "valid": not failed,
            "errors": len(validation.errors),
            "warnings": len(validation.warnings),
            "schema_version_findings": list(lagging),
            "findings": list(validation.render()),
            "limitations": list(report.limitations),
        },
        [
            f"validate {root}: {'FAIL' if failed else 'OK'} "
            f"({len(validation.errors)} error(s), {len(validation.warnings)} warning(s))",
            *[f"  {line}" for line in validation.render()],
            *[f"  schema-version: {line}" for line in lagging],
            *[f"  limitation: {text}" for text in report.limitations],
        ],
        as_json=as_json,
    )
    return EXIT_VIOLATION if failed else EXIT_OK


# --- explain ----------------------------------------------------------------


def _cmd_explain(args: argparse.Namespace) -> int:
    root = _catalog_root(args.path)
    on = _on(args.on)
    bundle = _bundle(root, args.commit, on, args.source_commit)
    as_json = args.format == "json"

    metric = bundle.internal.metrics.get(args.metric)
    if metric is None:
        _emit(
            {"metric": args.metric, "governed": False},
            [f"metric {args.metric!r} is not governed by this catalog"],
            as_json=as_json,
        )
        return EXIT_VIOLATION

    state = bundle.lifecycles[args.metric]
    resolved = resolve_as_of(metric, on)
    projection = bundle.public[args.metric]

    payload: dict[str, Any] = {
        "metric": args.metric,
        "governed": True,
        "as_of": on.isoformat(),
        "lifecycle": state.lifecycle.value,
        "metric_version_id": f"{args.metric}@{resolved.version}" if resolved else None,
        "owner": metric.owner,
        "access": metric.access,
        "missing_fields": list(state.missing_fields),
        "pending_reasons": [reason.value for reason in state.reasons],
        "unapproved_sources": list(state.unapproved_sources),
        "public_projection": projection.to_public_dict(),
    }
    if resolved is not None:
        payload["effective_from"] = resolved.effective_from.isoformat()
        payload["effective_to"] = (
            resolved.effective_to.isoformat() if resolved.effective_to else None
        )
        payload["limitations"] = list(resolved.content.limitations)
    if metric.deprecation is not None:
        payload["deprecated_from"] = metric.deprecation.deprecated_from.isoformat()
        payload["replacement_metric_id"] = metric.deprecation.replacement_metric_id

    lines = [
        f"{args.metric} as of {on}: {state.lifecycle.value}",
        f"  version      {payload['metric_version_id'] or '(none in effect)'}",
        f"  owner        {metric.owner}",
        f"  access       {metric.access}",
    ]
    if isinstance(projection, PendingStub):
        lines.append(f"  unset fields {', '.join(state.missing_fields) or '(none)'}")
        lines.append(f"  reasons      {', '.join(r.value for r in state.reasons)}")
    if state.unapproved_sources:
        lines.append(f"  unapproved   {', '.join(state.unapproved_sources)}")
    if resolved is not None:
        lines += [f"  limitacao    {text}" for text in resolved.content.limitations]
    _emit(payload, lines, as_json=as_json)
    return EXIT_OK


# --- check ------------------------------------------------------------------


def _cmd_check(args: argparse.Namespace) -> int:
    root = _catalog_root(args.path)
    on = _on(args.on)
    bundle = _bundle(root, args.commit, on, args.source_commit)
    as_json = args.format == "json"

    try:
        start, end = date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
    except ValueError as exc:
        raise _InvocationError(f"not a date: {exc}") from exc
    if end < start:
        raise _InvocationError(f"period ends {end} before it starts {start}")

    release: CatalogRelease | None = None
    if args.ledger:
        ledger = _read_ledger(Path(args.ledger))
        target = args.release_id or bundle.release_id
        release = ledger.resolve(target)
        if release is None and args.release_id:
            raise _InvocationError(f"release {target} is not in the ledger")

    try:
        request = CatalogValidationRequest(
            metrics=tuple(_split(args.metric)),
            dimensions=tuple(_split(args.dimensions)),
            sources=tuple(_split(args.sources)),
            date_range=DateRange(start=start, end=end),
            requester_access=tuple(_split(args.access)),
            aggregate=args.aggregate,
        )
    except ValidationError as exc:
        raise _InvocationError(f"invalid request: {exc}") from exc

    decision = evaluate(
        request,
        bundle,
        principal_type=PrincipalType(args.principal_type),
        authorization_scope=args.scope,
        on=on,
        snapshot=_snapshot(args.freshness),
        release=release,
        evaluated_at=_evaluated_at(args.evaluated_at),
    )

    lines = [
        f"{decision.outcome.value} / {decision.reason_code.value}",
        f"  subject   {decision.subject.kind.value} {decision.subject.id}",
        f"  mensagem  {decision.message_pt_br}",
        f"  decision  {decision.decision_id}",
        f"  release   {decision.catalog_release_id}",
        f"  finality  {decision.finality.value} · reproducibility {decision.reproducibility.value}",
        *[f"  evidence  {ref.kind.value}:{ref.id}" for ref in decision.evidence_refs],
        *[f"  segment   {s.metric_version_id} {s.start}..{s.end}" for s in decision.segments],
        *[f"  limitacao {lim.code} {lim.applies_to}" for lim in decision.limitations],
    ]
    # T110 / D-13 (OD-103, ciclo 537): TODA decisao do steward emite um evento no sink
    # operacional — ALLOW e DENY igualmente; uma emissao recusada SOBE (AuditEmissionError
    # nunca engolida). O produtor que existia sem sink e este comando; agora esta ligado.
    from ..provenance.audit_emit import emit_for_decision
    from ..provenance.file_archive import DEFAULT_ARCHIVE, FileAuditArchive

    archive = FileAuditArchive(Path(args.audit_path) if args.audit_path else DEFAULT_ARCHIVE)
    emit_for_decision(
        decision,
        request,
        bundle,
        archive,
        principal_id=args.principal,
        principal_type=PrincipalType(args.principal_type),
        correlation_id=args.correlation_id or decision.decision_id,
        authorization_scope=args.scope,
    )
    lines.append(f"  auditoria {archive.path}")

    _emit(decision.model_dump(mode="json"), lines, as_json=as_json)
    return EXIT_VIOLATION if decision.is_denial else EXIT_OK


# --- matrix -----------------------------------------------------------------

_MATRIX_COLUMNS = (
    "metric_id",
    "source_id",
    "dimension_id",
    "aggregation",
    "grain",
    "unit",
    "time_dimension",
    "additivity",
)


def _cmd_matrix(args: argparse.Namespace) -> int:
    root = _catalog_root(args.path)
    on = _on(args.on)
    bundle = _bundle(root, args.commit, on, args.source_commit)

    matrix = allowed_combinations(
        bundle,
        access=_split(args.access),
        principal_type=PrincipalType(args.principal_type),
        authorization_scope=args.scope,
        on=on,
        snapshot=_snapshot(args.freshness),
    )
    rows = [
        {
            "metric_id": row.metric_id,
            "source_id": row.source_id,
            "dimension_id": row.dimension_id or "",
            "aggregation": row.aggregation,
            "grain": row.grain,
            "unit": row.unit,
            "time_dimension": row.time_dimension,
            "additivity": row.additivity,
        }
        for row in matrix.rows
    ]

    if args.format == "json":
        print(
            json.dumps(
                {"evaluated_on": on.isoformat(), "rows": rows},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    elif args.format == "csv":
        print(",".join(_MATRIX_COLUMNS))
        for row in rows:
            print(",".join(f'"{row[key]}"' for key in _MATRIX_COLUMNS))
    else:
        print("| " + " | ".join(_MATRIX_COLUMNS) + " |")
        print("|" + "|".join(["---"] * len(_MATRIX_COLUMNS)) + "|")
        for row in rows:
            print("| " + " | ".join(row[key] for key in _MATRIX_COLUMNS) + " |")
    return EXIT_OK


# --- diff -------------------------------------------------------------------


def _git(repo: Path, *argv: str) -> str:
    """Run Git and decode its output as **UTF-8**, always.

    Not the locale codec. Authored content is pt-BR and the contracts declare it
    UTF-8; decoding it as cp1252 turns every accented character into a different
    string, and ``diff`` would then report a Semantic change on every metric
    whose ``calculation_basis`` contains an accent — a version bump demanded by
    an encoding bug.
    """
    try:
        result = subprocess.run(
            ["git", *argv],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=True,
        )
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError) as exc:
        raise _InvocationError(f"git {' '.join(argv)} failed: {exc}") from exc
    return result.stdout


def _resolve_base(repo: Path, base: str) -> str:
    """Prove the base ref names a real commit **before** reading its tree.

    Without this the two ways ``ls-tree`` returns nothing — an unknown ref and a
    real ref whose tree simply holds no catalog — arrive indistinguishable, and
    the bootstrap path below would read a typo in ``--base`` as "this is the
    first catalog" and wave the version gate through. Fail closed: the ref must
    resolve first, and only then may an empty listing be allowed to mean
    anything.
    """
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").strip()
    except _InvocationError as exc:
        raise _InvocationError(f"base ref does not resolve to a commit: {base}") from exc


def _diff_bootstrap(base: str, relative: str, current: LoadedCatalog, *, as_json: bool) -> int:
    """The base ref is valid and genuinely carries no catalog: the first one.

    Reached **only** after the base ref has been proved to resolve and the
    current catalog has been proved to load. Every version block is the initial
    governed addition — there is no prior definition, so no bump can be owed and
    no closed block can have been edited. That makes the verdict ``0`` on its
    own terms, not by skipping the gate: the gate ran and found nothing to
    enforce against.

    This state is reachable exactly once in a repository's life. The moment the
    base carries a catalog, ``_cmd_diff`` takes the normal path and full
    Semantic-version enforcement applies again.
    """
    changes: list[dict[str, Any]] = [
        {
            "metric": metric_id,
            "version": version.version,
            "classification": "initial_catalog",
            "fields": [],
            "requires_new_version": False,
            "closed": False,
            "verdict": "the first governed definition; there is no prior version to bump",
        }
        for metric_id, metric in sorted(current.metrics.items())
        for version in metric.versions
    ]
    lines = [
        f"diff against {base}: no catalog at {relative} in the base — initial governed addition",
        f"  {len(current.metrics)} metric(s), {len(changes)} version block(s) "
        "added as the first catalog",
    ]
    lines += [
        f"  {c['metric']}@{c['version']} [initial_catalog] - — {c['verdict']}" for c in changes
    ]
    _emit(
        {
            "base": base,
            "base_catalog_present": False,
            "bootstrap": True,
            "changes": changes,
            "requires_new_version": False,
        },
        lines,
        as_json=as_json,
    )
    return EXIT_OK


def _cmd_diff(args: argparse.Namespace) -> int:
    """Classify every change and state whether a new version block is required.

    The steward-facing half of the version gate (R-6): CI enforces it, and this
    lets a steward see the verdict before opening a pull request rather than
    discovering it in review.

    The baseline is materialised from Git into a temporary directory and loaded
    through the same loader, so the comparison is model-to-model rather than
    text-to-text. The library still opens no repository — the CLI is the layer
    allowed to know what a ref is.

    Five failure modes are kept apart on purpose, because collapsing any pair of
    them is how a gate stops being one: an unusable repository, a base ref that
    does not resolve, a missing current catalog (all exit 2 — the call is
    wrong), and malformed base or current content (exit 1 — governed content is
    wrong, and the message says *which side*). A base that legitimately carries
    no catalog is none of those, and is the one case that proceeds.
    """
    root = _catalog_root(args.path)
    repo = Path(args.repo)
    if not (repo / ".git").exists():
        raise _InvocationError(f"not a git repository: {repo}")
    try:
        relative = root.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError as exc:
        raise _InvocationError(f"{root} is not inside {repo}") from exc

    _resolve_base(repo, args.base)
    listing = _git(repo, "ls-tree", "-r", "--name-only", args.base, "--", relative).split()

    # Loaded before the branch so a malformed current catalog fails the same way
    # whether or not the base has one. Bootstrap must not become the path where
    # unloadable content goes unreported.
    current = _load(root)

    if not listing:
        return _diff_bootstrap(args.base, relative, current, as_json=args.format == "json")

    with tempfile.TemporaryDirectory() as tmp:
        baseline_root = Path(tmp) / "baseline"
        for tracked in listing:
            target = baseline_root / Path(tracked).relative_to(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            # newline="" keeps the blob byte-faithful to the ref rather than
            # re-encoding line endings for the local platform.
            with target.open("w", encoding="utf-8", newline="") as handle:
                handle.write(_git(repo, "show", f"{args.base}:{tracked}"))
        try:
            baseline = FingerprintBaseline.from_catalog(_load(baseline_root))
        except _CatalogError as exc:
            # Same class of fault as a malformed current tree, but the steward
            # cannot fix it here — naming the side saves them looking.
            raise _CatalogError.of(
                relative,
                f"the catalog at {args.base} does not load: {exc.summary}",
                rule="base_catalog_malformed",
            ) from exc

    current_records = FingerprintBaseline.from_metrics(current.metrics).records

    changes: list[dict[str, Any]] = []
    for metric_id, metric in sorted(current.metrics.items()):
        known = set(baseline.versions_of(metric_id))
        appended = bool({v.version for v in metric.versions} - known) if known else False
        for version in metric.versions:
            record = baseline.records.get((metric_id, version.version))
            if record is None:
                changes.append(
                    {
                        "metric": metric_id,
                        "version": version.version,
                        "classification": "new_version_block",
                        "fields": [],
                        "requires_new_version": False,
                        "closed": False,
                        "verdict": "a new version block was appended, which is the supported path",
                    }
                )
                continue
            if version_fingerprint(metric, version) == record.fingerprint:
                continue
            moved = list(
                moved_fields(record.inputs, current_records[(metric_id, version.version)].inputs)
            )
            changes.append(
                {
                    "metric": metric_id,
                    "version": version.version,
                    "classification": "semantic",
                    "fields": moved,
                    "requires_new_version": not appended,
                    "closed": record.is_closed,
                    "verdict": (
                        "a closed version was edited in a Semantic field; periods already "
                        "answered under it must not change"
                        if record.is_closed
                        else "a new version block is required"
                        if not appended
                        else "a new version block was appended, which is the supported path"
                    ),
                }
            )

    blocking = [c for c in changes if c["requires_new_version"] or c["closed"]]
    lines = [f"diff against {args.base}: {len(changes)} classified change(s)"]
    lines += [
        f"  {c['metric']}@{c['version']} [{c['classification']}] "
        f"{', '.join(c['fields']) or '-'} — {c['verdict']}"
        for c in changes
    ]
    if not changes:
        lines.append("  no Semantic-class change; no version bump required")
    _emit(
        {
            "base": args.base,
            "base_catalog_present": True,
            "bootstrap": False,
            "changes": changes,
            "requires_new_version": bool(blocking),
        },
        lines,
        as_json=args.format == "json",
    )
    return EXIT_VIOLATION if blocking else EXIT_OK


# --- compliance -------------------------------------------------------------


def _cmd_compliance(args: argparse.Namespace) -> int:
    root = _catalog_root(args.path)
    on = _on(args.on)
    coverage = _coverage(args.coverage)
    fixtures_used = [Capability.EXT_A] if coverage is not None and coverage.is_fixture else []

    # Raises the L1 report when the tree does not load, so every command
    # describes an unloadable catalog the same way.
    _load(root)

    report = compliance_report(
        root,
        current_commit=args.commit,
        on=on,
        coverage=coverage,
        codeowners=Path(args.codeowners) if args.codeowners else None,
    )
    readiness_path = Path(args.readiness)
    try:
        state = load_readiness(readiness_path)
    except ReadinessError as exc:
        # Version-controlled governed content. A record nobody can parse must
        # not read as "nothing is declared", which is what a usage error would
        # let a caller assume.
        raise _CatalogError.of(
            readiness_path.as_posix(),
            f"readiness record is malformed: {exc}",
            rule="readiness_record_malformed",
            kind="readiness",
        ) from exc
    verdict = guard(state, mode=GuardMode(args.mode), fixtures_used=fixtures_used)

    payload = report.to_dict()
    payload["readiness"] = verdict.to_dict()
    _emit(payload, [*report.render(), *verdict.render()], as_json=args.format == "json")

    if not verdict.permitted:
        return EXIT_VIOLATION
    return EXIT_OK if report.is_compliant() else EXIT_VIOLATION


# --- schema -----------------------------------------------------------------


def _cmd_schema(args: argparse.Namespace) -> int:
    target = Path(args.out)
    as_json = args.format == "json"

    if args.check:
        if not target.is_dir():
            raise _InvocationError(f"schema directory not found: {target}")
        drift = check_drift(target)
        _emit(
            {"checked": target.as_posix(), "drift": list(drift), "clean": not drift},
            [
                f"schema drift: {'CLEAN' if not drift else 'DRIFT'} ({len(drift)} file(s))",
                *[f"  {name}: regenerate; never hand-edit" for name in drift],
            ],
            as_json=as_json,
        )
        return EXIT_VIOLATION if drift else EXIT_OK

    written = export_all(target)
    _emit(
        {
            "written": [p.as_posix() for p in written],
            "schema_version": SCHEMA_VERSION,
            "supported": list(SUPPORTED_SCHEMA_VERSIONS),
        },
        [f"exported {len(written)} schema(s) to {target}"],
        as_json=as_json,
    )
    return EXIT_OK


# --- release ----------------------------------------------------------------


def _read_ledger(path: Path) -> ReleaseLedger:
    """Load the release ledger. A missing file is an empty ledger, not a pass.

    The ledger is **not catalog content** — it records which builds were
    published, withdrawn and activated. Durable storage of that belongs to the
    operational feature (D-13); this is a file the steward names.
    """
    if not path.is_file():
        return ReleaseLedger()
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _InvocationError(f"release ledger does not load: {exc}") from exc
    if not isinstance(raw, dict):
        raise _InvocationError(f"{path}: expected a mapping")
    payload = cast("dict[str, list[dict[str, Any]]]", raw)

    try:
        releases = [
            CatalogRelease(
                release_id=entry["release_id"],
                state=ReleaseState(entry["state"]),
                activated_at=datetime.fromisoformat(entry["activated_at"]),
                activation_event_id=entry["activation_event_id"],
                withdrawn_at=(
                    datetime.fromisoformat(entry["withdrawn_at"])
                    if entry.get("withdrawn_at")
                    else None
                ),
            )
            for entry in payload.get("releases", [])
        ]
        events = [
            ActivationEvent(
                event_id=entry["event_id"],
                kind=EventKind(entry["kind"]),
                release_id=entry["release_id"],
                occurred_at=datetime.fromisoformat(entry["occurred_at"]),
                reason=entry["reason"],
                actor_role=entry["actor_role"],
                validated_commit=entry.get("validated_commit"),
            )
            for entry in payload.get("events", [])
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise _InvocationError(f"release ledger is malformed: {exc}") from exc

    try:
        return ReleaseLedger.restore(releases, events)
    except ReleaseStateError as exc:
        # The file parsed; its *content* breaks a governance rule — a reused
        # release identifier makes every decision citing it unauditable.
        raise _CatalogError.of(
            path.as_posix(), str(exc), rule="release_ledger_invalid", kind="release_ledger"
        ) from exc


def _write_ledger(path: Path, ledger: ReleaseLedger) -> None:
    payload = {
        "releases": [
            {
                "release_id": r.release_id,
                "state": r.state.value,
                "activated_at": r.activated_at.isoformat(),
                "activation_event_id": r.activation_event_id,
                **({"withdrawn_at": r.withdrawn_at.isoformat()} if r.withdrawn_at else {}),
            }
            for r in sorted(ledger.releases.values(), key=lambda r: r.release_id)
        ],
        "events": [
            {
                "event_id": e.event_id,
                "kind": e.kind.value,
                "release_id": e.release_id,
                "occurred_at": e.occurred_at.isoformat(),
                "reason": e.reason,
                "actor_role": e.actor_role,
                **({"validated_commit": e.validated_commit} if e.validated_commit else {}),
            }
            for e in ledger.events
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cmd_release(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    ledger = _read_ledger(ledger_path)
    as_json = args.format == "json"

    if args.release_command == "status":
        active = ledger.active
        rows = sorted(ledger.releases.values(), key=lambda r: r.release_id)
        _emit(
            {
                "ledger": ledger_path.as_posix(),
                "active": active.release_id if active else None,
                "releases": [
                    {
                        "release_id": r.release_id,
                        "state": r.state.value,
                        "activated_at": r.activated_at.isoformat(),
                        "admits_new_decisions": r.admits_new_decisions,
                    }
                    for r in rows
                ],
                "events": len(ledger.events),
            },
            [
                f"active release: {active.release_id if active else '(none)'}",
                *[
                    f"  {r.release_id} {r.state.value}"
                    + ("" if r.admits_new_decisions else "  (no new decisions)")
                    for r in rows
                ],
            ],
            as_json=as_json,
        )
        return EXIT_OK

    occurred_at = datetime.now(tz=UTC)
    try:
        if args.release_command == "publish":
            root = _catalog_root(args.path)
            on = _on(args.on)
            validation = validate_release(root, commit=args.commit, on=on)
            if not validation.valid:
                _emit(
                    {
                        "published": False,
                        "commit": validation.commit,
                        "findings": list(validation.report.render()),
                    },
                    [
                        f"refusing to publish {validation.commit}: validation failed",
                        *[f"  {line}" for line in validation.report.render()],
                    ],
                    as_json=as_json,
                )
                return EXIT_VIOLATION
            release = ledger.publish(
                _bundle(root, args.commit, on, args.source_commit).release_id,
                validation,
                occurred_at=occurred_at,
                reason=args.reason,
                actor_role=args.actor_role,
            )
        elif args.release_command == "withdraw":
            release = ledger.withdraw(
                args.release_id,
                occurred_at=occurred_at,
                reason=args.reason,
                actor_role=args.actor_role,
            )
        else:
            release = ledger.activate(
                args.release_id,
                occurred_at=occurred_at,
                reason=args.reason,
                actor_role=args.actor_role,
            )
    except ReleaseStateError as exc:
        _emit({"ok": False, "error": str(exc)}, [f"refused: {exc}"], as_json=as_json)
        return EXIT_VIOLATION

    _write_ledger(ledger_path, ledger)
    _emit(
        {
            "ok": True,
            "release_id": release.release_id,
            "state": release.state.value,
            "activation_event_id": release.activation_event_id,
        },
        [f"{args.release_command}: {release.release_id} is now {release.state.value}"],
        as_json=as_json,
    )
    return EXIT_OK


# --- leakage-scan -----------------------------------------------------------


def _cmd_leakage(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    if not repo.is_dir():
        raise _InvocationError(f"repository root not found: {repo}")
    bundle = _bundle(_catalog_root(args.path), args.commit, _on(args.on), args.source_commit)
    report = scan_repository(
        repo,
        public_bundle=serialise_public(bundle.public),
        pending_metrics=bundle.pending,
    )
    _emit(report.to_dict(), report.render(), as_json=args.format == "json")
    return EXIT_OK if report.clean else EXIT_VIOLATION


# --- parser -----------------------------------------------------------------


def _add_common(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--path", default="semantic", help="Catalog root.")
    sub.add_argument("--on", default=None, help="Evaluation date, YYYY-MM-DD.")
    sub.add_argument("--commit", default="workingtree", help="Commit being validated.")
    sub.add_argument(
        "--source-commit",
        action="append",
        default=None,
        metavar="ID=COMMIT",
        help=(
            "The commit a source's content is at, as <source_id>=<commit>. Repeatable. "
            "Unstated sources are resolved from Git (ADR 0033)."
        ),
    )


def _add_format(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--format", choices=("text", "json"), default="text")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalog",
        description=(
            "Steward CLI for the governed semantic catalog. Reads authored YAML and "
            "caller-supplied fixtures; writes no catalog content."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Run L1-L4 over a catalog tree.")
    _add_common(validate)
    _add_format(validate)
    validate.add_argument("--strict", action="store_true", help="Warnings fail too.")
    validate.add_argument("--check-schema-version", action="store_true")
    validate.add_argument("--release", action="store_true", help="Whole-release atomic validation.")
    validate.add_argument("--coverage", default=None)
    validate.add_argument(
        "--coverage-live",
        dest="coverage_live",
        action="store_true",
        help="Read semantic.metric_availability live through the dedicated identity (D-12).",
    )
    validate.add_argument(
        "--credentials",
        default=None,
        help="Service-account file for --coverage-live; handed in, never read from a variable.",
    )
    validate.add_argument("--codeowners", default=None)
    validate.set_defaults(handler=_cmd_validate)

    explain = subparsers.add_parser("explain", help="Resolved contract as of a date.")
    _add_common(explain)
    _add_format(explain)
    explain.add_argument("metric")
    explain.set_defaults(handler=_cmd_explain)

    check = subparsers.add_parser("check", help="Run the gate pipeline; print the decision.")
    _add_common(check)
    _add_format(check)
    check.add_argument("metric")
    check.add_argument("--dimensions", default=None)
    check.add_argument("--sources", default=None)
    check.add_argument("--from", dest="from_date", required=True)
    check.add_argument("--to", dest="to_date", required=True)
    check.add_argument("--access", default=None)
    check.add_argument("--scope", default="default")
    check.add_argument("--principal-type", default="user", choices=("user", "service_principal"))
    check.add_argument("--aggregate", default=None)
    check.add_argument("--freshness", default=None, help="Observed snapshot fixture.")
    check.add_argument("--ledger", default=None)
    check.add_argument("--release-id", dest="release_id", default=None)
    check.add_argument(
        "--evaluated-at",
        dest="evaluated_at",
        default=None,
        help="Pin the evaluation instant (ISO-8601) so the output is byte-reproducible.",
    )
    # T110 / D-13 (OD-103): o sink operacional. O caminho tem default (runs/) e nao ha
    # interruptor de desligar — um --no-audit seria o silencio que o T075 recusa.
    check.add_argument("--principal", default="cli-steward", help="Pseudonymous actor id.")
    check.add_argument(
        "--correlation-id",
        dest="correlation_id",
        default=None,
        help="Join key for the run; defaults to the decision id.",
    )
    check.add_argument(
        "--audit-path",
        dest="audit_path",
        default=None,
        help="Operational audit archive (default: runs/operational-audit.jsonl).",
    )
    check.set_defaults(handler=_cmd_check)

    matrix = subparsers.add_parser("matrix", help="Export the allowed-combination matrix.")
    _add_common(matrix)
    matrix.add_argument("--format", choices=("md", "csv", "json"), default="md")
    matrix.add_argument("--access", default=None)
    matrix.add_argument("--scope", default="default")
    matrix.add_argument("--principal-type", default="user", choices=("user", "service_principal"))
    matrix.add_argument("--freshness", default=None)
    matrix.set_defaults(handler=_cmd_matrix)

    diff = subparsers.add_parser("diff", help="Classify changes against a Git ref.")
    _add_common(diff)
    _add_format(diff)
    diff.add_argument("--base", required=True)
    diff.add_argument("--repo", default=".")
    diff.set_defaults(handler=_cmd_diff)

    compliance = subparsers.add_parser("compliance", help="Compliance report.")
    _add_common(compliance)
    _add_format(compliance)
    compliance.add_argument("--coverage", default=None)
    compliance.add_argument("--codeowners", default=None)
    compliance.add_argument("--readiness", default="docs/readiness/external-readiness.yaml")
    compliance.add_argument("--mode", choices=("local", "integration", "release"), default="local")
    compliance.set_defaults(handler=_cmd_compliance)

    schema = subparsers.add_parser("schema", help="Generated JSON Schema.")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    export = schema_sub.add_parser("export", help="Write or check the generated schemas.")
    _add_format(export)
    export.add_argument("--out", default="schemas")
    export.add_argument("--check", action="store_true", help="Fail on drift instead of writing.")
    export.set_defaults(handler=_cmd_schema)

    release = subparsers.add_parser("release", help="Release state and corrective releases.")
    release_sub = release.add_subparsers(dest="release_command", required=True)
    for name in ("status", "withdraw", "publish", "activate"):
        sub = release_sub.add_parser(name)
        _add_format(sub)
        sub.add_argument("--ledger", required=True, help="Release ledger. Never catalog content.")
        if name != "status":
            sub.add_argument("--reason", required=True)
            sub.add_argument("--actor-role", required=True)
        if name in {"withdraw", "activate"}:
            sub.add_argument("release_id")
        if name == "publish":
            _add_common(sub)
        sub.set_defaults(handler=_cmd_release)

    leakage = subparsers.add_parser("leakage-scan", help="Static SC-013 leakage scan.")
    _add_common(leakage)
    _add_format(leakage)
    leakage.add_argument("--repo", default=".")
    leakage.set_defaults(handler=_cmd_leakage)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Never raises: every failure becomes an exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse exits 2 on a usage error, which is correct
        return int(exc.code or EXIT_INVOCATION)

    as_json = getattr(args, "format", "text") == "json"
    try:
        return int(args.handler(args))
    except _InvocationError as exc:
        # Nothing was validated, so nothing is printed on stdout: a verdict
        # beside a usage error would read as a result.
        print(f"catalog: {exc}", file=sys.stderr)
        return EXIT_INVOCATION
    except _CatalogError as exc:
        _emit(
            {
                "valid": False,
                "errors": len(exc.report.errors),
                "findings": list(exc.report.render()),
                "summary": exc.summary,
            },
            [f"FAIL: {exc.summary}", *[f"  {line}" for line in exc.report.render()]],
            as_json=as_json,
        )
        return EXIT_VIOLATION
    except (CatalogLoadError, ValidationError, PolicyUnresolvableError, ReadinessError) as exc:
        # Only governed content reaches here; caller-supplied inputs are
        # converted to _InvocationError at the point they are read. A traceback
        # never escapes — a crash is not a verdict.
        _emit(
            {"valid": False, "errors": 1, "findings": [str(exc)], "summary": str(exc)},
            [f"FAIL: {exc}"],
            as_json=as_json,
        )
        return EXIT_VIOLATION


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
