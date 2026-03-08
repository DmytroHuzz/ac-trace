# AC Trace

`ac-trace` maps acceptance criteria to code and tests, then mutates the code to prove the tests actually catch the breakage.

It is designed to fit an existing Python project, not force the project into a new architecture or workflow. You add a small amount of traceability metadata on top of your current codebase and keep using your current code, tests, and delivery process.

Current scope: Python code and `pytest` tests.

## Why teams use it

When code and tests are generated or heavily assisted by AI, teams often lose three things:

- clear ownership of which code implements which acceptance criterion
- confidence that the mapped tests actually protect that behavior
- an easy way to review requirement -> implementation -> test coverage

`ac-trace` gives that back by making the relationship explicit:

- `AC` -> `code`
- `code` -> `tests`
- `tests` -> proven by mutation checks, not only by green test runs

## What it gives you

- A YAML traceability map from acceptance criteria to code and tests
- An inference mode for Python projects that derives the map from existing pytest tests annotated with AC ids
- A mutation-based check that changes mapped code and runs only the mapped tests
- A clear result per AC: `Killed` (tests failed as expected) or `Unkilled` (tests did not fail)
- HTML and YAML reports that are easy to review locally or attach to CI

## Quick Start With The Demo

The repo contains a small self-contained demo project in [`demo/`](demo):

```text
demo/
  acceptance_criteria.yaml
  traceability.yaml
  demo_api/
  tests/
  test_result_report.html
```

The demo models a tiny quote API with four ACs:

- `AC-1`: VIP discount at threshold
- `AC-2`: Shipping fee by speed
- `AC-3`: Quote API returns a cost breakdown
- `AC-4`: Health endpoint reports service status

### 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install .
```

All examples below use `python -m ac_trace`. If you prefer, you can also use the installed `ac-trace` command.

### 2. Inspect The Demo Inputs

- AC catalog: [`demo/acceptance_criteria.yaml`](demo/acceptance_criteria.yaml)
- Hand-authored manifest: [`demo/traceability.yaml`](demo/traceability.yaml)
- Demo app: [`demo/demo_api/`](demo/demo_api)
- Demo tests: [`demo/tests/`](demo/tests)

### 3. Infer A Manifest From The Demo Tests

```bash
python3 -m ac_trace infer demo/acceptance_criteria.yaml --output demo/traceability.generated.yaml
```

This reads the AC catalog, scans annotated pytest tests, runs coverage, and produces a normal traceability manifest.

### 4. Validate The Manifest And Print The Overview

```bash
python3 -m ac_trace manifest demo/traceability.yaml
```

This validates the manifest first. If it is valid, it prints the AC -> code -> tests overview.

### 5. Run The Mutation Check

```bash
python3 -m ac_trace run demo/traceability.yaml
```

By default this:

- validates the manifest
- mutates each mapped `code:` item
- runs only the mapped `tests:`
- writes an HTML report to `demo/test_result_report.html`

The demo intentionally contains an `Unkilled` AC, so this command exits with code `1`. That is expected and useful: it shows how the tool surfaces weak tests.

### 6. Run A Single AC And Write YAML Output

```bash
python3 -m ac_trace run demo/traceability.yaml --ac AC-1 --report yaml --output demo/ac1-report.yaml
```

Use this when you want machine-readable output or you only want to inspect one AC at a time.

## How The Tool Works

The model is simple:

1. Define acceptance criteria.
2. Map each AC to the code that implements it.
3. Map each AC to the tests that should protect it.
4. Mutate the mapped code and run only the mapped tests.
5. Mark the AC as `Unkilled` if any mapped test never fails.

This is the key difference from a normal green test run: the tool checks whether the tests are sensitive to change, not only whether they pass on the original code.

## What Mutation Means Here

A mutation is a small, deliberate change in the implementation, made only for checking the tests.

Examples:

- `>=` becomes `>`
- `+` becomes `-`
- `15.0` becomes `16.0`

`ac-trace` applies one mutation at a time to code mapped to an AC and runs the mapped tests. If the tests fail, that mutation is `Killed`. If tests stay green when behavior was changed, the tests are too weak for that part of the code.

## Use It On Your Project

The intended adoption path is incremental. You do not need to redesign your project, replace pytest, or restructure your codebase.

### What You Add

You add only the traceability layer:

- an AC catalog
- optionally AC annotations on existing pytest tests
- a traceability manifest

### What You Do Not Need To Change

- your application architecture
- your package layout
- your existing pytest suite
- your development workflow

## Recommended Workflow For A Python Project

### 1. Create An AC Catalog

Create a YAML file that describes the ACs and where source and tests live:

```yaml
project_root: .
source_paths:
  - src
