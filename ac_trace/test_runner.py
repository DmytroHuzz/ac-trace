from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
import tempfile
from xml.etree import ElementTree

from ac_trace.manifest import AcceptanceCriterion


@dataclass(frozen=True)
class PytestCaseResult:
    selector: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class PytestResult:
    selectors: list[str]
    returncode: int
    stdout: str
    stderr: str
    cases: list[PytestCaseResult]


def selectors_for_criterion(criterion: AcceptanceCriterion) -> list[str]:
    selectors: list[str] = []
    for test_ref in criterion.tests:
        for case in test_ref.cases:
            selectors.append(f"{test_ref.path}::{case}")
    return selectors


SUBPROCESS_TIMEOUT = 300


def _expected_signature(selector: str) -> tuple[str, str]:
    path, _, remainder = selector.partition("::")
    parts = remainder.split("::") if remainder else []
    module_name = (
        path[:-3].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")
    )
    if len(parts) <= 1:
        return module_name, remainder
    return f"{module_name}.{'.'.join(parts[:-1])}", parts[-1]


def _selector_from_testcase(
    project_root: Path,
    testcase: ElementTree.Element,
    expected_selectors: dict[tuple[str, str], str],
) -> str | None:
    file_attr = testcase.get("file")
    name_attr = testcase.get("name")
    classname_attr = testcase.get("classname", "")
    if not name_attr:
        return None

    direct_match = expected_selectors.get((classname_attr, name_attr))
    if direct_match is not None:
        return direct_match

    if classname_attr:
        suffix_matches = [
            selector
            for (expected_classname, expected_name), selector in expected_selectors.items()
            if name_attr == expected_name
            and classname_attr.endswith(f".{expected_classname}")
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]

    if not file_attr:
        return None

    file_path = Path(file_attr)
    if file_path.is_absolute():
        try:
            relative_path = file_path.resolve().relative_to(project_root).as_posix()
        except ValueError:
            relative_path = file_path.as_posix()
    else:
        relative_path = file_attr.replace("\\", "/")

    if "::" in name_attr:
        return f"{relative_path}::{name_attr}"

    module_name = (
        relative_path[:-3].replace("/", ".")
        if relative_path.endswith(".py")
        else relative_path.replace("/", ".")
    )
    class_part = ""
    if (
        classname_attr
        and classname_attr != module_name
        and classname_attr.startswith(module_name + ".")
    ):
        class_part = classname_attr[len(module_name) + 1 :].replace(".", "::")

    if class_part:
        return f"{relative_path}::{class_part}::{name_attr}"
    return f"{relative_path}::{name_attr}"


def _status_from_testcase(testcase: ElementTree.Element) -> tuple[str, str]:
    for tag, status in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
        node = testcase.find(tag)
        if node is not None:
            message = node.get("message") or (node.text or "").strip()
            return status, message
    return "passed", ""


def _parse_junit_results(
    project_root: Path, xml_path: Path, selectors: list[str]
) -> list[PytestCaseResult]:
    expected_selectors = {
        _expected_signature(selector): selector for selector in selectors
    }
    if not xml_path.exists():
        return [
            PytestCaseResult(
                selector=selector,
                status="error",
                message="Pytest did not produce a JUnit report.",
            )
            for selector in selectors
        ]

    root = ElementTree.fromstring(xml_path.read_text(encoding="utf-8"))
    discovered: dict[str, PytestCaseResult] = {}
    for testcase in root.iter("testcase"):
        selector = _selector_from_testcase(project_root, testcase, expected_selectors)
        if selector is None:
            continue
        status, message = _status_from_testcase(testcase)
        discovered[selector] = PytestCaseResult(
            selector=selector,
            status=status,
            message=message,
        )

    results: list[PytestCaseResult] = []
    for selector in selectors:
        results.append(
            discovered.get(
                selector,
                PytestCaseResult(
                    selector=selector,
                    status="error",
                    message="Test did not produce an individual pytest result.",
                ),
            )
        )
    return results


def run_pytest(project_root: Path, selectors: list[str]) -> PytestResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        junit_path = Path(tmpdir) / "pytest-results.xml"
        command = [sys.executable, "-m", "pytest", f"--junitxml={junit_path}", *selectors]
        completed = subprocess.run(
            command,
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT,
        )
        cases = _parse_junit_results(project_root, junit_path, selectors)

    return PytestResult(
        selectors=selectors,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        cases=cases,
    )
