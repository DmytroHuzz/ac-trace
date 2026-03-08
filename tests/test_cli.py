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


def test_cmd_run_writes_yaml_report(tmp_path, capsys):
    output_path = tmp_path / "run-report.yaml"

    exit_code = cmd_run(
        str(PROJECT_ROOT / "traceability.yaml"),
        ["AC-1"],
        False,
        "yaml",
        str(output_path),
    )
    captured = capsys.readouterr()
    payload = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Wrote yaml report to" in captured.out
    assert payload["summary"]["validation"] == "passed"
    assert payload["summary"]["tests"] == "passed"
    assert payload["summary"]["mutation_check"] == "disabled"
    assert payload["acceptance_criteria"][0]["id"] == "AC-1"
