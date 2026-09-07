"""No production-readiness claim, and no fabricated evidence — T029 (FR-099, FR-100; SC-058).

Scanned over **every artifact this feature owns**: the package, its tests, its governed
content, and its specification directory. A claim in a docstring is still a claim, and a
reader who finds "production ready" in a comment will believe it before they read a
readiness record.

The scan is deliberately blunt: it looks for the phrases, then requires each occurrence
to be a **negation** or an explicit statement of absence. That is how `003` states the
same rule, and being blunt is the point — a subtle scan is one somebody can phrase
around.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pytest

pytestmark = pytest.mark.contract

#: Phrases that would constitute a claim. Each occurrence must be negated.
_CLAIM_PHRASES = (
    "production ready",
    "production-ready",
    "production readiness",
    "prontidão de produção",
    "pronto para produção",
)

#: Words that make an occurrence a negation or a statement of absence.
_NEGATORS = (
    "no ",
    "not ",
    "never",
    "zero",
    "without",
    "nothing",
    "says nothing",
    "claim no",
    "must not",
    "cannot",
    "unproven",
    "absent",
    "undeclared",
    "nenhum",
    "não",
    "sem ",
)

#: Fabrication markers. A credential-shaped literal in this feature would be a
#: fabricated secret, which `FR-097` and `NG-10` forbid outright.
_FABRICATION_PATTERNS = (
    re.compile(r"\bxoxb-[A-Za-z0-9-]+"),  # Slack bot token shape
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),  # AWS access key id shape
    re.compile(r"https://hooks\.slack\.com/\S+"),
    re.compile(r"https://api\.telegram\.org/bot\S+"),
    re.compile(r"https://graph\.facebook\.com/\S+"),
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "packages").is_dir() and (parent / "docs").is_dir():
            return parent
    raise AssertionError("repository root not found")


def _owned_files() -> list[Path]:
    root = _repo_root()
    roots = (
        root / "packages" / "channel_integration",
        root / "channel_governance",
        root / "specs" / "004-multichannel-integration",
    )
    files: list[Path] = []
    for base in roots:
        files.extend(
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix in {".py", ".md", ".yaml", ".yml", ".toml"}
            and "__pycache__" not in path.parts
            # A scanner must not scan its own pattern list: this module has to spell the
            # forbidden phrases out in order to look for them, so every occurrence here is
            # a pattern rather than a claim. One file excluded by name, visibly, rather
            # than a scan somebody phrased around.
            and path.name != Path(__file__).name
        )
    return sorted(files)


def test_every_owned_file_is_scannable() -> None:
    """A scan over zero files passes trivially, so the corpus is asserted first."""
    files = _owned_files()
    assert len(files) >= 20, f"only {len(files)} owned files found; the scan would be vacuous"


def test_no_artifact_claims_production_readiness() -> None:
    offenders: list[str] = []
    for path in _owned_files():
        lowered = path.read_text(encoding="utf-8").lower()
        for phrase in _CLAIM_PHRASES:
            start = 0
            while (index := lowered.find(phrase, start)) != -1:
                window = lowered[max(0, index - 90) : index + len(phrase) + 20]
                if not any(negator in window for negator in _NEGATORS):
                    offenders.append(f"{path.name}: ...{window.strip()}...")
                start = index + len(phrase)
    assert not offenders, offenders


def test_no_artifact_carries_a_fabricated_credential_or_endpoint() -> None:
    """`FR-097`, `NG-10`: no credential, token, endpoint, bot or number is invented."""
    offenders: list[str] = []
    for path in _owned_files():
        text = path.read_text(encoding="utf-8")
        for pattern in _FABRICATION_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.name}: matches {pattern.pattern}")
    assert not offenders, offenders


def test_no_governed_content_file_declares_an_instance() -> None:
    """All four `channel_governance/` documents ship empty and unapproved.

    An instance appearing here would be this feature authoring a governance decision —
    a transport bound, a capability, a binding or a retention period — that `D-26` to `D-29` own.
    """
    import yaml

    root = _repo_root() / "channel_governance"
    documents = sorted(root.glob("*.yaml"))
    assert len(documents) == 4, f"expected four governed documents, found {len(documents)}"
    for path in documents:
        loaded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        document = cast(dict[str, object], loaded)
        assert document.get("instances") == [], f"{path.name} declares an instance"
