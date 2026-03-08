from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ac_trace.manifest import AcceptanceCriterion, TraceManifest


@dataclass(frozen=True)
class PytestResult:
    selectors: list[str]
    returncode: int
    stdout: str
    stderr: str


def selectors_for_criterion(criterion: AcceptanceCriterion) -> list[str]:
    selectors: list[str] = []
    for test_ref in criterion.tests:
        for case in test_ref.cases:
            selectors.append(f"{test_ref.path}::{case}")
    return selectors


SUBPROCESS_TIMEOUT = 300


def run_pytest(project_root: Path, selectors: list[str]) -> PytestResult:
    command = [sys.executable, "-m", "pytest", *selectors]
    completed = subprocess.run(
        command,
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
        timeout=SUBPROCESS_TIMEOUT,
    )
    return PytestResult(
        selectors=selectors,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_tests_for_manifest(
    manifest: TraceManifest, ac_ids: list[str] | None = None
) -> PytestResult:
    selectors: list[str] = []
    seen: set[str] = set()

    for criterion in manifest.find_criteria(ac_ids):
        for selector in selectors_for_criterion(criterion):
            if selector not in seen:
                selectors.append(selector)
                seen.add(selector)

    return run_pytest(manifest.project_root, selectors)
