# SPDX-License-Identifier: LGPL-3.0-or-later

"""Tests for the instance store."""

import gc
from math import gcd
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
                with Frac._store.super():
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


def new_plain_class() -> type:
    """Creates a fresh weak-referenceable class with no managed constructor."""
    return type("Plain", (), {})


class Node:
    """Flyweight node constructing its child inside its own constructor."""

    _store: ClassVar[InstanceStore] = InstanceStore()
    """Instance store for nodes."""

    __value: int
    __child: Node | None

    __slots__ = ("__weakref__", "__value", "__child")

    def __new__(cls, value: int) -> Self:
        with Node._store.instance(cls, value) as self:
            if self is None:
                self = object.__new__(cls)
                self.__value = value
                self.__child = Node(value - 1) if value > 0 else None
                Node._store.register(self)
            return self

    @property
    def child(self) -> Node | None:
        """Child node."""
        return self.__child


class LabelledNode(Node):
    """Flyweight labelled node, whose superclass constructor builds a child."""

    __label: str

    __slots__ = ("__label",)

    def __new__(cls, value: int, label: str) -> Self:
        with Node._store.instance(cls, (value, label)) as self:
            if self is None:
                with Node._store.super():
                    self = Node.__new__(cls, value)
                self.__label = label
            return self

    @property
    def label(self) -> str:
        """Label."""
        return self.__label


class ColouredNode(LabelledNode):
    """Flyweight coloured node, two levels below the store's root class."""

    __colour: str

    __slots__ = ("__colour",)

    def __new__(cls, value: int, label: str, colour: str) -> Self:
        with Node._store.instance(cls, (value, label, colour)) as self:
            if self is None:
                with Node._store.super():
                    self = LabelledNode.__new__(cls, value, label)
                self.__colour = colour
            return self

    @property
    def colour(self) -> str:
        """Colour."""
        return self.__colour


class Peer:
    """Flyweight constructing a peer after registering itself."""

    _store: ClassVar[InstanceStore] = InstanceStore()
    """Instance store for peers."""

    __peer: Peer | None

    __slots__ = ("__weakref__", "__peer")

    def __new__(cls, key: int) -> Self:
        with Peer._store.instance(cls, key) as self:
            if self is None:
                self = object.__new__(cls)
                Peer._store.register(self)
                self.__peer = Peer(-key) if key > 0 else None
            return self

    @property
    def peer(self) -> Peer | None:
        """Peer instance."""
        return self.__peer


