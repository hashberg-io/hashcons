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

    __building_instance: bool
    """Whether an instance building process is active."""

    __instance_to_register: object | None
    """Fresh instance registered by the active building process, if any."""

    __slots__ = (
        "__weakref__",
        "__instances",
        "__building_instance",
        "__instance_to_register",
    )

    def __new__(cls) -> Self:
        store = object.__new__(cls)
        store.__instances = WeakValueDictionary()
        store.__building_instance = False
        store.__instance_to_register = None
        return store

    def get[T](self, cls: type[T], key: Hashable) -> T | None:
        """Returns the instance with given class and key, if one exists."""
        return cast(T | None, self.__instances.get((cls, key)))

    @contextmanager
    def instance[T](self, cls: type[T], key: Hashable) -> Generator[T | None]:
        """Manages the creation of the instance with given class and key."""
        with InstanceStore.__lock:
            if self.__instance_to_register is not None:
                raise RuntimeError(
                    "Context manager 'instance' cannot be called after a managed "
                    "instance has already been created."
                )
            if self.__building_instance:
                yield None
                return
            existing_instance = self.get(cls, key)
            if existing_instance is not None:
                yield existing_instance
                return
            self.__building_instance = True
            try:
                yield None
                instance = self.__instance_to_register
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
                self.__building_instance = False
                self.__instance_to_register = None

    def register(self, instance: object) -> None:
        """Registers the fresh instance for the active building process."""
        if self.__building_instance:
            if self.__instance_to_register is not None:
                raise RuntimeError(
                    "Method 'register' can be called once per instance built."
                )
            self.__instance_to_register = instance
