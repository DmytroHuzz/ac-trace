from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ac_trace.catalog import CriteriaCatalog
from ac_trace.manifest import AcceptanceCriterion, CodeRef, TestRef, TraceManifest
from ac_trace.python_ast import PythonSymbol, discover_python_symbols, discover_pytest_cases


class InferenceError(ValueError):
    """Raised when an inferred manifest cannot be produced safely."""


def _iter_python_files(project_root: Path, roots: list[str]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        root_path = (project_root / root).resolve()
        if root_path.is_file() and root_path.suffix == ".py":
            if root_path not in seen:
                files.append(root_path)
                seen.add(root_path)
            continue
        if not root_path.exists():
            continue
        for path in sorted(root_path.rglob("*.py")):
            resolved = path.resolve()
            if resolved not in seen:
                files.append(resolved)
                seen.add(resolved)
    return files


def _normalize_covered_path(project_root: Path, raw_path: str) -> Path | None:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (project_root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(project_root)
    except ValueError:
        return None
    return candidate


def _covered_lines_for_selector(project_root: Path, source_paths: list[str], selector: str) -> dict[Path, set[int]]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        data_path = tmpdir_path / ".coverage"
        json_path = tmpdir_path / "coverage.json"

        run_command = [sys.executable, "-m", "coverage", "run", f"--data-file={data_path}"]
        for source_path in source_paths:
            run_command.append(f"--source={(project_root / source_path).resolve()}")
        run_command.extend(["-m", "pytest", selector])

        run_result = subprocess.run(
            run_command,
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if run_result.returncode != 0:
            output = (run_result.stdout + run_result.stderr).strip()
            raise InferenceError(f"Coverage run failed for {selector}:\n{output}")

        export_command = [
            sys.executable,
            "-m",
            "coverage",
            "json",
            f"--data-file={data_path}",
            "-o",
            str(json_path),
        ]
        export_result = subprocess.run(
            export_command,
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        if export_result.returncode != 0:
            output = (export_result.stdout + export_result.stderr).strip()
            raise InferenceError(f"Coverage export failed for {selector}:\n{output}")

        payload = json.loads(json_path.read_text(encoding="utf-8"))

    covered: dict[Path, set[int]] = {}
    for raw_path, file_report in payload.get("files", {}).items():
        normalized = _normalize_covered_path(project_root, raw_path)
        if normalized is None:
            continue
        executed_lines = file_report.get("executed_lines", [])
        if not isinstance(executed_lines, list) or not executed_lines:
            continue
        covered[normalized] = {line for line in executed_lines if isinstance(line, int)}
    return covered


def _group_tests_by_path(test_cases: list[tuple[str, str]]) -> list[TestRef]:
    grouped: dict[str, list[str]] = {}
    for path, case_id in sorted(test_cases):
        grouped.setdefault(path, [])
        if case_id not in grouped[path]:
            grouped[path].append(case_id)
    return [TestRef(path=path, cases=cases) for path, cases in grouped.items()]


def _group_code_refs(code_refs: list[CodeRef]) -> list[CodeRef]:
    grouped: dict[tuple[str, str | None], CodeRef] = {}
    for code_ref in sorted(code_refs, key=lambda ref: (ref.path, ref.symbol or "", ref.lines or "")):
        key = (code_ref.path, code_ref.symbol)
        if key not in grouped:
            grouped[key] = code_ref
    return list(grouped.values())


def _filter_specific_symbols(symbols: list[PythonSymbol]) -> list[PythonSymbol]:
    specific: list[PythonSymbol] = []
    for candidate in sorted(symbols, key=lambda symbol: (symbol.lineno, symbol.end_lineno, symbol.qualname)):
        is_container = any(
            other.qualname != candidate.qualname
            and candidate.lineno <= other.lineno
            and candidate.end_lineno >= other.end_lineno
            for other in symbols
        )
        if not is_container:
            specific.append(candidate)
    return specific


def infer_manifest(catalog: CriteriaCatalog) -> TraceManifest:
    discovered_tests = []
    for path in _iter_python_files(catalog.project_root, catalog.test_paths):
        discovered_tests.extend(discover_pytest_cases(path, catalog.project_root))

    criteria_by_id = {criterion.id: criterion for criterion in catalog.acceptance_criteria}
    tests_by_criterion: dict[str, list[tuple[str, str, str]]] = {criterion.id: [] for criterion in catalog.acceptance_criteria}
    for test_case in discovered_tests:
        unknown_ids = [criterion_id for criterion_id in test_case.ac_ids if criterion_id not in criteria_by_id]
        if unknown_ids:
            unknown_text = ", ".join(sorted(unknown_ids))
            raise InferenceError(f"{test_case.selector} references unknown acceptance criteria: {unknown_text}")
        for criterion_id in test_case.ac_ids:
            tests_by_criterion[criterion_id].append((test_case.path, test_case.case_id, test_case.selector))

    acceptance_criteria: list[AcceptanceCriterion] = []
    for criterion in catalog.acceptance_criteria:
        mapped_tests = tests_by_criterion[criterion.id]
        if not mapped_tests:
            raise InferenceError(f"{criterion.id} has no tests annotated with @ac(...)")

        inferred_code: list[CodeRef] = []
        for _, _, selector in mapped_tests:
            coverage = _covered_lines_for_selector(catalog.project_root, catalog.source_paths, selector)
            for covered_path, executed_lines in coverage.items():
                try:
                    relative_path = covered_path.relative_to(catalog.project_root).as_posix()
                except ValueError:
                    continue

                matched_symbols: list[PythonSymbol] = []
                for symbol in discover_python_symbols(covered_path):
                    if any(symbol.body_lineno <= line <= symbol.end_lineno for line in executed_lines):
                        matched_symbols.append(symbol)

                for symbol in _filter_specific_symbols(matched_symbols):
                    inferred_code.append(
                        CodeRef(
                            path=relative_path,
                            symbol=symbol.qualname,
                            lines=symbol.lines,
                            mutate=symbol.mutate,
                        )
                    )

        if not inferred_code:
            raise InferenceError(f"{criterion.id} did not map to any Python symbols under {catalog.source_paths}")

        acceptance_criteria.append(
            AcceptanceCriterion(
                id=criterion.id,
                title=criterion.title,
                description=criterion.description,
                code=_group_code_refs(inferred_code),
                tests=_group_tests_by_path([(path, case_id) for path, case_id, _ in mapped_tests]),
            )
        )

    return TraceManifest(
        manifest_path=catalog.catalog_path,
        project_root=catalog.project_root,
        acceptance_criteria=acceptance_criteria,
    )
