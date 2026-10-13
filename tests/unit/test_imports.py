"""Import smoke: every name core exports must resolve, and the factory must import."""
import pytest

import core


def test_all_core_exports_resolve_lazily_map():
    # The lazy map and __all__ must agree (a missing entry only fails at pipeline start).
    assert set(core.__all__) == set(core._modules)


def test_factory_imports():
    pytest.importorskip("torch")
    pytest.importorskip("ultralytics")
    from core.app import factory
    assert callable(factory.build_pipeline)
