"""Gmsh session lifecycle regressions; no native Gmsh install required."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from forceforge.solid3d import import_step, make_box


class _MockMeshAPI:
    def generate(self, dim):
        assert dim == 3

    def getNodes(self):
        return np.array([11, 17, 23, 42]), np.array([
            0, 0, 0,
            0.1, 0, 0,
            0, 0.02, 0,
            0, 0, 0.02,
        ]), np.array([])

    def getElements(self, dim):
        assert dim == 3
        return [4], [np.array([1])], [np.array([11, 17, 23, 42])]


class _MockModelAPI:
    def __init__(self, existing=False):
        self.names = ["host"] if existing else []
        self.current = "host" if existing else ""
        self.mesh = _MockMeshAPI()
        self.occ = SimpleNamespace(
            addBox=lambda *args: 1,
            importShapes=lambda path: [(3, 1)],
            synchronize=lambda: None,
        )
        self.fail_volume = False

    def getCurrent(self):
        return self.current

    def add(self, name):
        assert name not in self.names
        self.names.append(name)
        self.current = name

    def getEntities(self, dimension):
        return [] if self.fail_volume else [(3, 1)]

    def remove(self):
        self.names.remove(self.current)
        self.current = self.names[0] if self.names else ""

    def setCurrent(self, name):
        assert name in self.names
        self.current = name


class _MockGmsh:
    def __init__(self, existing=False):
        self.initialized = existing
        self.model = _MockModelAPI(existing)
        self.option = SimpleNamespace(setNumber=lambda *args: None)
        self.init_calls = 0
        self.finalize_calls = 0

    def isInitialized(self):
        return self.initialized

    def initialize(self):
        assert not self.initialized
        self.initialized = True
        self.init_calls += 1

    def finalize(self):
        assert self.initialized
        self.initialized = False
        self.finalize_calls += 1
        self.model.names.clear()
        self.model.current = ""


def test_two_consecutive_meshing_runs(monkeypatch):
    """Re-clicking Solve should not raise 'Gmsh already initialized'."""
    gmsh = _MockGmsh()
    monkeypatch.setitem(sys.modules, "gmsh", gmsh)
    for _ in range(2):
        out = make_box(mesh_size=0.01)
        assert out.tet.shape == (1, 4)
    assert (gmsh.init_calls, gmsh.finalize_calls) == (2, 2)
    assert not gmsh.isInitialized()


def test_preinitialized_gmsh_preserved(monkeypatch):
    """Never finalize or overwrite the host's pre-existing Gmsh model."""
    gmsh = _MockGmsh(existing=True)
    monkeypatch.setitem(sys.modules, "gmsh", gmsh)
    for _ in range(2):
        make_box(mesh_size=0.01)
        assert gmsh.isInitialized()
        assert gmsh.model.current == "host"
        assert gmsh.model.names == ["host"]
    assert gmsh.init_calls == 0
    assert gmsh.finalize_calls == 0


def test_preinitialized_gmsh_restored_after_failure(monkeypatch):
    gmsh = _MockGmsh(existing=True)
    gmsh.model.fail_volume = True
    monkeypatch.setitem(sys.modules, "gmsh", gmsh)
    with pytest.raises(ValueError, match="closed solid volumes"):
        make_box()
    assert gmsh.isInitialized()
    assert gmsh.model.names == ["host"]
    assert gmsh.model.current == "host"


def test_owned_gmsh_finalized_after_failure(monkeypatch):
    gmsh = _MockGmsh()
    gmsh.model.fail_volume = True
    monkeypatch.setitem(sys.modules, "gmsh", gmsh)
    with pytest.raises(ValueError, match="closed solid volumes"):
        make_box()
    assert gmsh.finalize_calls == 1
    assert not gmsh.isInitialized()


def test_step_import_reuses_borrowed_session(monkeypatch):
    gmsh = _MockGmsh(existing=True)
    monkeypatch.setitem(sys.modules, "gmsh", gmsh)
    out = import_step(b"ISO-10303-21;\\nENDSEC;")
    assert out.tet.shape == (1, 4)
    assert gmsh.model.current == "host"
