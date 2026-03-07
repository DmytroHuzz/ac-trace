from __future__ import annotations


def calculate_discount(subtotal: float, is_vip: bool) -> float:
    if is_vip and subtotal >= 100:
        return round(subtotal * 0.10, 2)
    return 0.0


def calculate_shipping(expedited: bool) -> float:
    return 15.0 if expedited else 5.0


def build_quote(subtotal: float, is_vip: bool, expedited: bool) -> dict[str, float]:
    discount = calculate_discount(subtotal=subtotal, is_vip=is_vip)
    shipping = calculate_shipping(expedited=expedited)
    total = round(subtotal - discount + shipping, 2)
    return {
        "subtotal": subtotal,
        "discount": discount,
        "shipping": shipping,
        "total": total,
    }
