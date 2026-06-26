"""Smoke test: the whole library imports without heavy ML deps (M0 acceptance)."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import sutradhar

# Real-provider modules lazily import heavy deps only inside start(); importing
# the module itself must always succeed.
ALL_MODULES = [
    name for _, name, _ in pkgutil.walk_packages(sutradhar.__path__, prefix="sutradhar.")
]


@pytest.mark.parametrize("module", ALL_MODULES)
def test_module_imports(module: str) -> None:
    importlib.import_module(module)


def test_version_present() -> None:
    assert sutradhar.__version__
    assert isinstance(sutradhar.__version__, str)
