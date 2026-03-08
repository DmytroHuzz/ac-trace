from pathlib import Path

import yaml

from ac_trace.cli import cmd_manifest, cmd_run


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cmd_manifest_validates_then_prints_overview(capsys):
    exit_code = cmd_manifest(str(PROJECT_ROOT / "traceability.yaml"), ["AC-1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Manifest is valid." in captured.out
    assert "AC-1: VIP discount at threshold" in captured.out
    assert "AC-2: Shipping fee by speed" not in captured.out


def test_cmd_run_writes_yaml_report_with_killed_summary(tmp_path, capsys):
    output_path = tmp_path / "run-report.yaml"

    exit_code = cmd_run(
        str(PROJECT_ROOT / "traceability.yaml"),
        ["AC-3"],
        "yaml",
        str(output_path),
    )
    captured = capsys.readouterr()
    payload = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Wrote yaml report to" in captured.out
    assert payload["summary"]["validation"] == "passed"
    assert payload["summary"]["mutations"]["killed"] == 9
    assert payload["summary"]["mutations"]["unkilled"] == 2
    assert payload["acceptance_criteria"][0]["id"] == "AC-3"
    assert payload["acceptance_criteria"][0]["summary"]["status"] == "killed"


def test_cmd_run_marks_ac_unkilled_when_a_test_never_fails(tmp_path, capsys):
    output_path = tmp_path / "run-report.yaml"

    exit_code = cmd_run(
        str(PROJECT_ROOT / "traceability.yaml"),
        ["AC-2"],
        "yaml",
        str(output_path),
    )
    captured = capsys.readouterr()
    payload = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert "test_standard_shipping_fee2 -> passed" in captured.out
    assert payload["acceptance_criteria"][0]["summary"]["status"] == "unkilled"
    assert payload["summary"]["mutations"]["killed"] == 2
    assert payload["acceptance_criteria"][0]["summary"]["tests_never_failed"] == 1
    assert payload["acceptance_criteria"][0]["summary"]["never_failed_tests"] == [
        "tests/test_pricing.py::test_standard_shipping_fee2"
    ]
