"""Phase 0 smoke test: every stage module imports."""

import importlib

import pytest

STAGE_MODULES = [
    "soa.triage",
    "soa.locate",
    "soa.extract",
    "soa.footnotes",
    "soa.stitch",
    "soa.schema",
    "soa.pipeline",
]


@pytest.mark.parametrize("module", STAGE_MODULES)
def test_stage_module_imports(module):
    importlib.import_module(module)
