"""Update the README coverage badge via a shields.io JSON endpoint on gh-pages.

Reads the coverage data produced by pytest-cov (the ``.coverage`` file in the
repository root), renders a shields.io endpoint JSON file, and pushes it to the
``gh-pages`` branch so the README can display a live coverage badge without any
third-party coverage service.

Usage:
    python scripts/update_coverage_badge.py [--dry-run]

``--dry-run`` only prints the badge JSON that would be pushed (useful locally).
The script is intended to run inside GitHub Actions on main pushes; locally it
requires push access to be meaningful.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BADGE_FILENAME = "coverage-badge.json"
GH_PAGES_BRANCH = "gh-pages"
CI_BOT_NAME = "github-actions[bot]"
CI_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def coverage_percent() -> float:
    """Run `coverage json` and return the total covered percentage."""
    subprocess.run(
        [sys.executable, "-m", "coverage", "json"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    report_path = REPO_ROOT / "coverage.json"
    if not report_path.exists():
        raise RuntimeError("coverage json was not written")

    data = json.loads(report_path.read_text(encoding="utf-8"))
    report_path.unlink()
    return float(data["totals"]["percent_covered"])


def badge_json(percent: float) -> dict:
    """Return the shields.io endpoint payload for a coverage percentage."""
    if percent >= 95:
        color = "brightgreen"
    elif percent >= 90:
        color = "green"
    elif percent >= 75:
        color = "orange"
    else:
        color = "red"

    return {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{percent:.0f}%",
        "color": color,
    }


def push_to_gh_pages(badge: dict) -> None:
    """Write the badge JSON to the gh-pages branch (orphan-friendly)."""
    remote = f"https://x-access-token:{_git_token()}@github.com/{_repo_slug()}.git"

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "ghp"
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", GH_PAGES_BRANCH, remote, str(work)],
            capture_output=True,
            check=False,
        )
        if clone.returncode != 0:
            # No gh-pages branch yet (first publish): start a fresh orphan repo.
            shutil.rmtree(work, ignore_errors=True)
            subprocess.run(["git", "init", "-q", "-b", GH_PAGES_BRANCH, str(work)], check=True)
            _git(work, "remote", "add", "origin", remote)

        (work / BADGE_FILENAME).write_text(json.dumps(badge), encoding="utf-8")
        _git(work, "config", "user.name", CI_BOT_NAME)
        _git(work, "config", "user.email", CI_BOT_EMAIL)
        _git(work, "add", BADGE_FILENAME)
        commit = subprocess.run(
            ["git", "-C", str(work), "diff", "--cached", "--quiet"],
            capture_output=True,
            check=False,
        )
        if commit.returncode == 0:
            print("coverage badge unchanged; nothing to push")
            return

        _git(work, "commit", "-q", "-m", "chore: update coverage badge [skip ci]")
        push = subprocess.run(
            ["git", "-C", str(work), "push", "-q", "--force", "origin", GH_PAGES_BRANCH],
            capture_output=True,
            check=False,
        )
        if push.returncode != 0:
            raise RuntimeError(f"failed to push {GH_PAGES_BRANCH}: {push.stderr.decode()}")


def _git(work: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)


def _git_token() -> str:
    import os

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to push the coverage badge")
    return token


def _repo_slug() -> str:
    import os

    slug = os.environ.get("GITHUB_REPOSITORY", "")
    if not slug:
        raise RuntimeError("GITHUB_REPOSITORY is required to push the coverage badge")
    return slug


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print badge JSON, do not push")
    args = parser.parse_args()

    percent = coverage_percent()
    badge = badge_json(percent)
    print(f"coverage: {percent:.2f}%")
    print(json.dumps(badge))

    if not args.dry_run:
        push_to_gh_pages(badge)
        print(f"badge pushed to {GH_PAGES_BRANCH}/{BADGE_FILENAME}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
