from __future__ import annotations

import argparse
from pathlib import Path

from engineering_playbook.core import ROOT
from engineering_playbook.installer import legacy_bootstrap


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for engineering-playbook init."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--project-name")
    parser.add_argument("--profile", default="standard")
    parser.add_argument("--stack", default="python")
    parser.add_argument(
        "--agents",
        default="codex,claude-code,gemini-cli,github-copilot,cursor,windsurf",
    )
    parser.add_argument("--ci", choices=["github", "none"], default="github")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(legacy_bootstrap(parse_args()))