test_paths:
  - tests
acceptance_criteria:
  - id: AC-101
    title: VIP discount at threshold
    description: VIP customers with subtotal >= 100 receive a 10% discount.
```

`project_root` is resolved relative to the catalog file.

### 2. Reuse Your Existing Tests

If you want automatic inference, annotate existing pytest tests with the AC ids they validate:

```python
from ac_trace.annotations import ac


@ac("AC-101")
def test_vip_discount_applies_at_threshold():
    ...
```

You do not need to rewrite the tests. You only add the AC link.

### 3. Generate Or Write The Manifest

You have two options.

Option A: infer the manifest

```bash
python3 -m ac_trace infer path/to/acceptance_criteria.yaml --output path/to/traceability.yaml
```

Option B: write the manifest manually

```yaml
project_root: .
acceptance_criteria:
  - id: AC-101
    title: VIP discount at threshold
    description: VIP customers with subtotal >= 100 receive a 10% discount.
    code:
      - path: src/pricing/service.py
        symbol: calculate_discount
        lines: 10-18
        mutate: true
    tests:
      - path: tests/test_pricing.py
        cases:
          - test_vip_discount_applies_at_threshold
          - test_non_vip_customer_gets_no_discount
```

Notes:

- `symbol` is the Python function or method to trace
- if `lines` is present, mutations are limited to that line range inside the symbol
- if multiple mutation sites exist in that range, all of them are executed one by one
- use `mutate: false` for traced framework glue that you want to include in the map but not mutate

### 4. Validate The Mapping

```bash
python3 -m ac_trace manifest path/to/traceability.yaml
```

This checks that:

- code files exist
- test files exist
- symbols exist
- line ranges are valid
- mapped test case names exist

### 5. Run The Mutation Check

```bash
python3 -m ac_trace run path/to/traceability.yaml
```

By default this writes `test_result_report.html` next to the manifest.

Useful variants:

```bash
python3 -m ac_trace run path/to/traceability.yaml --ac AC-101
python3 -m ac_trace run path/to/traceability.yaml --report yaml
python3 -m ac_trace run path/to/traceability.yaml --report yaml --output path/to/report.yaml
python3 -m ac_trace run path/to/traceability.yaml --report none
```

### 6. Add It To CI

The `run` command is CI-friendly:

- exit code `0`: all selected ACs are `Killed`
- exit code `1`: manifest validation failed or at least one selected AC is `Unkilled`

That means you can add it to your pipeline without changing the rest of your workflow:

```bash
python3 -m ac_trace manifest path/to/traceability.yaml
python3 -m ac_trace run path/to/traceability.yaml --report yaml --output artifacts/ac-trace.yaml
```

A typical usage pattern is:

- run it on pull requests for changed ACs
- publish the HTML or YAML report as a build artifact
- fail the build when an AC is still `Unkilled`

## Result Model

### `Killed`

An AC is `Killed` when every test mapped to that AC fails at least once across the executed mutations.

### `Unkilled`

An AC is `Unkilled` when at least one mapped test never fails. That means the traceability map may exist, but the mapped tests still do not fully protect the behavior.

## Commands

### `infer`

Generates a traceability manifest from:

- the AC catalog
- AC annotations on pytest tests
- coverage collected from those tests

### `manifest`

Validates the manifest and prints an overview only if validation succeeds.

### `run`

Runs the mutation-based test check and writes a report in `html`, `yaml`, or no report.

## Demo Files

- AC catalog: [`demo/acceptance_criteria.yaml`](demo/acceptance_criteria.yaml)
- Demo manifest: [`demo/traceability.yaml`](demo/traceability.yaml)
- Demo report: [`demo/test_result_report.html`](demo/test_result_report.html)
- Demo API: [`demo/demo_api/app.py`](demo/demo_api/app.py)
- Demo pricing logic: [`demo/demo_api/services/pricing.py`](demo/demo_api/services/pricing.py)
- Demo tests: [`demo/tests/test_api.py`](demo/tests/test_api.py), [`demo/tests/test_pricing.py`](demo/tests/test_pricing.py)

## Current Scope

Today the implementation is intentionally narrow:

- Python only
- pytest only
- YAML-based traceability

That keeps the workflow practical and easy to integrate into a real project without forcing a large change in how the project is built or tested.
