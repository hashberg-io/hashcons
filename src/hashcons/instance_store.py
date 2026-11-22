# SPDX-License-Identifier: LGPL-3.0-or-later

"""Instance stores for flyweight classes."""

# Part of HashCons: hash consing for flyweight classes
# Copyright (C) 2024 Hashberg Ltd

# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <https://www.gnu.org/licenses/>.

from collections.abc import Generator, Hashable
from contextlib import contextmanager
from enum import Enum, auto
from threading import RLock
from typing import ClassVar, Self, cast, final
from weakref import WeakValueDictionary


@final
class _SuperState(Enum):
    """State of a super context."""

    PENDING = auto()
    """Awaiting the superclass constructor's instance context."""

    JOINED = auto()
    """Inside the superclass constructor's instance context."""

    DONE = auto()
    """After the superclass constructor's instance context."""


@final
class InstanceStore:
    """Store of flyweight instances, indexed by class and instance key."""

    __lock: ClassVar[RLock] = RLock()
    """Lock shared by all instance stores."""

    __instances: WeakValueDictionary[tuple[type, Hashable], object]
    """Stored instances, indexed by class and instance key."""

    __build_classes: list[type]
    """Classes of the active builds, innermost last."""

    __build_instances: list[object | None]
    """Fresh instances registered by the active builds, innermost last."""

    __build_super_states: list[list[_SuperState]]
    """States of the super contexts of the active builds, innermost last."""

    __slots__ = (
        "__weakref__",
        "__instances",
        "__build_classes",
        "__build_instances",
        "__build_super_states",
    )

    def __new__(cls) -> Self:
        store = object.__new__(cls)
        store.__instances = WeakValueDictionary()
        store.__build_classes = []
        store.__build_instances = []
        store.__build_super_states = []
        return store

    def get[T](self, cls: type[T], key: Hashable) -> T | None:
        """Returns the instance with given class and key, if one exists."""
        return cast(T | None, self.__instances.get((cls, key)))

    @contextmanager
    def instance[T](self, cls: type[T], key: Hashable) -> Generator[T | None]:
        """Manages the creation of the instance with given class and key."""
        with InstanceStore.__lock:
            if self.__build_classes and self.__build_classes[-1] is cls:
                states = self.__build_super_states[-1]
                if states and states[-1] is _SuperState.PENDING:
                    states[-1] = _SuperState.JOINED
                    try:
                        yield None
                    finally:
                        states[-1] = _SuperState.DONE
                    return
                if states and states[-1] is _SuperState.DONE:
                    raise RuntimeError(
                        "The class being built cannot be constructed again within "
                        "a 'super' context."
                    )
            existing_instance = self.get(cls, key)
            if existing_instance is not None:
                yield existing_instance
                return
            self.__build_classes.append(cls)
            self.__build_instances.append(None)
            self.__build_super_states.append([])
            try:
                yield None
                instance = self.__build_instances[-1]
                if instance is None:
                    raise RuntimeError(
                        "Context manager signalled that no instance existed, "
                        "but a fresh instance was not registered."
                    )
                if not isinstance(instance, cls):
                    raise TypeError(
                        f"Instance registered is not of the expected type {cls!r}."
                    )
                self.__instances[(cls, key)] = instance
            finally:
                self.__build_classes.pop()
                self.__build_instances.pop()
                self.__build_super_states.pop()

    @contextmanager
    def super(self) -> Generator[None]:
        """Joins the next instance context for the class being built to its build."""
        with InstanceStore.__lock:
            if not self.__build_classes or self.__build_instances[-1] is not None:
                raise RuntimeError(
                    "Context manager 'super' must be entered while building an "
                    "instance, before it is registered."
                )
            states = self.__build_super_states[-1]
            if states and states[-1] is not _SuperState.JOINED:
                raise RuntimeError(
                    "Context manager 'super' can only be nested within a "
                    "superclass constructor."
                )
            states.append(_SuperState.PENDING)
            try:
                yield
                if states[-1] is _SuperState.PENDING:
                    raise RuntimeError(
                        "Superclass constructor did not enter the instance context "
                        "for the class being built."
                    )
            finally:
                states.pop()

    def register(self, instance: object) -> None:
        """Registers the fresh instance for the innermost active build."""
        if not self.__build_instances:
            raise RuntimeError(
                "Method 'register' must be called while building an instance."
            )
        if self.__build_instances[-1] is not None:
            raise RuntimeError(
                "Method 'register' can be called once per instance built."
            )
        self.__build_instances[-1] = instance
