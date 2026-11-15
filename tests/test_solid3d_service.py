"""Failure-containment, HTTP routing and result-contract tests for 3D workspace."""
from __future__ import annotations

import base64
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading
from urllib.request import Request, urlopen

import numpy as np
import pytest

import solid3d_service
from forceforge.solid3d import Mesh
from forceforge.solid3d_worker import calculate
from web_server import Handler, handle_api


def test_validates_bad_geometry_and_step_size():
    with pytest.raises(ValueError, match="Geometry"):
        solid3d_service.validated_config({"geometry":"unknown"})
    with pytest.raises(ValueError, match="axis"):
        solid3d_service.validated_config({"axis":"diagonal"})
    with pytest.raises(ValueError, match="must be between"):
        solid3d_service.validated_config({"mesh_size_mm": 0})
    with pytest.raises(ValueError, match="Select|Upload"):
        solid3d_service.validated_config({"geometry":"step"})
    with pytest.raises(ValueError, match="4 MB"):
        solid3d_service.validated_config({
            "geometry":"step", "step_base64":"A" * 5_500_000,
        })
    cfg = solid3d_service.validated_config({
        "geometry":"step",
        "cad_unit":"mm",
        "step_base64":base64.b64encode(b"ISO-10303-21;").decode(),
    })
    assert cfg["cad_unit"] == "mm"


def test_http_dispatches_3d_without_2d_truss_parsing(monkeypatch):
    expected = {"ok":True,"mesh":{"node_count":4}}
    monkeypatch.setattr(solid3d_service, "run_study", lambda config: expected)
    assert handle_api("/api/solid3d/solve", {"geometry":"box"}) == expected


def test_worker_crash_is_handled_and_2d_stays_available(monkeypatch):
    monkeypatch.setattr(
        solid3d_service.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], -11, "", ""),
    )
    with pytest.raises(ValueError, match="exited unexpectedly"):
        solid3d_service.run_study({"geometry":"box"})
    # Parent has not imported native gmsh or died; existing 2D FEA still works.
    assert handle_api("/api/solve", {})["analysis"]["mass_kg"] > 0


def test_worker_timeout_is_bounded(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 65)
    monkeypatch.setattr(solid3d_service.subprocess, "run", fail)
    with pytest.raises(ValueError, match="exceeded"):
        solid3d_service.run_study({"geometry":"box"})


def test_child_result_is_returned(monkeypatch):
    def fake_run(args, **kwargs):
        output = Path(args[-1])
        output.write_text(json.dumps({"ok":True,"mesh":{"node_count":10}}))
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(solid3d_service.subprocess, "run", fake_run)
    out = solid3d_service.run_study({"geometry":"box"})
    assert out["mesh"]["node_count"] == 10


def test_native_worker_calculates_tetrahedron_without_gmsh(monkeypatch):
    mesh = Mesh(
        np.array([[0.,0.,0.],[0.,1.,0.],[0.,0.,1.],[1.,0.,0.]]),
        np.array([[0,1,2,3]]),
    )
    monkeypatch.setattr("forceforge.solid3d_worker.make_box", lambda *a: mesh)
    data = solid3d_service.validated_config({"geometry":"box","E_gpa":.001})
    out = calculate(data)
    assert out["ok"] is True
    assert out["mesh"]["tetrahedra"] == 1
    assert len(out["boundary_faces"]) == 4
    assert out["metrics"]["equilibrium_residual_n"] < 1e-6


def test_worker_refuses_large_mesh(monkeypatch):
    mesh = Mesh(
        np.array([[0.,0.,0.],[0.,1.,0.],[0.,0.,1.],[1.,0.,0.]]),
        np.tile(np.array([[0,1,2,3]]), (solid3d_service.MAX_TETS+1, 1)),
    )
    monkeypatch.setattr("forceforge.solid3d_worker.make_box", lambda *a: mesh)
    data = solid3d_service.validated_config({"geometry":"box"})
    with pytest.raises(ValueError, match="Mesh too dense"):
        calculate(data)


def test_http_3d_page_assets_health_and_api(monkeypatch):
    monkeypatch.setattr(
        solid3d_service, "run_study",
        lambda config: {"ok":True,"mesh":{"node_count":4}},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = "http://127.0.0.1:" + str(server.server_address[1])
        for path, check in [
            ("/", b"FORCEFORGE"),
            ("/solid3d", b"solid3d.js"),
            ("/solid3d.css", b".workspace"),
            ("/solid3d.js", b"/api/solid3d/solve"),
            ("/api/health", b"ok"),
        ]:
            with urlopen(base + path, timeout=5) as response:
                assert response.status == 200
                assert check in response.read()
        req = Request(
            base + "/api/solid3d/solve",
            method="POST",
            data=json.dumps({"geometry":"box"}).encode(),
            headers={"Content-Type":"application/json"},
        )
        with urlopen(req, timeout=5) as response:
            out = json.loads(response.read())
            assert out["ok"] is True
            assert out["mesh"]["node_count"] == 4
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
