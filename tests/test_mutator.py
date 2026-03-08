from pathlib import Path

from ac_trace.manifest import load_manifest
from ac_trace.mutator import discover_mutation_sites, mutate_symbol, run_mutation_check


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_mutate_symbol_respects_line_range(tmp_path):
    source_path = PROJECT_ROOT / "demo/demo_api/services/pricing.py"
    temp_path = tmp_path / "pricing.py"
    temp_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

    no_mutations = discover_mutation_sites(temp_path, "calculate_discount", "4-5")
    assert len(no_mutations) == 1

    mutations = discover_mutation_sites(temp_path, "calculate_discount", "6-7")
    assert len(mutations) == 5

    did_mutate = mutate_symbol(
        temp_path,
        "calculate_discount",
        "6-7",
        target_index=mutations[0].index,
    )
    assert did_mutate is not None


def test_run_mutation_check_uses_code_ref_lines_and_all_supported_mutations():
    manifest = load_manifest(PROJECT_ROOT / "demo/traceability.yaml").select(["AC-1"])

    reports = run_mutation_check(manifest)
    assert len(reports) == 6
    assert sum(report.status == "killed" for report in reports) == 5
    assert sum(report.status == "unkilled" for report in reports) == 1
