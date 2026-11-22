# hashcons

[![Python versions](https://img.shields.io/badge/python-3.14+-green.svg)](https://docs.python.org/3.14/)
[![PyPI version](https://img.shields.io/pypi/v/hashcons.svg)](https://pypi.python.org/pypi/hashcons/)
[![PyPI status](https://img.shields.io/pypi/status/hashcons.svg)](https://pypi.python.org/pypi/hashcons/)
[![Checked with Mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](https://github.com/python/mypy)
[![Documentation Status](https://img.shields.io/readthedocs/hashcons/latest)](https://hashcons.readthedocs.io/en/latest/)
[![Python package status](https://github.com/hashberg-io/hashcons/actions/workflows/python.yml/badge.svg)](https://github.com/hashberg-io/hashcons/actions/workflows/python.yml)

A simple implementation of flyweight instance management using hash consing: an `InstanceStore` guarantees that a flyweight class has at most one live instance for each instance key, holding instances weakly and supporting subclassing, pickling and concurrent construction.

## Install

Install the latest release from [PyPI](https://pypi.org/project/hashcons/):

```console
$ pip install --upgrade hashcons
```

The library requires Python 3.14 or later.

## Usage

A flyweight class keeps an instance store as a private class attribute.
Its constructor derives an instance key from its arguments and enters the store's `instance` context, which yields the existing instance for that key, or `None` if there is none.
In the latter case, the constructor validates its arguments, creates a fresh instance, sets its attributes and registers it with the store.
Exceptions raised during construction are safe: nothing is stored if the context exits with an error.
Instances are held weakly, so slotted flyweight classes must include `"__weakref__"` in their slots.

```python
from typing import ClassVar, Self
from hashcons import InstanceStore

class MyFrac:

    _store: ClassVar[InstanceStore] = InstanceStore()

    __num: int
    __den: int

    __slots__ = ("__weakref__", "__num", "__den")

    def __new__(cls, num: int, den: int) -> Self:
        with MyFrac._store.instance(cls, (num, den)) as self:
            if self is None:
                if den == 0:
                    raise ZeroDivisionError()
                self = object.__new__(cls)
                self.__num = num
                self.__den = den
                MyFrac._store.register(self)
            return self

x = MyFrac(10, 3)
assert x is MyFrac(10, 3)
assert x is not MyFrac(3, 10)
```

Instances of different subclasses are stored separately.
A subclass constructor enters the superclass store's `instance` context with its own key and, if no instance exists, calls the superclass constructor within the store's `super` context: the superclass constructor then creates and registers the instance, and the subclass must not call `register` itself.
Validation can happen both before and after the superclass constructor call.

```python
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

y = MyNamedFrac(10, 3, "y")
assert y is not x
assert y is MyNamedFrac(10, 3, "y")
assert y is not MyNamedFrac(10, 3, "z")
```

Constructors can construct other instances managed by the same store at any point, including instances of their own class, except within a `super` context.
Nested construction, pickling support, thread safety and validation are covered in the [getting-started guide](https://hashcons.readthedocs.io/en/latest/getting-started.html).

## API

The full API documentation is available at [hashcons.readthedocs.io](https://hashcons.readthedocs.io/).

## Structure

- `src/hashcons/` — the package source; `instance_store.py` defines `InstanceStore`.
- `tests/` — the pytest suite.
- `docs/` — Sphinx documentation sources, built with `autodoc_typehints.py` (see [sphinx-docscripts](https://github.com/hashberg-io/sphinx-docscripts)).
- `pypi-upload.py` — builds the distribution and uploads it to PyPI.

## License

[LGPL-3.0-or-later](LICENSE) © Hashberg Ltd.
