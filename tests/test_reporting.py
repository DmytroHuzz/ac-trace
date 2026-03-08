from pathlib import Path

import yaml

from ac_trace.manifest import load_manifest
from ac_trace.mutator import MutationReport
from ac_trace.test_runner import PytestResult
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
            selectors=["tests/test_pricing.py::test_vip_discount_applies_at_threshold"],
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
    assert "`demo_api/services/pricing.py::calculate_discount`: killed" in report


def test_render_html_report_includes_sections():
    manifest = load_manifest(PROJECT_ROOT / "traceability.yaml")

    report = render_report(
        manifest,
        format="html",
        validation_errors=[],
        mutation_reports=[],
    )

    assert "<!doctype html>" in report
    assert "AC Trace Report" in report
    assert "VIP discount at threshold" in report
    assert "<table>" in report


def test_render_yaml_report_includes_test_and_mutation_status():
    manifest = load_manifest(PROJECT_ROOT / "traceability.yaml")
    test_result = PytestResult(
        selectors=["tests/test_pricing.py::test_vip_discount_applies_at_threshold"],
        returncode=0,
        stdout="1 passed",
        stderr="",
    )
    mutation_reports = [
        MutationReport(
            criterion_id="AC-1",
            code_path="demo_api/services/pricing.py",
            symbol="calculate_discount",
            mutation="constant 100 -> 101",
            status="killed",
            selectors=["tests/test_pricing.py::test_vip_discount_applies_at_threshold"],
            pytest_output="",
        )
    ]

    report = render_report(
        manifest,
        format="yaml",
        validation_errors=[],
        test_result=test_result,
        mutation_requested=True,
        mutation_reports=mutation_reports,
    )
    payload = yaml.safe_load(report)

    assert payload["summary"]["tests"] == "passed"
    assert payload["summary"]["mutation_check"] == "passed"
    assert payload["test_run"]["returncode"] == 0
    assert payload["mutation_check"]["reports"][0]["status"] == "killed"
