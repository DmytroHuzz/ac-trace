from pathlib import Path

import yaml

from ac_trace.manifest import load_manifest
from ac_trace.mutator import MutationReport
from ac_trace.test_runner import PytestCaseResult
from ac_trace.reporting import render_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_render_markdown_report_includes_summary_and_mutations():
    manifest = load_manifest(PROJECT_ROOT / "traceability.yaml")
    mutation_reports = [
        MutationReport(
            criterion_id="AC-1",
            code_path="demo_api/services/pricing.py",
            symbol="calculate_discount",
            mutation="constant 100 -> 101",
            status="killed",
            selectors=[
                "tests/test_pricing.py::test_vip_discount_applies_at_threshold",
                "tests/test_pricing.py::test_non_vip_customer_gets_no_discount",
            ],
            test_results=[
                PytestCaseResult(
                    selector="tests/test_pricing.py::test_vip_discount_applies_at_threshold",
                    status="failed",
                ),
                PytestCaseResult(
                    selector="tests/test_pricing.py::test_non_vip_customer_gets_no_discount",
                    status="failed",
                ),
            ],
            pytest_output="",
        )
    ]

    report = render_report(
        manifest,
        format="markdown",
        validation_errors=[],
        mutation_reports=mutation_reports,
    )

    assert "# AC Trace Report" in report
    assert "AC-1: VIP discount at threshold" in report
    assert "Mutations killed: 1" in report
    assert "Killed ACs: 1" in report
    assert "Unkilled ACs: 3" in report
    assert "Status: Killed" in report
    assert "`demo_api/services/pricing.py::calculate_discount`: killed" in report
    assert "`tests/test_pricing.py::test_vip_discount_applies_at_threshold` -> failed" in report


def test_render_html_report_includes_sections():
    manifest = load_manifest(PROJECT_ROOT / "traceability.yaml")
    mutation_reports = [
        MutationReport(
            criterion_id="AC-1",
            code_path="demo_api/services/pricing.py",
            symbol="calculate_discount",
            mutation="constant 100 -> 101",
            status="killed",
            selectors=[
                "tests/test_pricing.py::test_vip_discount_applies_at_threshold",
                "tests/test_pricing.py::test_non_vip_customer_gets_no_discount",
            ],
            test_results=[
                PytestCaseResult(
                    selector="tests/test_pricing.py::test_vip_discount_applies_at_threshold",
                    status="failed",
                ),
                PytestCaseResult(
                    selector="tests/test_pricing.py::test_non_vip_customer_gets_no_discount",
                    status="failed",
                ),
            ],
            pytest_output="",
        )
    ]

    report = render_report(
        manifest,
        format="html",
        validation_errors=[],
        mutation_reports=mutation_reports,
    )

    assert "<!doctype html>" in report
    assert "AC Trace Report" in report
    assert "VIP discount at threshold" in report
    assert "Killed ACs" in report
    assert "Unkilled ACs" in report
    assert "status-badge status-killed" in report
    assert ">Killed</span>" in report
    assert "<table>" in report


def test_render_yaml_report_includes_per_test_mutation_results():
    manifest = load_manifest(PROJECT_ROOT / "traceability.yaml")
    mutation_reports = [
        MutationReport(
            criterion_id="AC-1",
            code_path="demo_api/services/pricing.py",
            symbol="calculate_discount",
            mutation="constant 100 -> 101",
            status="unkilled",
            selectors=[
                "tests/test_pricing.py::test_vip_discount_applies_at_threshold",
                "tests/test_pricing.py::test_non_vip_customer_gets_no_discount",
            ],
            test_results=[
                PytestCaseResult(
                    selector="tests/test_pricing.py::test_vip_discount_applies_at_threshold",
                    status="failed",
                ),
                PytestCaseResult(
                    selector="tests/test_pricing.py::test_non_vip_customer_gets_no_discount",
                    status="passed",
                ),
            ],
            pytest_output="failed one, passed one",
        )
    ]

    report = render_report(
        manifest,
        format="yaml",
        validation_errors=[],
        mutation_reports=mutation_reports,
    )
    payload = yaml.safe_load(report)

    assert payload["summary"]["mutations"]["unkilled"] == 1
    assert payload["summary"]["criteria_by_status"]["unkilled"] == 4
    assert payload["acceptance_criteria"][0]["summary"]["status"] == "unkilled"
    assert payload["acceptance_criteria"][0]["summary"]["tests_never_failed"] == 1
    assert payload["acceptance_criteria"][0]["mutations"][0]["test_results"][1]["status"] == "passed"
