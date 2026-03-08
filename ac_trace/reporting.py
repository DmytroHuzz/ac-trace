from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from html import escape
import yaml

from ac_trace.manifest import TraceManifest
from ac_trace.mutator import MutationReport
from ac_trace.test_runner import PytestResult


def _summary_counts(manifest: TraceManifest) -> dict[str, int]:
    return {
        "criteria": len(manifest.acceptance_criteria),
        "code_refs": sum(len(criterion.code) for criterion in manifest.acceptance_criteria),
        "test_files": sum(len(criterion.tests) for criterion in manifest.acceptance_criteria),
        "test_cases": sum(len(test_ref.cases) for criterion in manifest.acceptance_criteria for test_ref in criterion.tests),
    }


def _mutation_counts(reports: list[MutationReport]) -> Counter[str]:
    return Counter(report.status for report in reports)


def _mutation_by_criterion(reports: list[MutationReport]) -> dict[str, list[MutationReport]]:
    grouped: dict[str, list[MutationReport]] = {}
    for report in reports:
        grouped.setdefault(report.criterion_id, []).append(report)
    return grouped


def _test_status(test_result: PytestResult | None) -> str:
    if test_result is None:
        return "not run"
    return "passed" if test_result.returncode == 0 else "failed"


def _mutation_status(
    mutation_requested: bool,
    mutation_reports: list[MutationReport] | None,
) -> str:
    if not mutation_requested:
        return "disabled"
    if mutation_reports is None:
        return "not run"
    if any(report.status == "survived" for report in mutation_reports):
        return "failed"
    return "passed"


def render_markdown_report(
    manifest: TraceManifest,
    validation_errors: list[str] | None = None,
    test_result: PytestResult | None = None,
    mutation_requested: bool = False,
    mutation_reports: list[MutationReport] | None = None,
) -> str:
    counts = _summary_counts(manifest)
    validation_errors = validation_errors or []
    effective_mutation_reports = mutation_reports or []
    mutation_counts = _mutation_counts(effective_mutation_reports)
    mutations_by_criterion = _mutation_by_criterion(effective_mutation_reports)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    lines = [
        "# AC Trace Report",
        "",
        f"Generated: {generated_at}",
        "",
        "## Summary",
        "",
        f"- Acceptance criteria: {counts['criteria']}",
        f"- Code references: {counts['code_refs']}",
        f"- Test files: {counts['test_files']}",
        f"- Test cases: {counts['test_cases']}",
        f"- Validation: {'passed' if not validation_errors else 'failed'}",
        f"- Tests: {_test_status(test_result)}",
        f"- Mutation check: {_mutation_status(mutation_requested, mutation_reports)}",
    ]

    if mutation_reports is not None:
        lines.extend(
            [
                f"- Mutations killed: {mutation_counts.get('killed', 0)}",
                f"- Mutations survived: {mutation_counts.get('survived', 0)}",
                f"- Mutations skipped: {mutation_counts.get('skipped', 0)}",
            ]
        )

    if validation_errors:
        lines.extend(["", "## Validation Errors", ""])
        for error in validation_errors:
            lines.append(f"- {error}")

    if test_result is not None:
        lines.extend(["", "## Test Run", ""])
        lines.append(f"- Return code: {test_result.returncode}")
        lines.append("- Selectors:")
        for selector in test_result.selectors:
            lines.append(f"  - `{selector}`")
        if test_result.returncode != 0:
            lines.extend(["", "Pytest Output", "", "```text", test_result.stdout + test_result.stderr, "```"])

    for criterion in manifest.acceptance_criteria:
        lines.extend(["", f"## {criterion.id}: {criterion.title}", "", criterion.description, "", "Code", ""])
        for code_ref in criterion.code:
            details = []
            if code_ref.symbol:
                details.append(code_ref.symbol)
            if code_ref.lines:
                details.append(f"lines {code_ref.lines}")
            if not code_ref.mutate:
                details.append("mutation skipped")
            lines.append(f"- `{code_ref.path}`: {', '.join(details) if details else 'file'}")

        lines.extend(["", "Tests", ""])
        for test_ref in criterion.tests:
            for case in test_ref.cases:
                lines.append(f"- `{test_ref.path}::{case}`")

        criterion_mutations = mutations_by_criterion.get(criterion.id, [])
        if criterion_mutations:
            lines.extend(["", "Mutation Check", ""])
            for report in criterion_mutations:
                lines.append(f"- `{report.code_path}::{report.symbol}`: {report.status} ({report.mutation})")

    return "\n".join(lines) + "\n"


