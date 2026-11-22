# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for the instance store."""

import gc
import os
import pickle
import subprocess
import sys
import threading
from pathlib import Path
from typing import ClassVar, Literal, Self

import pytest

from hashcons import InstanceStore


class Frac:
    """Flyweight fraction."""

    _store: ClassVar[InstanceStore] = InstanceStore()
    """Instance store for fractions."""

    __num: int
    __den: int

    __slots__ = ("__weakref__", "__num", "__den")

    def __new__(cls, num: int, den: int) -> Self:
        with Frac._store.instance(cls, (num, den)) as self:
            if self is None:
                if den == 0:
                    raise ZeroDivisionError()
                self = object.__new__(cls)
                self.__num = num
                self.__den = den
                Frac._store.register(self)
            return self

    @property
    def num(self) -> int:
        """Numerator."""
        return self.__num

    @property
    def den(self) -> int:
        """Denominator."""
        return self.__den

    def __getnewargs__(self) -> tuple[int, int]:
        return (self.__num, self.__den)

    def __getstate__(self) -> Literal[None]:
        return None


class NamedFrac(Frac):
    """Flyweight named fraction."""

    __name: str

    __slots__ = ("__name",)

    def __new__(cls, num: int, den: int, name: str) -> Self:
        with Frac._store.instance(cls, (num, den, name)) as self:
            if self is None:
                if not name:
                    raise ValueError("Name must be non-empty.")
                self = Frac.__new__(cls, num, den)
                if name.startswith("_"):
                    raise ValueError("Name must not start with an underscore.")
                self.__name = name
            return self

    @property
    def name(self) -> str:
        """Name."""
        return self.__name

    def __getnewargs__(self) -> tuple[int, int, str]:  # type: ignore[override]
        return (self.num, self.den, self.__name)


class Plain:
    """Weak-referenceable class with no managed constructor."""


def lock_is_free() -> bool:
    """Checks whether another thread can construct a fresh instance."""
    result: list[Frac] = []
    thread = threading.Thread(target=lambda: result.append(Frac(-7, 13)))
    thread.start()
    thread.join(timeout=5)
    return not thread.is_alive() and len(result) == 1


def test_same_key_same_instance() -> None:
    x = Frac(10, 3)
    assert x is Frac(10, 3)
    assert (x.num, x.den) == (10, 3)


def test_different_keys_different_instances() -> None:
    assert Frac(1, 2) is not Frac(2, 1)


def test_get() -> None:
    x = Frac(5, 7)
    assert Frac._store.get(Frac, (5, 7)) is x
    assert Frac._store.get(Frac, (5, 8)) is None
    assert Frac._store.get(NamedFrac, (5, 7)) is None


def test_subclass_instances() -> None:
    x = Frac(10, 3)
    y = NamedFrac(10, 3, "y")
    assert y is not x
    assert y is NamedFrac(10, 3, "y")
    assert y is not NamedFrac(10, 3, "z")
    assert type(y) is NamedFrac
    assert (y.num, y.den, y.name) == (10, 3, "y")
    assert Frac._store.get(NamedFrac, (10, 3, "y")) is y
    assert Frac._store.get(NamedFrac, (10, 3)) is None


def test_failed_construction_releases_lock() -> None:
    with pytest.raises(ZeroDivisionError):
        Frac(1, 0)
    assert Frac._store.get(Frac, (1, 0)) is None
    assert lock_is_free()


def test_failed_subclass_construction_before_super_releases_lock() -> None:
    with pytest.raises(ValueError):
        NamedFrac(1, 3, "")
    assert lock_is_free()


def test_failed_super_construction_releases_lock() -> None:
    with pytest.raises(ZeroDivisionError):
        NamedFrac(1, 0, "x")
    assert Frac._store.get(NamedFrac, (1, 0, "x")) is None
    assert lock_is_free()


def test_failed_subclass_construction_after_super_releases_lock() -> None:
    with pytest.raises(ValueError):
        NamedFrac(1, 3, "_x")
    assert Frac._store.get(NamedFrac, (1, 3, "_x")) is None
    assert Frac._store.get(NamedFrac, (1, 3)) is None
    assert lock_is_free()


def test_error_with_existing_instance_releases_lock() -> None:
    x = Frac(2, 9)
    with pytest.raises(RuntimeError):
        with Frac._store.instance(Frac, (2, 9)) as self:
            assert self is x
            raise RuntimeError()
    assert lock_is_free()


def test_missing_registration() -> None:
    store = InstanceStore()
    with pytest.raises(AssertionError):
        with store.instance(Plain, 0):
            pass
    assert store.get(Plain, 0) is None
    with store.instance(Plain, 0) as self:
        assert self is None
        store.register(Plain())


def test_double_registration() -> None:
    store = InstanceStore()
    with pytest.raises(AssertionError):
        with store.instance(Plain, 0):
            store.register(Plain())
            store.register(Plain())
    assert store.get(Plain, 0) is None


def test_wrong_type_registration() -> None:
    store = InstanceStore()
    with pytest.raises(AssertionError):
        with store.instance(Plain, 0):
            store.register(object())
    assert store.get(Plain, 0) is None


def test_register_outside_building_is_ignored() -> None:
    store = InstanceStore()
    store.register(Plain())
    with store.instance(Plain, 0) as self:
        assert self is None
        instance = Plain()
        store.register(instance)
    assert store.get(Plain, 0) is instance


def test_instances_are_weakly_held() -> None:
    store = InstanceStore()
    with store.instance(Plain, 0):
        store.register(Plain())
    gc.collect()
    assert store.get(Plain, 0) is None


def test_pickle_round_trip() -> None:
    x = Frac(3, 11)
    y = NamedFrac(3, 11, "y")
    assert pickle.loads(pickle.dumps(x)) is x
    assert pickle.loads(pickle.dumps(y)) is y


def construct_after_barrier(barrier: threading.Barrier, results: list[Frac]) -> None:
    """Constructs a shared fraction once all threads reach the barrier."""
    barrier.wait()
    results.append(Frac(123, 456))


def test_concurrent_construction() -> None:
    barrier = threading.Barrier(16)
    results: list[Frac] = []
    threads = [
        threading.Thread(target=construct_after_barrier, args=(barrier, results))
        for _ in range(16)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(results) == 16
    assert all(r is results[0] for r in results)


def test_optimised_mode() -> None:
    script = (
        "from hashcons import InstanceStore\n"
        "class A: pass\n"
        "store = InstanceStore()\n"
        "with store.instance(A, 0) as a:\n"
        "    a = A()\n"
        "    store.register(a)\n"
        "assert store.get(A, 0) is a or print('missing')\n"
        "print('ok')\n"
    )
    src = Path(__file__).parent.parent / "src"
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        capture_output=True,
        text=True,
        env=os.environ | {"PYTHONPATH": str(src)},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
