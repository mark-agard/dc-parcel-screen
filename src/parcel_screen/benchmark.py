from collections.abc import Callable
from time import perf_counter
from typing import Any, TypeVar

T = TypeVar("T")


def measure_call(
    function: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> tuple[T, float]:
    started = perf_counter()
    result = function(*args, **kwargs)
    return result, perf_counter() - started