def render_html_report(
    manifest: TraceManifest,
    validation_errors: list[str] | None = None,
    test_result: PytestResult | None = None,
    mutation_requested: bool = False,
    mutation_reports: list[MutationReport] | None = None,
) -> str:
    counts = _summary_counts(manifest)
    validation_errors = validation_errors or []
    effective_mutation_reports = mutation_reports or []
    mutation_counts = _mutation_counts(effective_mutation_reports)
    mutations_by_criterion = _mutation_by_criterion(effective_mutation_reports)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    summary_items = [
        ("Acceptance criteria", counts["criteria"]),
        ("Code references", counts["code_refs"]),
        ("Test files", counts["test_files"]),
        ("Test cases", counts["test_cases"]),
        ("Validation", "passed" if not validation_errors else "failed"),
        ("Tests", _test_status(test_result)),
        ("Mutation check", _mutation_status(mutation_requested, mutation_reports)),
    ]
    if mutation_reports is not None:
        summary_items.extend(
            [
                ("Mutations killed", mutation_counts.get("killed", 0)),
                ("Mutations survived", mutation_counts.get("survived", 0)),
                ("Mutations skipped", mutation_counts.get("skipped", 0)),
            ]
        )

    sections: list[str] = []
    if validation_errors:
        errors_markup = "".join(f"<li>{escape(error)}</li>" for error in validation_errors)
        sections.append(f"<section><h2>Validation Errors</h2><ul>{errors_markup}</ul></section>")

    if test_result is not None:
        selectors_markup = "".join(f"<li>{escape(selector)}</li>" for selector in test_result.selectors)
        output_markup = ""
        if test_result.returncode != 0:
            output_markup = f"<h3>Pytest Output</h3><pre>{escape(test_result.stdout + test_result.stderr)}</pre>"
        sections.append(
            (
                "<section>"
                "<h2>Test Run</h2>"
                f"<p>Status: <strong>{escape(_test_status(test_result))}</strong></p>"
                f"<p>Return code: {test_result.returncode}</p>"
                f"<ul>{selectors_markup}</ul>"
                f"{output_markup}"
                "</section>"
            )
        )

    for criterion in manifest.acceptance_criteria:
        code_rows = "".join(
            (
                "<tr>"
                f"<td>{escape(code_ref.path)}</td>"
                f"<td>{escape(code_ref.symbol or '')}</td>"
                f"<td>{escape(code_ref.lines or '')}</td>"
                f"<td>{'yes' if code_ref.mutate else 'no'}</td>"
                "</tr>"
            )
            for code_ref in criterion.code
        )
        test_rows = "".join(
            f"<li>{escape(f'{test_ref.path}::{case}')}</li>"
            for test_ref in criterion.tests
            for case in test_ref.cases
        )
        mutation_rows = "".join(
            (
                "<li>"
                f"{escape(report.code_path)}::{escape(report.symbol)}"
                f" <strong>{escape(report.status)}</strong> "
                f"({escape(report.mutation)})"
                "</li>"
            )
            for report in mutations_by_criterion.get(criterion.id, [])
        )
        mutation_block = f"<h3>Mutation Check</h3><ul>{mutation_rows}</ul>" if mutation_rows else ""

        sections.append(
            (
                "<section>"
                f"<h2>{escape(criterion.id)}: {escape(criterion.title)}</h2>"
                f"<p>{escape(criterion.description)}</p>"
                "<h3>Code</h3>"
                "<table>"
                "<thead><tr><th>Path</th><th>Symbol</th><th>Lines</th><th>Mutate</th></tr></thead>"
                f"<tbody>{code_rows}</tbody>"
                "</table>"
                "<h3>Tests</h3>"
                f"<ul>{test_rows}</ul>"
                f"{mutation_block}"
                "</section>"
            )
        )

    summary_markup = "".join(
        (
            "<div class='card'>"
            f"<div class='label'>{escape(str(label))}</div>"
            f"<div class='value'>{escape(str(value))}</div>"
            "</div>"
        )
        for label, value in summary_items
    )

    return (
        "<!doctype html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>AC Trace Report</title>"
        "<style>"
        ":root { --bg: #f4f1e8; --panel: #fffdf7; --ink: #1f2430; --muted: #5b6472; --line: #d9d1c0; --accent: #b24c2c; }"
        "body { margin: 0; font-family: Georgia, 'Times New Roman', serif; background: radial-gradient(circle at top, #fff8e8, var(--bg) 58%); color: var(--ink); }"
        "main { max-width: 1100px; margin: 0 auto; padding: 48px 20px 72px; }"
        "h1, h2, h3 { margin: 0 0 12px; }"
        "p, li, td, th { line-height: 1.45; }"
        ".meta { color: var(--muted); margin-bottom: 24px; }"
        ".summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 28px; }"
        ".card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 16px; box-shadow: 0 10px 24px rgba(31, 36, 48, 0.05); }"
        ".label { color: var(--muted); font-size: 0.9rem; }"
        ".value { font-size: 1.5rem; margin-top: 6px; }"
        "section { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; padding: 20px; margin-bottom: 18px; }"
        "table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }"
        "th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 10px 8px; vertical-align: top; }"
        "ul { margin: 0; padding-left: 20px; }"
        "strong { color: var(--accent); }"
        "@media (max-width: 720px) { main { padding-top: 28px; } table, thead, tbody, tr, th, td { display: block; } th { padding-bottom: 4px; } td { padding-top: 0; } }"
        "</style>"
        "</head>"
        "<body>"
        "<main>"
        "<h1>AC Trace Report</h1>"
        f"<div class='meta'>Generated: {escape(generated_at)}</div>"
        f"<div class='summary'>{summary_markup}</div>"
        f"{''.join(sections)}"
        "</main>"
        "</body>"
        "</html>"
    )


