from pathlib import Path

from ac_trace.manifest import load_manifest
from ac_trace.validator import validate_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_validate_manifest_rejects_line_range_outside_symbol(tmp_path):
    demo_root = (PROJECT_ROOT / "demo").as_posix()
    manifest_path = tmp_path / "traceability.invalid.yaml"
    manifest_path.write_text(
        (
            f"project_root: {demo_root}\n"
            "acceptance_criteria:\n"
            "  - id: AC-X\n"
            "    title: Invalid lines\n"
            "    description: Invalid line range for the symbol.\n"
            "    code:\n"
            "      - path: demo_api/services/pricing.py\n"
            "        symbol: calculate_shipping\n"
            "        lines: 1-2\n"
            "        mutate: true\n"
            "    tests:\n"
            "      - path: tests/test_pricing.py\n"
            "        cases:\n"
            "          - test_expedited_shipping_fee\n"
        ),
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)
    errors = validate_manifest(manifest)

    assert (
        "AC-X: line range '1-2' falls outside symbol 'calculate_shipping' in "
        "demo_api/services/pricing.py"
    ) in errors
