from __future__ import annotations

from pathlib import Path

from ac_trace.manifest import TraceManifest
from ac_trace.python_ast import discover_pytest_case_ids, resolve_python_symbol


def _validate_lines(path: Path, line_spec: str) -> str | None:
    parts = line_spec.split("-", maxsplit=1)
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return f"{path}: invalid line range '{line_spec}'"

    start, end = (int(part) for part in parts)
    line_count = len(path.read_text(encoding="utf-8").splitlines())
    if start < 1 or end < start or end > line_count:
        return f"{path}: line range '{line_spec}' is outside the file"
    return None


def validate_manifest(manifest: TraceManifest) -> list[str]:
    errors: list[str] = []
    test_case_cache: dict[Path, set[str]] = {}

    for criterion in manifest.acceptance_criteria:
        for code_ref in criterion.code:
            code_path = code_ref.resolved_path(manifest.project_root)
            if not code_path.exists():
                errors.append(f"{criterion.id}: missing code file {code_ref.path}")
                continue
            resolved_symbol = None
            if code_ref.symbol:
                resolved_symbol = resolve_python_symbol(code_path, code_ref.symbol)
                if resolved_symbol is None:
                    errors.append(f"{criterion.id}: symbol '{code_ref.symbol}' not found in {code_ref.path}")
            if code_ref.lines:
                line_error = _validate_lines(code_path, code_ref.lines)
                if line_error:
                    errors.append(f"{criterion.id}: {line_error}")
                elif resolved_symbol is not None:
                    start_text, _, end_text = code_ref.lines.partition("-")
                    start, end = int(start_text), int(end_text)
                    if start < resolved_symbol.lineno or end > resolved_symbol.end_lineno:
                        errors.append(
                            f"{criterion.id}: line range '{code_ref.lines}' falls outside symbol "
                            f"'{code_ref.symbol}' in {code_ref.path}"
                        )

        for test_ref in criterion.tests:
            test_path = test_ref.resolved_path(manifest.project_root)
            if not test_path.exists():
                errors.append(f"{criterion.id}: missing test file {test_ref.path}")
                continue
            if test_path not in test_case_cache:
                test_case_cache[test_path] = discover_pytest_case_ids(test_path, manifest.project_root)
            test_cases = test_case_cache[test_path]
            for case in test_ref.cases:
                if case not in test_cases:
                    errors.append(f"{criterion.id}: test '{case}' not found in {test_ref.path}")

    return errors
