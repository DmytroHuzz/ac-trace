# AC Trace Report

Generated: 2026-03-07 21:13:20Z

## Summary

- Acceptance criteria: 4
- Code references: 7
- Test files: 5
- Test cases: 7
- Validation: passed
- Mutations killed: 5
- Mutations survived: 0
- Mutations skipped: 0

## AC-1: VIP discount at threshold

VIP customers with a subtotal of at least 100 receive a 10% discount.

Code

- `demo_api/services/pricing.py`: calculate_discount, lines 4-7

Tests

- `tests/test_pricing.py::test_non_vip_customer_gets_no_discount`
- `tests/test_pricing.py::test_vip_discount_applies_at_threshold`

Mutation Check

- `demo_api/services/pricing.py::calculate_discount`: killed (constant 100 -> 101)

## AC-2: Shipping fee by speed

Expedited shipping costs 15.0 and standard shipping costs 5.0.

Code

- `demo_api/services/pricing.py`: calculate_shipping, lines 10-11

Tests

- `tests/test_pricing.py::test_expedited_shipping_fee`
- `tests/test_pricing.py::test_standard_shipping_fee`

Mutation Check

- `demo_api/services/pricing.py::calculate_shipping`: killed (constant 15.0 -> 16.0)

## AC-3: Quote API returns a cost breakdown

POST /quote returns subtotal, discount, shipping, and total.

Code

- `demo_api/app.py`: create_app.quote, lines 16-21, mutation skipped
- `demo_api/services/pricing.py`: build_quote, lines 14-23
- `demo_api/services/pricing.py`: calculate_discount, lines 4-7
- `demo_api/services/pricing.py`: calculate_shipping, lines 10-11

Tests

- `tests/test_api.py::test_quote_endpoint_returns_breakdown`
- `tests/test_pricing.py::test_build_quote_combines_discount_and_shipping`

Mutation Check

- `demo_api/services/pricing.py::build_quote`: killed (Sub -> Add)
- `demo_api/services/pricing.py::calculate_discount`: killed (constant 100 -> 101)
- `demo_api/services/pricing.py::calculate_shipping`: killed (constant 15.0 -> 16.0)

## AC-4: Health endpoint reports service status

GET /health returns {"status": "ok"}.

Code

- `demo_api/app.py`: create_app.health, lines 12-13, mutation skipped

Tests

- `tests/test_api.py::test_healthcheck`
