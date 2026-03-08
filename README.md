# AC Trace

`ac-trace` is a small proof of concept for recovering ownership of AI-generated code.

It makes three things explicit:

1. Acceptance criteria
2. The code that implements each criterion
3. The tests that are supposed to protect that implementation

The manifest is stored as YAML, and the CLI can:

- validate a manifest and print its overview in one step
- run mutation checks for the mapped code and emit an HTML or YAML report in one step
- mutate mapped code and verify that the mapped tests fail
- infer a traceability manifest from Python tests annotated with AC ids
- generate HTML or YAML execution reports for review and handoff

## Why this shape

This is intentionally narrow. The current implementation focuses on Python symbols and pytest tests so the core workflow is tangible:

- define traceability explicitly
- run the right tests for a requirement
- challenge those tests with mutation-style changes
- recover mappings automatically from real execution data instead of maintaining them by hand only

For other languages, the same high-level shape still applies, but the parser, coverage, and mutation adapters would be different.

## Demo domain

The demo API is a tiny quote service with these ACs:

- `AC-1`: VIP customers with subtotal `>= 100` receive a 10% discount
- `AC-2`: Expedited shipping costs `15`, standard shipping costs `5`
- `AC-3`: `POST /quote` returns subtotal, discount, shipping, and total
- `AC-4`: `GET /health` returns `{"status": "ok"}`

The demo project now lives under [demo](/Users/dmytrohuz/Code/testurtion/demo):

- [acceptance_criteria.yaml](/Users/dmytrohuz/Code/testurtion/demo/acceptance_criteria.yaml): source-of-truth AC catalog
- [traceability.yaml](/Users/dmytrohuz/Code/testurtion/demo/traceability.yaml): hand-authored traceability example
- [test_result_report.html](/Users/dmytrohuz/Code/testurtion/demo/test_result_report.html): generated demo report

## Quick start

Create a virtual environment and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
```

Infer a manifest from the AC catalog plus annotated tests:

```bash
python3 -m ac_trace infer demo/acceptance_criteria.yaml --output demo/traceability.yaml
```

Validate the manifest and print its overview:

```bash
python3 -m ac_trace manifest demo/traceability.yaml
```

Run mutation checks for all ACs and write the default HTML report:

```bash
python3 -m ac_trace run demo/traceability.yaml
```

Run only one AC and write a YAML report:

```bash
python3 -m ac_trace run demo/traceability.yaml --ac AC-1 --report yaml --output demo/ac1-result.yaml
```

Generate an HTML report from the inferred manifest:

```bash
python3 -m ac_trace run demo/traceability.generated.yaml --report html --output demo/traceability-report.html
```

Run the inferred manifest without writing any report:

```bash
python3 -m ac_trace run demo/traceability.generated.yaml --report none
```

## Inference workflow

Automatic inference currently works for Python and expects pytest tests to declare which AC they validate:

```python
from ac_trace.annotations import ac


@ac("AC-1")
def test_vip_discount_applies_at_threshold():
    ...
```

The inference command then:

1. Finds `@ac(...)`-annotated tests under `test_paths`
2. Runs each mapped test with coverage
3. Uses Python AST ranges to convert covered lines into function-level code references
4. Emits a normal traceability manifest that the rest of the tool can validate, execute, mutate, and report on

This keeps the mapping recoverable without pretending that AC-to-code linkage can be guessed purely from filenames or LLM output.

## CLI shape

`manifest`

- validates the manifest first
- prints the AC -> code -> tests overview only when validation passes
- supports `--ac AC_ID` to scope the output

`run`

- validates the manifest first
- discovers every supported mutation site inside each mutable `code:` item
- if `lines` is defined, only mutation sites fully inside that line range are considered
- applies one mutation site at a time and runs all mapped tests from `tests:` for each mutation
- writes an HTML report by default; use `--report yaml` or `--report none`
- scopes to all ACs by default; use `--ac AC_ID` to narrow it
- writes to `test_result_report.html` or `test_result_report.yaml` next to the manifest unless `--output` is provided
- marks an AC as `unkilled` if any mapped test never fails across all mutations for that AC

## Manifest shape

```yaml
project_root: .
acceptance_criteria:
  - id: AC-1
    title: Example criterion
    description: Short business rule
    code:
      - path: app/service.py
        symbol: calculate_value
        mutate: true
    tests:
      - path: tests/test_service.py
        cases:
          - test_calculate_value
```

`symbol` defines the Python function or method to trace. If `lines` is also present, mutation is limited to the intersection of that symbol and the declared line range. When multiple mutation sites exist in that scoped region, the runner executes them all as separate mutation runs. Set `mutate: false` for traced files that are mostly framework glue and should not participate in mutation checks.
