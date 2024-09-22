flyweight: hash consing and instance management
===============================================

.. image:: https://img.shields.io/badge/python-3.12+-green.svg
    :target: https://docs.python.org/3.12/
    :alt: Python versions

.. image:: https://img.shields.io/pypi/v/flyweight.svg
    :target: https://pypi.python.org/pypi/flyweight/
    :alt: PyPI version

.. image:: https://img.shields.io/pypi/status/flyweight.svg
    :target: https://pypi.python.org/pypi/flyweight/
    :alt: PyPI status

.. image:: http://www.mypy-lang.org/static/mypy_badge.svg
    :target: https://github.com/python/mypy
    :alt: Checked with Mypy

.. image:: https://readthedocs.org/projects/flyweight/badge/?version=latest
    :target: https://flyweight.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

.. image:: https://github.com/hashberg-io/flyweight/actions/workflows/python-pytest.yml/badge.svg
    :target: https://github.com/hashberg-io/flyweight/actions/workflows/python-pytest.yml
    :alt: Python package status

.. image:: https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square
    :target: https://github.com/RichardLitt/standard-readme
    :alt: standard-readme compliant


A simple implementation of hash consing and flyweight instance management.

.. contents::

Install
-------

You can install the latest release from `PyPI <https://pypi.org/project/flyweight/>`_:

.. code-block:: console

    $ pip install -U flyweight

Usage
-----

The `InstanceStore` class can be used to create instance stores, i.e. flyweight factories.
A common pattern is to use an instance store for each flyweight class, stored as a protected/private class attribute:

.. code-block:: python

    from flyweight import InstanceStore
    from typing import ClassVar
    from typing_extensions import Self

    class MyFrac:

        _store: ClassVar[InstanceStore] = InstanceStore()

        ... # <- class body here

In the constructor for the class, the store is queried by calling the `instance` method with:

- the specific subclass `cls`, because instances of different subclasses are stored separately;
- an `instance_key`, derived from the constructor arguments and uniquely identifying a flyweight instance.

The store returns the instance of the class for given instance key, or `None` if none exists.

.. code-block:: python

    class MyFrac:

        _store: ClassVar[InstanceStore] = InstanceStore()

        def __new__(cls, num: int, den: int) -> Self:
            instance_key = (num, den) # instance key derived from constructor args
            with MyFrac._store.instance(cls, instance_key) as self:
                if self is None:
                    ... # <- instance construction logic here
                return self

        ... # <- class body here

If no instance exists, one should be created, usually via a call to the super constructor.
When a new instance is created, its attributes should be validated and set.
The instance is then registered by passing it to the `register` method of the store.

.. code-block:: python

    class MyFrac:

        _store: ClassVar[InstanceStore] = InstanceStore()

        __num: int
        __den: int

        def __new__(cls, num: int, den: int) -> Self:
            instance_key = (num, den)
            with MyFrac._store.instance(cls, instance_key) as self:
                if self is None: # if no instance with given key exists
                    # 1. Validate constructor arguments:
                    if den == 0:
                        raise ZeroDivisionError()
                    # 2. Create the new instance:
                    self = super().__new__(cls)
                    # 3. Set instance attributes:
                    self.__num = num
                    self.__den = den
                    # 4. Register the instance in the store:
                    MyFrac._store.register(self)
                return self

        ... # <- class body here

Note that it is safe to raise exceptions as part of the instance construction process,
as the `instance` context manager will take care of performing the necessary cleanup.
The code snippet below exemplifies validation, new instance creation, and instance reuse.

.. code-block:: python

    try:
        inf = MyFrac(1, 0) # does not pass constructor validation
    except ZeroDivisionError:
        pass

    x = MyFrac(10, 3)  # new instance with key=(10, 3) created
    x1 = MyFrac(10, 3) # instance with key=(10, 3) exists

    assert x is x1 # a unique instance exists for each (cls, instance_key) pair

Because subclasses are stored separately, flyweight classes support inheritance.
Subclasses should use the `instance` context manager for the flyweight superclass's store, which will return an instance of the subclass for the given instance key, if one exists.
If a new instance of the subclass must be created, the subclass can do so by making a call to the superclass constructor:

1. The `instance` context is entered in the superclass constructor:
   it recognises that it is entered within another `instance` context for the same store,
 it presumes that this is because the superclass constructor was called by a subclass, and it returns `None` to signal to the superclass constructor that a new instance is needed.
2. The superclass constructor creates a new instance, sets its attributes, registers it,
 and returns it to the subclass constructor.
3. The subclass constructor takes the instance from the superclass constructor, sets its attribtues, and returns it.

Note that the subclass's constructor should not call `register` when creating a new instance:
by the time the superclass constructor returns, the new instance has already been registered.
The code snippet below exemplifies subclass usage.

.. code-block:: python

    class MyNamedFrac(MyFrac):

        __name: str

        def __new__(cls, num: int, den: int, name: str) -> Self:
            key = (num, den, name)
            with MyFrac._store.instance(cls, key) as self:
                if self is None:
                    self = super().__new__(cls, num, den)
                    self.__name = name
                return self


    y = MyNamedFrac(10, 3, "y")  # new instance with key=(10, 3, 'y') created
    y1 = MyNamedFrac(10, 3, "y") # instance with key=(10, 3, 'y') returned
    z = MyNamedFrac(10, 3, "z")  # new instance with key=(10, 3, 'z') created

    assert y is not x
    assert y is y1
    assert y is not z

Subclasses can perform their validation both before and after the superclass constructor call.
The ability to perform validation after is important in cases where subclass validation depends on superclass validation, e.g. because it uses properties/methods of the partially initialised instance.
There is no issue with errors being raised after the superclass constructor has returned:
the new instance as been registered by the superclass constructor, but it will be unregistered by the subclass `instance` context if it is exited in error.

API
---

The full API documentation is available at https://flyweight.readthedocs.io/

License
-------

`LGPL © Hashberg Ltd. <LICENSE>`_
