"""
The :class:`InstanceStore` class provides a mechanism to manage the creation
of instances for flyweight classes, based on class and a unique instance key.
"""

# Part of HashCons: hash consing for flyweight classes
# Copyright (C) 2024 Hashberg Ltd

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301
# USA

from __future__ import annotations

from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from threading import RLock
from typing import Any, ClassVar, Type, TypeVar, cast
from weakref import WeakValueDictionary
from typing_extensions import Self

T_co = TypeVar("T_co", covariant=True)
"""
Covariant type variable for arbitrary values.
"""

class InstanceStore:
    """

    An instance store, which can be used to manage the process of instance
    creation for instances of flyweight classes.
    Instances are stored internally in a :class:`~weakref.WeakValueDictionary`,
    indexed by their class and a user-provided instance key.

    The :meth:`instance` method implements a context manager for use within the
    flyweight class constructor, within which managed instance creation can be
    performed.

    The :meth:`register` method must be called within the :meth:`instance`
    context when a new instance is created, as opposed to when an existing
    instance is used.

    .. code-block:: python

        class MyClass:

            __store: ClassVar[InstanceStore] = InstanceStore()

            def __new__(cls, ...) -> Self:
                #       args ^^^
                key = ...# derive instance key from constructor args
                with MyClass.__store.instance(cls, key) as self:
                    if self is None: # if no instance with given key exists
                        self = super().__new__(cls)
                        ... # <- set instance attributes here
                        MyClass.__store.register(self)
                    return self

            ... # <- class body here

    In order to customise the instance creation process, it will typically be
    necessary to implement flyweight class constructors using
    `__new__ <https://docs.python.org/3/reference/datamodel.html#object.__new__>`_,
    rather than
    `__init__ <https://docs.python.org/3/reference/datamodel.html#object.__init__>`_.

    If :mod:`pickle` support is desirable, flyweight classes should implement either the
    `__getnewargs__ <https://docs.python.org/3/library/pickle.html#object.__getnewargs__>`_
    method or the
    `__getnewargs_ex__ <https://docs.python.org/3/library/pickle.html#object.__getnewargs_ex__>`_
    method, depending on whether the constructor takes keyword-only arguments.
    Classes should also implement
    `__getstate__ <https://docs.python.org/3/library/pickle.html#object.__getstate__>`_
    to return :obj:`None`, in order to prevent the default
    `__setstate__ <https://docs.python.org/3/library/pickle.html#object.__setstate__>`_
    being called by the pickling process (cf.
    `PEP 307 <https://peps.python.org/pep-0307/#case-3-pickling-new-style-class-instances-using-protocol-2>`_).

    .. code-block:: python

        def __getnewargs__(self) -> tuple[...]:
            #      __new__ arg types here ^^^
            return (...)
            #       ^^^ args to __new__ here

        def __getstate__(self) -> Literal[None]:
            return None

    """
    __lock: ClassVar[RLock] = RLock()

    __instances: WeakValueDictionary[tuple[Type[Any], Hashable], Any]
    __building_instance: bool
    __instance_to_register: Any | None

    __slots__ = (
        "__weakref__",
        "__instances",
        "__building_instance",
        "__instance_to_register",
    )

    def __new__(cls) -> Self:
        store = super().__new__(cls)
        store.__instances = WeakValueDictionary()
        store.__building_instance = False
        store.__instance_to_register = None
        return store

    def get(self, cls: Type[T_co], key: Hashable) -> T_co | None:
        """
        Returns the instance with given class and instance key,
        or :obj:`None` if no such instance exists.
        """
        instance = self.__instances.get((cls, key))
        return None if instance is None else cast(T_co, instance)

    @contextmanager
    def instance(self, cls: Type[T_co], key: Hashable) -> Iterator[T_co | None]:
        """
        Context manager to manage the creation of an instance of the given
        class, uniquely identified by the given key.

        If an instance with the given key already exists, it is yielded.
        Otherwise, the following procedure is followed:

        1. The instance building process is started.
        2. The value :obj:`None` is yielded, to signal to the context
           that no instance with the given key exists yet.
        3. Once control is returned to the context manager, it checks
           that an instance was registered using the :meth`register` method,
           and that it is actually an instance of the given class.
        4. If the checks from Step 3 are successful, the instance is stored
           using the given class and key.
        5. Regardless of whether the checks from Step 3 are successful, the
           instance building process is terminated.

        It is possible for the same instance building process to be shared
        by multiple contexts, e.g. when using the same store for instances
        of a class and its subclasses.
        If the context manager is invoked multiple times, it yields the
        same value across all calls, but the instance process is started
        at most once by the outermost call, and fully handled by it.
        This makes it possible to create subclasses of a flyweight class.

        If the instance building process is started, the
        :meth:`~InstanceStore.register` method must be called exactly once.

        Failure to comply with the above requirements results in an
        :exc:`AssertionError` being raised.
        For the sake of performance, all validation is done by assertions,
        so it is removed when compiling with the
        `-O flag <https://docs.python.org/3/using/cmdline.html#cmdoption-O>`_.

        """
        InstanceStore.__lock.acquire()
        assert self.__instance_to_register is None, (
            "Context manager 'instance' cannot be called after a managed "
            "instance has already been created."
        )
        # Instance is already been built within another context, defer to it:
        if self.__building_instance:
            yield None
            InstanceStore.__lock.release()
            return
        # If an instance with the given key already exists, return it:
        existing_instance = cast(T_co, self.__instances.get((cls, key)))
        if existing_instance is not None:
            yield existing_instance
            InstanceStore.__lock.release()
            return
        # Start the instance building process:
        self.__building_instance = True
        try:
            # Signal that no instance exists:
            yield None
            # Ensure that an instance was actually constructed:
            assert (instance := self.__instance_to_register) is not None, (
                "Context manager signalled that no instance existed, "
                "but a fresh instance was not constructed."
            )
            # Ensure that the instance is of the correct type:
            assert isinstance(
                instance, cls
            ), f"Instance constructed is not of the expected type {cls!r}."
            # If we get here, construction was successful and we must register:
            self.__instances[(cls, key)] = instance
        except BaseException as e:
            # Unregister the instance if an error occurs after registration:
            if (cls, key) in self.__instances:
                del self.__instances[(cls, key)]
            raise e
        finally:
            # Terminate the instance building process:
            self.__building_instance = False
            self.__instance_to_register = None
            InstanceStore.__lock.release()

    def register(self, instance: Any) -> None:
        """
        If the instance building process is active, the given instance
        is registered as the fresh instance being built.
        Otherwise, the instance is ignored.

        If the instance building process is started by the :meth:`instance`
        method, the :meth:`register` method must be called exactly once,
        otherwise an :exc:`AssertionError` will be raised by the
        :meth:`instance` method at the moment when the context is exited.
        """
        if self.__building_instance:
            assert (
                self.__instance_to_register is None
            ), "Method 'register' can be called once per instance built."
            self.__instance_to_register = instance
