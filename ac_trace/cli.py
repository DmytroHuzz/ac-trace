from __future__ import annotations

import argparse
from pathlib import Path

from ac_trace.catalog import CatalogError, load_catalog
from ac_trace.inference import InferenceError, infer_manifest
from ac_trace.manifest import ManifestError, dump_manifest, load_manifest
from ac_trace.mutator import run_mutation_check
from ac_trace.reporting import render_report
from ac_trace.test_runner import run_tests_for_manifest
from ac_trace.validator import validate_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acceptance criteria traceability demo"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    overview = subparsers.add_parser("overview")
    overview.add_argument("manifest", help="Path to traceability YAML file")
    overview.add_argument(
        "--ac", action="append", dest="ac_ids", help="Acceptance criterion id"
    )

    validate = subparsers.add_parser("validate")
    validate.add_argument("manifest", help="Path to traceability YAML file")

    test = subparsers.add_parser("test")
    test.add_argument("manifest", help="Path to traceability YAML file")
    test.add_argument(
        "--ac", action="append", dest="ac_ids", help="Acceptance criterion id"
    )

    mutation_check = subparsers.add_parser("mutation-check")
    mutation_check.add_argument("manifest", help="Path to traceability YAML file")
    mutation_check.add_argument(
        "--ac", action="append", dest="ac_ids", help="Acceptance criterion id"
    )

    infer = subparsers.add_parser("infer")
    infer.add_argument("catalog", help="Path to acceptance-criteria catalog YAML file")
    infer.add_argument(
        "--output", help="Path to write the inferred traceability manifest"
    )

    report = subparsers.add_parser("report")
    report.add_argument("manifest", help="Path to traceability YAML file")
    report.add_argument(
        "--ac", action="append", dest="ac_ids", help="Acceptance criterion id"
    )
    report.add_argument("--format", choices=["markdown", "html"], default="markdown")
    report.add_argument("--output", help="Path to write the generated report")
    report.add_argument(
        "--with-mutation-check",
        action="store_true",
        help="Include mutation-check results",
    )

    return parser


def cmd_overview(manifest_path: str, ac_ids: list[str] | None) -> int:
    manifest = load_manifest(manifest_path)
    for criterion in manifest.find_criteria(ac_ids):
        print(f"{criterion.id}: {criterion.title}")
        print(f"  description: {criterion.description}")
        for code_ref in criterion.code:
            location = code_ref.symbol or code_ref.lines or "file"
            print(f"  code: {code_ref.path} -> {location}")
        for test_ref in criterion.tests:
            cases = ", ".join(test_ref.cases)
            print(f"  tests: {test_ref.path} -> {cases}")
        print()
    return 0


def cmd_validate(manifest_path: str) -> int:
    manifest = load_manifest(manifest_path)
    errors = validate_manifest(manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("Manifest is valid.")
    return 0


def cmd_test(manifest_path: str, ac_ids: list[str] | None) -> int:
    manifest = load_manifest(manifest_path).select(ac_ids)
    result = run_tests_for_manifest(manifest, ac_ids)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.returncode


def cmd_mutation_check(manifest_path: str, ac_ids: list[str] | None) -> int:
    manifest = load_manifest(manifest_path).select(ac_ids)
    reports = run_mutation_check(manifest, ac_ids)

    exit_code = 0
    for report in reports:
        selectors = ", ".join(report.selectors)
        print(
            f"{report.criterion_id} | {report.code_path}::{report.symbol} | "
            f"{report.mutation} | {report.status}"
        )
        print(f"  selectors: {selectors}")
        if report.status in {"survived"}:
            exit_code = 1
            if report.pytest_output:
                print("  pytest output:")
                for line in report.pytest_output.strip().splitlines():
                    print(f"    {line}")
        elif report.status == "skipped":
            print("  pytest output: skipped because no supported mutation was found")

    return exit_code


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


def cmd_report(
    manifest_path: str,
    ac_ids: list[str] | None,
    format: str,
    output: str | None,
    with_mutation_check: bool,
) -> int:
    manifest = load_manifest(manifest_path).select(ac_ids)
    validation_errors = validate_manifest(manifest)
    mutation_reports = None
    if with_mutation_check and not validation_errors:
        mutation_reports = run_mutation_check(manifest)

    content = render_report(
        manifest,
        format=format,
        validation_errors=validation_errors,
        mutation_reports=mutation_reports,
    )

    if output:
        output_path = Path(output).resolve()
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote {format} report to {output_path}")
    else:
        print(content, end="")

    if validation_errors:
        return 1
    if mutation_reports and any(
        report.status == "survived" for report in mutation_reports
    ):
        return 1
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "overview":
            return cmd_overview(args.manifest, args.ac_ids)
        if args.command == "validate":
            return cmd_validate(args.manifest)
        if args.command == "test":
            return cmd_test(args.manifest, args.ac_ids)
        if args.command == "mutation-check":
            return cmd_mutation_check(args.manifest, args.ac_ids)
        if args.command == "infer":
            return cmd_infer(args.catalog, args.output)
        if args.command == "report":
            return cmd_report(
                args.manifest,
                args.ac_ids,
                args.format,
                args.output,
                args.with_mutation_check,
            )
    except (CatalogError, InferenceError, ManifestError) as error:
        print(f"ERROR: {error}")
        return 1

    parser.print_help()
    return 1