class Ratio:
    """Flyweight ratio returning a normalised instance from inside its context."""

    _store: ClassVar[InstanceStore] = InstanceStore()
    """Instance store for ratios."""

    __slots__ = ("__weakref__",)

    def __new__(cls, num: int, den: int) -> Self:
        with Ratio._store.instance(cls, (num, den)) as self:
            if self is None:
                g = gcd(num, den)
                if g != 1:
                    return cls(num // g, den // g)
                self = object.__new__(cls)
                Ratio._store.register(self)
            return self


class ForgetfulNamedFrac(Frac):
    """Subclass calling the superclass constructor without the super marker."""

    __slots__ = ()

    def __new__(cls, num: int, den: int, name: str) -> Self:
        with Frac._store.instance(cls, (num, den, name)) as self:
            if self is None:
                self = Frac.__new__(cls, num, den)
            return self


class Unmanaged:
    """Weak-referenceable class whose constructor does not use any store."""

    __slots__ = ("__weakref__",)


class UnmanagedChild(Unmanaged):
    """Subclass using the super marker around a constructor that ignores the store."""

    _store: ClassVar[InstanceStore] = InstanceStore()
    """Instance store for the subclass."""

    __slots__ = ()

    def __new__(cls, key: int) -> Self:
        with UnmanagedChild._store.instance(cls, key) as self:
            if self is None:
                with UnmanagedChild._store.super():
                    self = object.__new__(cls)
            return self


class Sibling:
    """Flyweight whose constructor builds same-class instances at a given stage."""

    _store: ClassVar[InstanceStore] = InstanceStore()
    """Instance store for siblings."""

    __peer: Sibling | None

    __slots__ = ("__weakref__", "__peer")

    def __new__(cls, key: int, stage: str = "") -> Self:
        if stage == "before-context":
            cls(key + 100)
        with Sibling._store.instance(cls, key) as self:
            if self is None:
                self = object.__new__(cls)
                self.__peer = cls(key + 100) if stage == "inside-context" else None
                Sibling._store.register(self)
            return self

    @property
    def peer(self) -> Sibling | None:
        """Peer instance."""
        return self.__peer


class StagedSibling(Sibling):
    """Subclass building same-class instances at a given stage of its super context."""

    __slots__ = ()

    def __new__(cls, key: int, stage: str = "") -> Self:
        with Sibling._store.instance(cls, (key, stage)) as self:
            if self is None:
                with Sibling._store.super():
                    if stage == "before-super":
                        cls(key + 100)
                    self = Sibling.__new__(cls, key, stage)
                    if stage == "after-super":
                        cls(key + 200)
            return self


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
    with pytest.raises(RuntimeError):
        with store.instance(Plain, 0):
            pass
    assert store.get(Plain, 0) is None
    with store.instance(Plain, 0) as self:
        assert self is None
        store.register(Plain())


def test_double_registration() -> None:
    store = InstanceStore()
    with pytest.raises(RuntimeError):
        with store.instance(Plain, 0):
            store.register(Plain())
            store.register(Plain())
    assert store.get(Plain, 0) is None


def test_wrong_type_registration() -> None:
    store = InstanceStore()
    with pytest.raises(TypeError):
        with store.instance(Plain, 0):
            store.register(object())
    assert store.get(Plain, 0) is None


def test_register_outside_building() -> None:
    store = InstanceStore()
    with pytest.raises(RuntimeError):
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


OPTIMISED_MODE_SCRIPT = """
from hashcons import InstanceStore
class A: pass
store = InstanceStore()
with store.instance(A, 0) as a:
    a = A()
    store.register(a)
print("ok" if store.get(A, 0) is a else "missing")
try:
    with store.instance(A, 1):
        store.register(object())
except TypeError:
    print("wrong type rejected")
try:
    with store.instance(A, 2):
        pass
except RuntimeError:
    print("missing registration rejected")
try:
    with store.instance(A, 3):
        store.register(A())
        store.register(A())
except RuntimeError:
    print("double registration rejected")
"""
"""Script exercising the store with assertions disabled."""


def test_optimised_mode() -> None:
    src = Path(__file__).parent.parent / "src"
    result = subprocess.run(
        [sys.executable, "-O", "-c", OPTIMISED_MODE_SCRIPT],
        capture_output=True,
        text=True,
        env=os.environ | {"PYTHONPATH": str(src)},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "ok",
        "wrong type rejected",
        "missing registration rejected",
        "double registration rejected",
    ]


def test_nested_construction_same_class() -> None:
    node = Node(2)
    assert node.child is Node(1)
    assert node.child is not None and node.child.child is Node(0)
    assert Node(0).child is None


def test_nested_construction_of_existing_instance() -> None:
    leaf = Node(10)
    assert Node(11).child is leaf


def test_nested_construction_inside_superclass_constructor() -> None:
    node = LabelledNode(3, "a")
    assert type(node) is LabelledNode
    assert node.label == "a"
    assert node.child is Node(2)
    assert node is LabelledNode(3, "a")
    assert Node._store.get(LabelledNode, 3) is None


def test_two_level_superclass_chain() -> None:
    node = ColouredNode(2, "b", "red")
    assert type(node) is ColouredNode
    assert (node.label, node.colour) == ("b", "red")
    assert node.child is Node(1)
    assert node is ColouredNode(2, "b", "red")
    assert Node._store.get(ColouredNode, (2, "b")) is None
    assert Node._store.get(ColouredNode, 2) is None


def test_nested_construction_after_registration() -> None:
    x = Peer(4)
    assert x.peer is Peer(-4)
    assert Peer(-4).peer is None


def test_returning_nested_instance_is_rejected() -> None:
    assert Ratio(1, 2) is Ratio(1, 2)
    with pytest.raises(RuntimeError, match="not registered"):
        Ratio(2, 4)
    assert Ratio._store.get(Ratio, (2, 4)) is None


def test_missing_super_marker() -> None:
    with pytest.raises(RuntimeError, match="not registered"):
        ForgetfulNamedFrac(1, 5, "x")
    assert Frac._store.get(ForgetfulNamedFrac, (1, 5, "x")) is None
    assert lock_is_free()


def test_super_with_unmanaged_superclass() -> None:
    with pytest.raises(RuntimeError, match="did not enter"):
        UnmanagedChild(0)
    assert lock_is_free()


def test_super_outside_build() -> None:
    store = InstanceStore()
    with pytest.raises(RuntimeError, match="must be entered"):
        with store.super():
            pass


def test_super_after_registration() -> None:
    store = InstanceStore()
    Plain = new_plain_class()
    with pytest.raises(RuntimeError, match="must be entered"):
        with store.instance(Plain, 0):
            store.register(Plain())
            with store.super():
                pass
    assert store.get(Plain, 0) is None


def test_nested_super() -> None:
    store = InstanceStore()
    Plain = new_plain_class()
    with pytest.raises(RuntimeError, match="can only be nested"):
        with store.instance(Plain, 0):
            with store.super():
                with store.super():
                    pass


@pytest.mark.parametrize("stage", ["before-super", "after-super", "before-context"])
def test_same_class_construction_within_super(stage: str) -> None:
    with pytest.raises(RuntimeError, match="constructed again"):
        StagedSibling(1, stage)
    assert Sibling._store.get(StagedSibling, (1, stage)) is None
    assert lock_is_free()


def test_same_class_construction_inside_superclass_context() -> None:
    x = StagedSibling(2, "inside-context")
    assert type(x) is StagedSibling
    assert x is StagedSibling(2, "inside-context")
    assert x.peer is StagedSibling(102)
