"""Shared fail-closed resolution posture for governed content — T022 (FR-103; SC-059).

Four governed documents, one resolution rule: **exactly one effective instance, or
refuse.** Zero effective instances, more than one, or one missing a required field all
produce the document's own reason code. Nothing is inferred, defaulted or carried
forward (`FR-103`).

**"Exactly one" rather than "the newest".** Picking the newest of two effective
instances would let an unreviewed addition silently supersede an approved one, and
the failure would look like normal operation. Refusing makes an ambiguous governance
state visible at the moment it arises.

**The content root is located, never configured.** A settable path would be a runtime
switch over governance content — a deployment could point it at a file of its own
making — which is the same defect `003` avoided for the same reason.

Every loader here **reads**. None writes, mutates, creates or defaults a document, and
none offers a flag, environment variable, argument or override by which an
undeclared capability could appear declared.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml

from ..contracts.reason_codes import ChannelReasonCode

__all__ = [
    "GOVERNANCE_DIRECTORY",
    "ContentUnresolvable",
    "effective_instance",
    "governed_content_root",
    "load_document",
    "read_instances",
]

GOVERNANCE_DIRECTORY = "channel_governance"


class ContentUnresolvable(ValueError):  # noqa: N818 - a governed refusal, not an error
    """A governed document does not resolve to exactly one usable instance.

    Carries the document's own reason code, so a caller refuses with the code the
    contract declares rather than with a generic failure. The four documents have four
    distinct codes precisely because they are separately owned and separately
    approved: a rendering-matrix gap must not be reported as a transport-policy gap.
    """

    def __init__(self, code: ChannelReasonCode, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


def governed_content_root() -> Path:
    """``channel_governance/`` at the repository root, located by walking up."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / GOVERNANCE_DIRECTORY
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"{GOVERNANCE_DIRECTORY}/ not found above {here}")


def load_document(filename: str, code: ChannelReasonCode) -> Mapping[str, Any]:
    """Read one governed document, refusing with ``code`` if it cannot be read.

    An absent file, unparseable YAML or a non-mapping document is a governed refusal
    rather than an exception escaping to a caller: the capability the document gates
    is unavailable either way, and the caller's contract is to refuse with a code.
    """
    path = governed_content_root() / filename
    if not path.is_file():
        raise ContentUnresolvable(code, f"{filename} does not exist")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentUnresolvable(code, f"{filename} is not readable as YAML") from exc
    if not isinstance(document, Mapping):
        raise ContentUnresolvable(code, f"{filename} is not a mapping")
    return cast(Mapping[str, Any], document)


def read_instances(
    filename: str, kind: str, code: ChannelReasonCode
) -> tuple[Mapping[str, Any], ...]:
    """The declared instances of one governed document, unvalidated.

    Asserts the envelope — ``schema_version``, ``kind``, ``instances`` — and nothing
    about an instance's content. An empty list is **valid and expected**: all four
    documents ship with no approved instance, and reading zero is how the fail-closed
    state arises rather than an error condition.
    """
    document = load_document(filename, code)
    if document.get("schema_version") != 1:
        raise ContentUnresolvable(code, f"{filename} declares an unknown schema_version")
    if document.get("kind") != kind:
        raise ContentUnresolvable(code, f"{filename} declares kind {document.get('kind')!r}")
    raw_instances: object = document.get("instances", [])
    if not isinstance(raw_instances, Sequence) or isinstance(raw_instances, str | bytes):
        raise ContentUnresolvable(code, f"{filename} declares a non-list `instances`")
    entries = cast(Sequence[object], raw_instances)
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ContentUnresolvable(code, f"{filename} declares a non-mapping instance")
    return tuple(cast(Mapping[str, Any], entry) for entry in entries)


def effective_instance(
    instances: Sequence[Mapping[str, Any]],
    required_fields: Sequence[str],
    code: ChannelReasonCode,
    label: str,
) -> Mapping[str, Any]:
    """The single effective instance, or refuse.

    Three refusals, one code, deliberately (`contracts/reason-codes.md` §2): zero
    effective, more than one effective, and one missing a required field. A caller
    cannot act differently on them — every one means the capability is unavailable —
    and separate codes would tell a sender something about the governance state.
    """
    if not instances:
        raise ContentUnresolvable(code, f"{label} declares no instance")
    if len(instances) > 1:
        raise ContentUnresolvable(code, f"{label} declares {len(instances)} effective instances")
    instance = instances[0]
    missing = [field for field in required_fields if field not in instance]
    if missing:
        raise ContentUnresolvable(code, f"{label} instance is missing {', '.join(sorted(missing))}")
    return instance
