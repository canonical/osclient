# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The typed result every osclient call returns.

A call returns either a :class:`Success` carrying ``data`` or a :class:`Failure`
carrying a ``reason``; :data:`OpensearchResult` is the union of the two. Both
variants expose ``ok`` / ``data`` / ``reason``, so a result reads as a single
type. A result is truthy when it succeeded, so ``if res:`` (or ``if not res:``,
``assert res``) both branches and narrows ``data`` to be present; you can also
pattern-match on ``Success`` / ``Failure``. An expected failure (HTTP error,
transport error, bad JSON) is a value here, not a raised exception.
"""

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Union

T = TypeVar("T")


@dataclass(frozen=True)
class Success(Generic[T]):
    """A call that succeeded; ``data`` holds the processed result."""

    data: T
    ok: Literal[True] = True
    reason: str = ""

    def __bool__(self) -> Literal[True]:
        return True


@dataclass(frozen=True)
class Failure:
    """A call that failed; ``reason`` explains why and ``data`` is None."""

    reason: str
    ok: Literal[False] = False
    data: None = None

    def __bool__(self) -> Literal[False]:
        return False


# The one type callers name. Written with Union (not ``|``) so the generic alias
# stays subscriptable at runtime on Python 3.10.
OpensearchResult = Union[Success[T], Failure]
