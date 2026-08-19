"""Local developer quality-check command for NexusAgent.

Runs, in order, and stops at the first failure:

    ruff check .
    ruff format --check .
    pytest

Usage:
    python scripts/check.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CHECKS = [
    ("Running ruff check...", [sys.executable, "-m", "ruff", "check", "."]),
    ("Running ruff format check...", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("Running pytest...", [sys.executable, "-m", "pytest"]),
]


def main() -> int:
    for message, command in CHECKS:
        print(message)
        result = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if result.returncode != 0:
            print(f"Failed: {' '.join(command)}")
            return result.returncode

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
