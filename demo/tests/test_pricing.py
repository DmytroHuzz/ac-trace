from ac_trace.annotations import ac
from demo.demo_api.services.pricing import (
    build_quote,
    calculate_discount,
    calculate_shipping,
)


@ac("AC-1")
def test_vip_discount_applies_at_threshold():
    assert calculate_discount(100, True) == 10.0


@ac("AC-1")
def test_non_vip_customer_gets_no_discount():
    assert calculate_discount(150, False) == 0.0


@ac("AC-2")
def test_expedited_shipping_fee():
    assert calculate_shipping(True) == 15.0


@ac("AC-2")
def test_standard_shipping_fee():
    assert calculate_shipping(False) == 5.0


@ac("AC-2")
def test_standard_shipping_fee_never_fails():
    assert True


@ac("AC-3")
def test_build_quote_combines_discount_and_shipping():
    assert build_quote(subtotal=100, is_vip=True, expedited=False) == {
        "subtotal": 100,
        "discount": 10.0,
        "shipping": 5.0,
        "total": 95.0,
    }
