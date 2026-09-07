from __future__ import annotations

import sys

from engineering_playbook.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["delivery", *sys.argv[1:]]))