def render_report(
    manifest: TraceManifest,
    *,
    format: str,
    validation_errors: list[str] | None = None,
    test_result: PytestResult | None = None,
    mutation_requested: bool = False,
    mutation_reports: list[MutationReport] | None = None,
) -> str:
    if format == "markdown":
        return render_markdown_report(
            manifest,
            validation_errors,
            test_result,
            mutation_requested,
            mutation_reports,
        )
    if format == "html":
        return render_html_report(
            manifest,
            validation_errors,
            test_result,
            mutation_requested,
            mutation_reports,
        )
    if format == "yaml":
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
            "summary": {
                "criteria": len(manifest.acceptance_criteria),
                "code_references": sum(len(criterion.code) for criterion in manifest.acceptance_criteria),
                "test_files": sum(len(criterion.tests) for criterion in manifest.acceptance_criteria),
                "test_cases": sum(
                    len(test_ref.cases)
                    for criterion in manifest.acceptance_criteria
                    for test_ref in criterion.tests
                ),
                "validation": "passed" if not validation_errors else "failed",
                "tests": _test_status(test_result),
                "mutation_check": _mutation_status(mutation_requested, mutation_reports),
            },
            "validation_errors": validation_errors or [],
            "test_run": None
            if test_result is None
            else {
                "returncode": test_result.returncode,
                "status": _test_status(test_result),
                "selectors": test_result.selectors,
                "stdout": test_result.stdout,
                "stderr": test_result.stderr,
            },
            "mutation_check": {
                "requested": mutation_requested,
                "reports": None
                if mutation_reports is None
                else [
                    {
                        "criterion_id": report.criterion_id,
                        "code_path": report.code_path,
                        "symbol": report.symbol,
                        "mutation": report.mutation,
                        "status": report.status,
                        "selectors": report.selectors,
                        "pytest_output": report.pytest_output,
                    }
                    for report in mutation_reports
                ],
            },
            "acceptance_criteria": [
                {
                    "id": criterion.id,
                    "title": criterion.title,
                    "description": criterion.description,
                    "code": [
                        {
                            "path": code_ref.path,
                            "symbol": code_ref.symbol,
                            "lines": code_ref.lines,
                            "mutate": code_ref.mutate,
                        }
                        for code_ref in criterion.code
                    ],
                    "tests": [
                        {
                            "path": test_ref.path,
                            "cases": test_ref.cases,
                        }
                        for test_ref in criterion.tests
                    ],
                }
                for criterion in manifest.acceptance_criteria
            ],
        }
        return yaml.safe_dump(payload, sort_keys=False)
    raise ValueError(f"Unsupported report format: {format}")
