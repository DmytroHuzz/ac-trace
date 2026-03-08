from __future__ import annotations

import argparse
from pathlib import Path

from ac_trace.catalog import CatalogError, load_catalog
from ac_trace.inference import InferenceError, infer_manifest
from ac_trace.manifest import ManifestError, dump_manifest, load_manifest
from ac_trace.mutator import FAILED_TEST_STATUSES, run_mutation_check
from ac_trace.reporting import render_report
from ac_trace.test_runner import selectors_for_criterion
from ac_trace.validator import validate_manifest


class CliError(ValueError):
    """Raised when CLI arguments are inconsistent."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acceptance criteria traceability demo"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("manifest", help="Path to traceability YAML file")
    manifest.add_argument(
        "--ac", action="append", dest="ac_ids", help="Acceptance criterion id"
    )

    run = subparsers.add_parser("run")
    run.add_argument("manifest", help="Path to traceability YAML file")
    run.add_argument(
        "--ac", action="append", dest="ac_ids", help="Acceptance criterion id"
    )
    run.add_argument(
        "--report",
        choices=["none", "html", "yaml"],
        default="html",
        help="Write no report, an HTML report, or a YAML report",
    )
    run.add_argument(
        "--output",
        help="Path to write the generated report",
    )

    infer = subparsers.add_parser("infer")
    infer.add_argument("catalog", help="Path to acceptance-criteria catalog YAML file")
    infer.add_argument(
        "--output", help="Path to write the inferred traceability manifest"
    )

    return parser


def _print_overview(manifest) -> None:
    for criterion in manifest.acceptance_criteria:
        print(f"{criterion.id}: {criterion.title}")
        print(f"  description: {criterion.description}")
        for code_ref in criterion.code:
            location = code_ref.symbol or code_ref.lines or "file"
            print(f"  code: {code_ref.path} -> {location}")
        for test_ref in criterion.tests:
            cases = ", ".join(test_ref.cases)
            print(f"  tests: {test_ref.path} -> {cases}")
        print()


def _print_validation_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"ERROR: {error}")


def _print_mutation_reports(reports) -> None:
    for report in reports:
        print(
            f"{report.criterion_id} | {report.code_path}::{report.symbol} | "
            f"{report.mutation} | {report.status}"
        )
        for test_result in report.test_results:
            print(f"  {test_result.selector} -> {test_result.status}")
            if test_result.message:
                print(f"    {test_result.message}")
        if report.status in {"unkilled"} and report.pytest_output:
            print("  pytest output:")
            for line in report.pytest_output.strip().splitlines():
                print(f"    {line}")
        elif report.status == "skipped":
            print("  pytest output: skipped because no supported mutation was found")


def _default_output_path(report_format: str) -> Path | None:
    if report_format == "html":
        return Path("test_result_report.html").resolve()
    if report_format == "yaml":
        return Path("test_result_report.yaml").resolve()
    return None


def cmd_manifest(manifest_path: str, ac_ids: list[str] | None) -> int:
    manifest = load_manifest(manifest_path).select(ac_ids)
    errors = validate_manifest(manifest)
    if errors:
        _print_validation_errors(errors)
        return 1

    print("Manifest is valid.")
    print()
    _print_overview(manifest)
    return 0


def cmd_infer(catalog_path: str, output: str | None) -> int:
    catalog = load_catalog(catalog_path)
    manifest = infer_manifest(catalog)
    output_path = Path(output).resolve() if output else None
    content = dump_manifest(
        manifest,
        relative_to=output_path.parent if output_path else catalog.project_root,
    )

    if output_path:
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote inferred manifest to {output_path}")
    else:
        print(content, end="")
    return 0


def cmd_run(
    manifest_path: str,
    ac_ids: list[str] | None,
    report_format: str,
    output: str | None,
) -> int:
    manifest = load_manifest(manifest_path).select(ac_ids)
    validation_errors = validate_manifest(manifest)
    mutation_reports = None

    if validation_errors:
        _print_validation_errors(validation_errors)
    else:
        mutation_reports = run_mutation_check(manifest)
        _print_mutation_reports(mutation_reports)

    if report_format == "none" and output is not None:
        raise CliError("Cannot use --output when --report is 'none'")

    if report_format != "none":
        output_path = Path(output).resolve() if output else _default_output_path(report_format)
        content = render_report(
            manifest,
            format=report_format,
            validation_errors=validation_errors,
            mutation_reports=mutation_reports,
        )
        assert output_path is not None
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote {report_format} report to {output_path}")

    if validation_errors:
        return 1

    assert mutation_reports is not None
    for criterion in manifest.acceptance_criteria:
        selectors = set(selectors_for_criterion(criterion))
        failed_selectors = {
            test_result.selector
            for report in mutation_reports
            if report.criterion_id == criterion.id
            for test_result in report.test_results
            if test_result.status in FAILED_TEST_STATUSES
        }
        if selectors.difference(failed_selectors):
            return 1
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "manifest":
            return cmd_manifest(args.manifest, args.ac_ids)
        if args.command == "infer":
            return cmd_infer(args.catalog, args.output)
        if args.command == "run":
            return cmd_run(
                args.manifest,
                args.ac_ids,
                args.report,
                args.output,
            )
    except (CatalogError, CliError, InferenceError, ManifestError) as error:
        print(f"ERROR: {error}")
        return 1

    parser.print_help()
    return 1
