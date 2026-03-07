# AC Trace

`ac-trace` is a small proof of concept for recovering ownership of AI-generated code.

It makes three things explicit:

1. Acceptance criteria
2. The code that implements each criterion
3. The tests that are supposed to protect that implementation

The manifest is stored as YAML, and the CLI can:

- show an overview of AC -> code -> tests
- validate that the mapped files and symbols exist
- run only the tests linked to a specific AC
- mutate mapped code and verify that the mapped tests fail
- infer a traceability manifest from Python tests annotated with AC ids
- generate Markdown or HTML reports for review and handoff

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

The repo now includes two YAML files:

- [acceptance_criteria.yaml](/Users/dmytrohuz/Code/testurtion/acceptance_criteria.yaml): source-of-truth AC catalog
- [traceability.yaml](/Users/dmytrohuz/Code/testurtion/traceability.yaml): hand-authored traceability example

## Quick start

Create a virtual environment and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
```

Inspect the traceability map:

```bash
python3 -m ac_trace overview traceability.yaml
```

Validate that all references exist:

```bash
python3 -m ac_trace validate traceability.yaml
```

Run tests for one AC:

```bash
python3 -m ac_trace test traceability.yaml --ac AC-1
```

Run the mutation-style test check:

```bash
python3 -m ac_trace mutation-check traceability.yaml
```

Infer a manifest from the AC catalog plus annotated tests:

```bash
python3 -m ac_trace infer acceptance_criteria.yaml --output traceability.generated.yaml
```

Generate a Markdown report:

```bash
python3 -m ac_trace report traceability.generated.yaml --format markdown --with-mutation-check --output traceability-report.md
```

Generate an HTML report:

```bash
python3 -m ac_trace report traceability.generated.yaml --format html --with-mutation-check --output traceability-report.html
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
4. Emits a normal traceability manifest that the rest of the tool can validate, test, mutate, and report on

This keeps the mapping recoverable without pretending that AC-to-code linkage can be guessed purely from filenames or LLM output.

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

`symbol` is the important field for the current prototype. `lines` can also be declared for documentation, but symbol-based traceability is what the validator and mutator use. Set `mutate: false` for traced files that are mostly framework glue and should not participate in mutation checks.
