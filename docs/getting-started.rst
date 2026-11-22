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
A subclass constructor enters the context of the superclass's store with its own instance key and, if no instance exists, calls the superclass constructor.
The superclass constructor's context recognises that an instance is already being built, yields :obj:`None`, and the superclass constructor creates and registers the instance.
The subclass constructor must not call :meth:`~hashcons.instance_store.InstanceStore.register` itself.
Validation can be performed both before and after the superclass constructor call: if the subclass context exits with an exception, the instance is not stored.

.. code-block:: python

    class MyNamedFrac(MyFrac):

        __name: str

        __slots__ = ("__name",)

        def __new__(cls, num: int, den: int, name: str) -> Self:
            with MyFrac._store.instance(cls, (num, den, name)) as self:
                if self is None:
                    self = MyFrac.__new__(cls, num, den)
                    self.__name = name
                return self

While an instance is being built, the store treats every nested :meth:`~hashcons.instance_store.InstanceStore.instance` call as part of the same building process.
A constructor must therefore not construct other instances managed by the same store from inside its context: any such instances must be constructed before the context is entered.

Pickling
--------

If :mod:`pickle` support is desirable, flyweight classes should implement `__getnewargs__ <https://docs.python.org/3/library/pickle.html#object.__getnewargs__>`_, or `__getnewargs_ex__ <https://docs.python.org/3/library/pickle.html#object.__getnewargs_ex__>`_ if the constructor takes keyword-only arguments, so that unpickling goes through the constructor and returns the stored instance.
They should also implement `__getstate__ <https://docs.python.org/3/library/pickle.html#object.__getstate__>`_ to return :obj:`None`, so that the default `__setstate__ <https://docs.python.org/3/library/pickle.html#object.__setstate__>`_ does not overwrite the attributes of the shared instance (cf. `PEP 307 <https://peps.python.org/pep-0307/#case-3-pickling-new-style-class-instances-using-protocol-2>`_).

Thread safety and validation
----------------------------

All instance stores share a single re-entrant lock, held for the duration of each :meth:`~hashcons.instance_store.InstanceStore.instance` context, so construction is thread-safe.
Misuse of the store, such as failing to register a fresh instance, registering twice, or registering an instance of the wrong class, is detected by assertions, which are removed when running with the `-O flag <https://docs.python.org/3/using/cmdline.html#cmdoption-O>`_.

GitHub repo: https://github.com/hashberg-io/hashcons
