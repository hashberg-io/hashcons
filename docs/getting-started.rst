Getting Started
===============

A simple implementation of flyweight instance management using hash consing.
You can install the latest release from `PyPI <https://pypi.org/project/hashcons/>`_:

.. code-block:: console

    $ pip install -U hashcons

The library requires Python 3.14 or later.

Flyweight classes
-----------------

The :class:`~hashcons.instance_store.InstanceStore` class implements flyweight factories.
Instances are held in a :class:`~weakref.WeakValueDictionary`, indexed by their class and a user-provided instance key, so flyweight classes must be weak-referenceable: slotted classes must include ``"__weakref__"`` in their ``__slots__``.

The :meth:`~hashcons.instance_store.InstanceStore.instance` context manager is entered by the flyweight class constructor.
It yields the existing instance with given class and key, or :obj:`None` if no such instance exists.
In the latter case, the constructor creates a fresh instance and passes it to :meth:`~hashcons.instance_store.InstanceStore.register`, exactly once; the instance is stored when the context exits.
If the context exits with an exception, nothing is stored, so it is safe to raise exceptions during construction.
Constructors are implemented with `__new__ <https://docs.python.org/3/reference/datamodel.html#object.__new__>`_ rather than `__init__ <https://docs.python.org/3/reference/datamodel.html#object.__init__>`_, so that existing instances can be returned.

.. code-block:: python

    from typing import ClassVar, Literal, Self
    from hashcons import InstanceStore

    class MyFrac:
        """ A flyweight class. """

        _store: ClassVar[InstanceStore] = InstanceStore()

        __num: int
        __den: int

        __slots__ = ("__weakref__", "__num", "__den")

        def __new__(cls, num: int, den: int) -> Self:
            """ Flyweight class constructor. """
            instance_key = (num, den) # instance key derived from constructor args
            with MyFrac._store.instance(cls, instance_key) as self:
                if self is None: # if no instance with given key exists
                    # 1. Validate constructor arguments:
                    if den == 0:
                        raise ZeroDivisionError()
                    # 2. Create the new instance:
                    self = object.__new__(cls)
                    # 3. Set instance attributes:
                    self.__num = num
                    self.__den = den
                    # 4. Register the instance in the store:
                    MyFrac._store.register(self)
                return self

        def __getnewargs__(self) -> tuple[int, int]:
            """ Optional support for pickling. """
            return (self.__num, self.__den)

        def __getstate__(self) -> Literal[None]:
            """ Optional support for pickling. """
            return None

        ... # <- class body here

Subclasses
----------

Instances of different subclasses are stored separately, under the subclass passed to :meth:`~hashcons.instance_store.InstanceStore.instance`.
A subclass constructor enters the :meth:`~hashcons.instance_store.InstanceStore.instance` context of the superclass's store with its own instance key and, if no instance exists, calls the superclass constructor within the store's :meth:`~hashcons.instance_store.InstanceStore.super` context.
The superclass constructor's :meth:`~hashcons.instance_store.InstanceStore.instance` context then joins the build of the subclass instance: it yields :obj:`None`, and the superclass constructor creates and registers the instance.
The subclass constructor must not call :meth:`~hashcons.instance_store.InstanceStore.register` itself.
Validation can be performed both before and after the superclass constructor call: if the subclass context exits with an exception, the instance is not stored.

.. code-block:: python

    class MyNamedFrac(MyFrac):

        __name: str

        __slots__ = ("__name",)

        def __new__(cls, num: int, den: int, name: str) -> Self:
            with MyFrac._store.instance(cls, (num, den, name)) as self:
                if self is None:
                    with MyFrac._store.super():
                        self = MyFrac.__new__(cls, num, den)
                    self.__name = name
                return self

A :meth:`~hashcons.instance_store.InstanceStore.super` context accepts exactly one :meth:`~hashcons.instance_store.InstanceStore.instance` context for the class being built, namely that of the superclass constructor.
Constructing another instance of the class being built within a :meth:`~hashcons.instance_store.InstanceStore.super` context, other than from within the superclass constructor's own :meth:`~hashcons.instance_store.InstanceStore.instance` context, raises :exc:`RuntimeError`.

Nested construction
-------------------

Outside of :meth:`~hashcons.instance_store.InstanceStore.super` contexts, every :meth:`~hashcons.instance_store.InstanceStore.instance` context runs its own lookup and build, so constructors can construct other instances managed by the same store, including instances of their own class, at any point.

.. code-block:: python

    class Node:

        _store: ClassVar[InstanceStore] = InstanceStore()

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

A constructor which returns an instance other than the one it registers, e.g. a normalised instance constructed within its context, fails with :exc:`RuntimeError`, because its own build ends with no registered instance.
Normalisation of constructor arguments is performed before the :meth:`~hashcons.instance_store.InstanceStore.instance` context is entered, so that the instance key is the normalised one.

Pickling
--------

If :mod:`pickle` support is desirable, flyweight classes should implement `__getnewargs__ <https://docs.python.org/3/library/pickle.html#object.__getnewargs__>`_, or `__getnewargs_ex__ <https://docs.python.org/3/library/pickle.html#object.__getnewargs_ex__>`_ if the constructor takes keyword-only arguments, so that unpickling goes through the constructor and returns the stored instance.
They should also implement `__getstate__ <https://docs.python.org/3/library/pickle.html#object.__getstate__>`_ to return :obj:`None`, so that the default `__setstate__ <https://docs.python.org/3/library/pickle.html#object.__setstate__>`_ does not overwrite the attributes of the shared instance (cf. `PEP 307 <https://peps.python.org/pep-0307/#case-3-pickling-new-style-class-instances-using-protocol-2>`_).

Thread safety and validation
----------------------------

All instance stores share a single re-entrant lock, held for the duration of each :meth:`~hashcons.instance_store.InstanceStore.instance` context, so construction is thread-safe.
Misuse of the store raises an exception, also when running with the `-O flag <https://docs.python.org/3/using/cmdline.html#cmdoption-O>`_: :exc:`TypeError` for registering an instance of the wrong class, and :exc:`RuntimeError` for failing to register a fresh instance, registering twice, registering outside a build, and misuse of :meth:`~hashcons.instance_store.InstanceStore.super` contexts.

Upgrading from 0.1
------------------

- Subclass constructors wrap their call to the superclass constructor in the store's :meth:`~hashcons.instance_store.InstanceStore.super` context; without it, construction fails with :exc:`RuntimeError`.
- Nested :meth:`~hashcons.instance_store.InstanceStore.instance` contexts outside of :meth:`~hashcons.instance_store.InstanceStore.super` contexts are independent builds, rather than being joined to the enclosing build.
- Misuse raises :exc:`RuntimeError` or :exc:`TypeError` instead of :exc:`AssertionError`, and calling :meth:`~hashcons.instance_store.InstanceStore.register` outside a build raises instead of being ignored.
- The library requires Python 3.14 or later, and no longer depends on ``typing_extensions``.

GitHub repo: https://github.com/hashberg-io/hashcons
