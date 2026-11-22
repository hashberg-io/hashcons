# hashcons

Hash consing for flyweight classes: a single public class, `InstanceStore` in `src/hashcons/instance_store.py`, re-exported from `hashcons`.
Published on PyPI and Read the Docs; licensed LGPL-2.1-or-later (kept as-is, not the house default).

## Design

- Instances live in a `WeakValueDictionary` keyed by `(cls, key)`, so flyweight classes must be weak-referenceable.
- One class-level `RLock` is shared by all stores, held for the whole `instance` context; a single global lock avoids lock-ordering deadlocks between stores.
- While a store is building an instance, every nested `instance` call on that store defers to the outer one (yields `None`); this is what lets subclass constructors call superclass constructors.
  Consequence: constructing a different instance of the same store inside a constructor's context is unsupported (documented limitation, no runtime detection beyond the double-`register` assertion).
- Misuse is detected by assertions only (stripped under `-O`), by design for performance; the code must still behave sensibly under `-O` (`test_optimised_mode`).
- The lock is acquired via `with` inside the generator, so it is released on every exit path, including exceptions thrown into the context.

## Conventions

- Python 3.15 only; PEP 695 generics, `typing.Self`, no runtime dependencies.
- Docstrings are one sentence; narrative documentation lives in `docs/getting-started.rst` and `README.md`.
- Docs tooling (`autodoc_typehints.py`, `docs/conf.py`, `docs/make-api.py`) is copied from `hashberg-io/sphinx-docscripts`; it does not resolve PEP 695 function type parameters, so `T` is listed in `skip_missing_references`.
  Rebuild with `python make-api.py`, then `sphinx-build -M html . _build`, from `docs/`.

## Checks

- `black --check src tests`, `mypy src tests`, `pytest` (all configured in `pyproject.toml`, also run in CI).
