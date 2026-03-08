from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape

import yaml

from ac_trace.manifest import TraceManifest
from ac_trace.mutator import FAILED_TEST_STATUSES, MutationReport
from ac_trace.test_runner import selectors_for_criterion


@dataclass(frozen=True)
class CriterionMutationSummary:
    criterion_id: str
    status: str
    total_tests: int
    total_mutations: int
    killed_mutations: int
    unkilled_mutations: int
    skipped_mutations: int
    tests_failed_at_least_once: int
    tests_never_failed: int
    never_failed_selectors: list[str]


def _summary_counts(manifest: TraceManifest) -> dict[str, int]:
    return {
        "criteria": len(manifest.acceptance_criteria),
        "code_refs": sum(len(criterion.code) for criterion in manifest.acceptance_criteria),
        "test_files": sum(len(criterion.tests) for criterion in manifest.acceptance_criteria),
        "test_cases": sum(
            len(test_ref.cases)
            for criterion in manifest.acceptance_criteria
            for test_ref in criterion.tests
        ),
    }


def _mutation_counts(reports: list[MutationReport]) -> Counter[str]:
    return Counter(report.status for report in reports)


def _mutation_by_criterion(reports: list[MutationReport]) -> dict[str, list[MutationReport]]:
    grouped: dict[str, list[MutationReport]] = {}
    for report in reports:
        grouped.setdefault(report.criterion_id, []).append(report)
    return grouped


def _criterion_summaries(
    manifest: TraceManifest,
    mutation_reports: list[MutationReport] | None,
) -> dict[str, CriterionMutationSummary]:
    reports_by_criterion = _mutation_by_criterion(mutation_reports or [])
    summaries: dict[str, CriterionMutationSummary] = {}

    for criterion in manifest.acceptance_criteria:
        selectors = selectors_for_criterion(criterion)
        criterion_reports = reports_by_criterion.get(criterion.id, [])
        failed_selectors = {
            test_result.selector
            for report in criterion_reports
            for test_result in report.test_results
            if test_result.status in FAILED_TEST_STATUSES
        }
        never_failed_selectors = [
            selector for selector in selectors if selector not in failed_selectors
        ]

        mutation_counts = Counter(report.status for report in criterion_reports)
        if never_failed_selectors:
            status = "unkilled"
        elif criterion_reports:
            status = "killed"
        else:
            status = "not_run"

        summaries[criterion.id] = CriterionMutationSummary(
            criterion_id=criterion.id,
            status=status,
            total_tests=len(selectors),
            total_mutations=len(criterion_reports),
            killed_mutations=mutation_counts.get("killed", 0),
            unkilled_mutations=mutation_counts.get("unkilled", 0),
            skipped_mutations=mutation_counts.get("skipped", 0),
            tests_failed_at_least_once=len(failed_selectors),
            tests_never_failed=len(never_failed_selectors),
            never_failed_selectors=never_failed_selectors,
        )

    return summaries


def render_markdown_report(
    manifest: TraceManifest,
    validation_errors: list[str] | None = None,
    mutation_reports: list[MutationReport] | None = None,
) -> str:
    counts = _summary_counts(manifest)
    validation_errors = validation_errors or []
    mutation_reports = mutation_reports or []
    mutation_counts = _mutation_counts(mutation_reports)
    mutations_by_criterion = _mutation_by_criterion(mutation_reports)
    summaries = _criterion_summaries(manifest, mutation_reports)
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
        f"- Mutations killed: {mutation_counts.get('killed', 0)}",
        f"- Mutations unkilled: {mutation_counts.get('unkilled', 0)}",
        f"- Mutations skipped: {mutation_counts.get('skipped', 0)}",
    ]

    if validation_errors:
        lines.extend(["", "## Validation Errors", ""])
        for error in validation_errors:
            lines.append(f"- {error}")

    for criterion in manifest.acceptance_criteria:
        summary = summaries[criterion.id]
        lines.extend(
            [
                "",
                f"## {criterion.id}: {criterion.title}",
                "",
                criterion.description,
                "",
                "Summary",
                "",
                f"- Status: {summary.status}",
                f"- Mutations: {summary.total_mutations}",
                f"- Tests that failed at least once: {summary.tests_failed_at_least_once}",
                f"- Tests never failed: {summary.tests_never_failed}",
            ]
        )
        if summary.never_failed_selectors:
            lines.append("- Never failed selectors:")
            for selector in summary.never_failed_selectors:
                lines.append(f"  - `{selector}`")

        lines.extend(["", "Code", ""])
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
            lines.extend(["", "Mutations", ""])
            for report in criterion_mutations:
                lines.append(
                    f"- `{report.code_path}::{report.symbol}`: {report.status} ({report.mutation})"
                )
                for test_result in report.test_results:
                    lines.append(
                        f"  - `{test_result.selector}` -> {test_result.status}"
                    )

    return "\n".join(lines) + "\n"


