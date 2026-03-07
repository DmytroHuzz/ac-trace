from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


F = TypeVar("F", bound=Callable[..., object])


def ac(*ids: str) -> Callable[[F], F]:
    """Annotate a test with one or more acceptance-criteria ids."""

    def decorator(func: F) -> F:
        setattr(func, "__ac_ids__", tuple(ids))
        return func

    return decorator
