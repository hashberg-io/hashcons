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
from threading import RLock
from typing import ClassVar, Self, cast, final
from weakref import WeakValueDictionary


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

    __build_super_pending: list[bool]
    """Whether each active build awaits a superclass constructor, innermost last."""

    __slots__ = (
        "__weakref__",
        "__instances",
        "__build_classes",
        "__build_instances",
        "__build_super_pending",
    )

    def __new__(cls) -> Self:
        store = object.__new__(cls)
        store.__instances = WeakValueDictionary()
        store.__build_classes = []
        store.__build_instances = []
        store.__build_super_pending = []
        return store

    def get[T](self, cls: type[T], key: Hashable) -> T | None:
        """Returns the instance with given class and key, if one exists."""
        return cast(T | None, self.__instances.get((cls, key)))

    @contextmanager
    def instance[T](self, cls: type[T], key: Hashable) -> Generator[T | None]:
        """Manages the creation of the instance with given class and key."""
        with InstanceStore.__lock:
            if (
                self.__build_super_pending
                and self.__build_super_pending[-1]
                and self.__build_classes[-1] is cls
            ):
                self.__build_super_pending[-1] = False
                yield None
                return
            existing_instance = self.get(cls, key)
            if existing_instance is not None:
                yield existing_instance
                return
            self.__build_classes.append(cls)
            self.__build_instances.append(None)
            self.__build_super_pending.append(False)
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
                self.__build_super_pending.pop()

    @contextmanager
    def super(self) -> Generator[None]:
        """Joins the next instance context for the class being built to its build."""
        with InstanceStore.__lock:
            if not self.__build_classes or self.__build_instances[-1] is not None:
                raise RuntimeError(
                    "Context manager 'super' must be entered while building an "
                    "instance, before it is registered."
                )
            if self.__build_super_pending[-1]:
                raise RuntimeError("Context manager 'super' cannot be nested.")
            depth = len(self.__build_classes)
            self.__build_super_pending[-1] = True
            try:
                yield
                if self.__build_super_pending[depth - 1]:
                    raise RuntimeError(
                        "Superclass constructor did not enter the instance context "
                        "for the class being built."
                    )
            finally:
                self.__build_super_pending[depth - 1] = False

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
