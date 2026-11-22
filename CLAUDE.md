# hashcons

Hash consing for flyweight classes: a single public class, `InstanceStore` in `src/hashcons/instance_store.py`, re-exported from `hashcons`.
Published on PyPI and Read the Docs; licensed LGPL-3.0-or-later.

## Design

- Instances live in a `WeakValueDictionary` keyed by `(cls, key)`, so flyweight classes must be weak-referenceable.
- One class-level `RLock` is shared by all stores, held for the whole `instance` context; a single global lock avoids lock-ordering deadlocks between stores.
- Each store keeps a stack of active builds (class, registered instance, super-context states); every `instance` call outside a `super` context does its own lookup and build, so nested construction from the same store works anywhere.
- Subclass constructors mark the superclass constructor call with `with store.super():`; the next `instance` call for the class being built joins the enclosing build instead of starting one.
  A `super` context accepts exactly one such call (states pending, joined, done); a further same-class `instance` call once done raises, which closes the ambiguous window between entering `super` and the superclass's `instance` call.
  A call form (`store.super(ctor, cls, ...)`), implicit joining and a two-phase key/initialiser protocol were considered and rejected.
- A constructor returning a nested instance without registering one fails ("not registered"); explicitly registering an already-stored instance under a second key is accepted but deliberately undocumented.
- How stores are attached to class hierarchies is the user's business: the library does not check that a class is managed by a single store.
- Misuse raises `RuntimeError`/`TypeError`, never `assert`, and `register` outside a build raises: checks critical to the store's logic must survive `-O` (`test_optimised_mode`).
- The lock is acquired via `with` inside the generator, so it is released on every exit path, including exceptions thrown into the context.

## Conventions

- Python 3.14 and 3.15 supported (3.14 also because Read the Docs has no 3.15 yet); PEP 695 generics, `typing.Self`, no runtime dependencies.
- Docstrings are one sentence; narrative documentation lives in `docs/getting-started.rst` and `README.md`.
- Docs tooling (`autodoc_typehints.py`, `docs/conf.py`, `docs/make-api.py`) is copied from `hashberg-io/sphinx-docscripts` (`docs/conf.py` imports the package from `pkg_path` in `docs/make-api.json`, i.e. `../src`); Read the Docs builds on Python 3.14, and CI builds the docs on 3.14 with warnings as errors.
  Rebuild with `python make-api.py`, then `sphinx-build -M html . _build`, from `docs/`.

## Checks

- `black --check src tests`, `mypy src tests`, `pytest` (all configured in `pyproject.toml`, also run in CI).
