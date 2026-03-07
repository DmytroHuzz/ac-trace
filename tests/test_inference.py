from pathlib import Path

from ac_trace.catalog import load_catalog
from ac_trace.inference import infer_manifest
from ac_trace.manifest import dump_manifest, load_manifest
from ac_trace.validator import validate_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_infer_manifest_from_catalog(tmp_path):
    catalog = load_catalog(PROJECT_ROOT / "acceptance_criteria.yaml")

    manifest = infer_manifest(catalog)
    errors = validate_manifest(manifest)

    assert errors == []

    criteria = {criterion.id: criterion for criterion in manifest.acceptance_criteria}

    ac1_tests = {
        f"{test_ref.path}::{case}"
        for test_ref in criteria["AC-1"].tests
        for case in test_ref.cases
    }
    ac1_symbols = {code_ref.symbol for code_ref in criteria["AC-1"].code if code_ref.symbol}
    assert ac1_tests == {
        "tests/test_pricing.py::test_non_vip_customer_gets_no_discount",
        "tests/test_pricing.py::test_vip_discount_applies_at_threshold",
    }
    assert "calculate_discount" in ac1_symbols

    ac3_symbols = {code_ref.symbol for code_ref in criteria["AC-3"].code if code_ref.symbol}
    assert "build_quote" in ac3_symbols
    assert "create_app.quote" in ac3_symbols

    output_path = tmp_path / "traceability.generated.yaml"
    output_path.write_text(dump_manifest(manifest, relative_to=output_path.parent), encoding="utf-8")
    reloaded_manifest = load_manifest(output_path)

    assert validate_manifest(reloaded_manifest) == []