def render_html_report(
    manifest: TraceManifest,
    validation_errors: list[str] | None = None,
    mutation_reports: list[MutationReport] | None = None,
) -> str:
    counts = _summary_counts(manifest)
    validation_errors = validation_errors or []
    mutation_reports = mutation_reports or []
    mutation_counts = _mutation_counts(mutation_reports)
    mutations_by_criterion = _mutation_by_criterion(mutation_reports)
    summaries = _criterion_summaries(manifest, mutation_reports)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    summary_items = [
        ("Acceptance criteria", counts["criteria"]),
        ("Code references", counts["code_refs"]),
        ("Test files", counts["test_files"]),
        ("Test cases", counts["test_cases"]),
        ("Validation", "passed" if not validation_errors else "failed"),
        ("Mutations killed", mutation_counts.get("killed", 0)),
        ("Mutations unkilled", mutation_counts.get("unkilled", 0)),
        ("Mutations skipped", mutation_counts.get("skipped", 0)),
    ]

    sections: list[str] = []
    if validation_errors:
        errors_markup = "".join(
            f"<li>{escape(error)}</li>" for error in validation_errors
        )
        sections.append(
            f"<section><h2>Validation Errors</h2><ul>{errors_markup}</ul></section>"
        )

    for criterion in manifest.acceptance_criteria:
        summary = summaries[criterion.id]
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
        summary_rows = "".join(
            (
                "<tr>"
                f"<td>{escape(label)}</td>"
                f"<td>{escape(str(value))}</td>"
                "</tr>"
            )
            for label, value in [
                ("Status", summary.status),
                ("Mutations", summary.total_mutations),
                ("Killed mutations", summary.killed_mutations),
                ("Unkilled mutations", summary.unkilled_mutations),
                ("Skipped mutations", summary.skipped_mutations),
                ("Tests failed at least once", summary.tests_failed_at_least_once),
                ("Tests never failed", summary.tests_never_failed),
            ]
        )
        never_failed_block = ""
        if summary.never_failed_selectors:
            never_failed_items = "".join(
                f"<li>{escape(selector)}</li>"
                for selector in summary.never_failed_selectors
            )
            never_failed_block = (
                "<h3>Never Failed Tests</h3>"
                f"<ul>{never_failed_items}</ul>"
            )

        mutation_blocks = []
        for report in mutations_by_criterion.get(criterion.id, []):
            test_result_rows = "".join(
                (
                    "<tr>"
                    f"<td>{escape(test_result.selector)}</td>"
                    f"<td>{escape(test_result.status)}</td>"
                    f"<td>{escape(test_result.message)}</td>"
                    "</tr>"
                )
                for test_result in report.test_results
            )
            mutation_blocks.append(
                (
                    "<div class='mutation'>"
                    f"<h4>{escape(report.code_path)}::{escape(report.symbol)}</h4>"
                    f"<p><strong>{escape(report.status)}</strong> ({escape(report.mutation)})</p>"
                    "<table>"
                    "<thead><tr><th>Test</th><th>Status</th><th>Message</th></tr></thead>"
                    f"<tbody>{test_result_rows}</tbody>"
                    "</table>"
                    "</div>"
                )
            )

        sections.append(
            (
                "<section>"
                f"<h2>{escape(criterion.id)}: {escape(criterion.title)}</h2>"
                f"<p>{escape(criterion.description)}</p>"
                "<h3>Summary</h3>"
                "<table>"
                f"<tbody>{summary_rows}</tbody>"
                "</table>"
                f"{never_failed_block}"
                "<h3>Code</h3>"
                "<table>"
                "<thead><tr><th>Path</th><th>Symbol</th><th>Lines</th><th>Mutate</th></tr></thead>"
                f"<tbody>{code_rows}</tbody>"
                "</table>"
                "<h3>Tests</h3>"
                f"<ul>{test_rows}</ul>"
                "<h3>Mutations</h3>"
                f"{''.join(mutation_blocks) if mutation_blocks else '<p>No mutation results.</p>'}"
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
        "h1, h2, h3, h4 { margin: 0 0 12px; }"
        "p, li, td, th { line-height: 1.45; }"
        ".meta { color: var(--muted); margin-bottom: 24px; }"
        ".summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 28px; }"
        ".card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 16px; box-shadow: 0 10px 24px rgba(31, 36, 48, 0.05); }"
        ".label { color: var(--muted); font-size: 0.9rem; }"
        ".value { font-size: 1.5rem; margin-top: 6px; }"
        "section { background: var(--panel); border: 1px solid var(--line); border-radius: 20px; padding: 20px; margin-bottom: 18px; }"
        ".mutation { border: 1px solid var(--line); border-radius: 14px; padding: 16px; margin-bottom: 14px; background: #fffaf0; }"
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
    mutation_reports: list[MutationReport] | None = None,
) -> str:
    if format == "markdown":
        return render_markdown_report(
            manifest,
            validation_errors,
            mutation_reports,
        )
    if format == "html":
        return render_html_report(
            manifest,
            validation_errors,
            mutation_reports,
        )
    if format == "yaml":
        mutation_reports = mutation_reports or []
        summaries = _criterion_summaries(manifest, mutation_reports)
        payload = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
            "summary": {
                "criteria": len(manifest.acceptance_criteria),
                "code_references": sum(
                    len(criterion.code) for criterion in manifest.acceptance_criteria
                ),
                "test_files": sum(
                    len(criterion.tests) for criterion in manifest.acceptance_criteria
                ),
                "test_cases": sum(
                    len(test_ref.cases)
                    for criterion in manifest.acceptance_criteria
                    for test_ref in criterion.tests
                ),
                "validation": "passed" if not validation_errors else "failed",
                "mutations": dict(_mutation_counts(mutation_reports)),
            },
            "validation_errors": validation_errors or [],
            "acceptance_criteria": [
                {
                    "id": criterion.id,
                    "title": criterion.title,
                    "description": criterion.description,
                    "summary": {
                        "status": summaries[criterion.id].status,
                        "total_tests": summaries[criterion.id].total_tests,
                        "total_mutations": summaries[criterion.id].total_mutations,
                        "killed_mutations": summaries[criterion.id].killed_mutations,
                        "unkilled_mutations": summaries[criterion.id].unkilled_mutations,
                        "skipped_mutations": summaries[criterion.id].skipped_mutations,
                        "tests_failed_at_least_once": summaries[
                            criterion.id
                        ].tests_failed_at_least_once,
                        "tests_never_failed": summaries[
                            criterion.id
                        ].tests_never_failed,
                        "never_failed_tests": summaries[
                            criterion.id
                        ].never_failed_selectors,
                    },
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
                    "mutations": [
                        {
                            "code_path": report.code_path,
                            "symbol": report.symbol,
                            "mutation": report.mutation,
                            "status": report.status,
                            "test_results": [
                                {
                                    "selector": test_result.selector,
                                    "status": test_result.status,
                                    "message": test_result.message,
                                }
                                for test_result in report.test_results
                            ],
                            "pytest_output": report.pytest_output,
                        }
                        for report in mutation_reports
                        if report.criterion_id == criterion.id
                    ],
                }
                for criterion in manifest.acceptance_criteria
            ],
        }
        return yaml.safe_dump(payload, sort_keys=False)
    raise ValueError(f"Unsupported report format: {format}")
