"""Context, confirmation and numerical-evidence regressions for the upgraded Agent."""
from dataclasses import replace
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import pytest

from forceforge.agent import parse_offline
from forceforge.engineering_agent import (
    CadProposal, propose_cad_inputs, confirm_cad_inputs, review_cad_result,
)
from forceforge.cad_solid import CadLoad, solve_cad_mesh
from forceforge.mesh_verification import assess_mesh_evidence
from forceforge.robust import Requirements, grid_search
from forceforge.solid3d import SolidCase, _solid_nodes_and_tets
from forceforge.step_mesh import CadMesh
from forceforge.surrogate import train, propose_and_verify


@pytest.fixture(scope="module")
def training():
    req = Requirements()
    data = grid_search(req, heights=(.8, 1., 1.2, 1.4),
                       areas_mm2=(100., 180., 300., 550.))
    return req, data, train(data)


@pytest.mark.parametrize("change", [
    {"base_load_n": 1200}, {"material_E_pa": 70e9},
    {"yield_safety_factor": 3}, {"area_uncertainty": .2},
    {"span_m": 3},
])
def test_model_cannot_cross_engineering_contexts(training, change):
    req, _, (model, columns, _) = training
    with pytest.raises(ValueError, match="context changed"):
        propose_and_verify(model, columns, replace(req, **change))


def test_model_rejects_changed_solver_version(training, monkeypatch):
    import forceforge.surrogate as surrogate
    req, _, (model, columns, _) = training
    original = surrogate.truss_context
    monkeypatch.setattr(surrogate, "truss_context", lambda r: {**original(r), "solver_sha256": "new"})
    with pytest.raises(ValueError, match="context changed"):
        propose_and_verify(model, columns, req)


def test_training_rejects_unversioned_csv_or_conflicting_labels(training):
    _, data, _ = training
    unversioned = data.copy()
    unversioned.attrs.clear()
    with pytest.raises(ValueError, match="context missing"):
        train(unversioned)
    conflicting = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    conflicting.loc[len(conflicting)-1, "worst_stress_util"] += .1
    with pytest.raises(ValueError, match="Conflicting FEA"):
        train(conflicting)


def test_height_holdout_keeps_whole_heights_unseen(training):
    _, data, _ = training
    model, _, metrics = train(data, validation_strategy="height")
    info = model.forceforge_validation_
    assert set(info["train_heights_m"]).isdisjoint(info["test_heights_m"])
    assert all(np.isfinite(m["mae"]) and np.isfinite(m["baseline_mae"]) for m in metrics.values())


def test_verified_candidates_export_prediction_error_and_context(training):
    req, _, (model, cols, _) = training
    result = propose_and_verify(model, cols, req, n=300)
    assert len(result) == 12
    assert result.fea_verified.all()
    assert set(result.requirements_id) == {model.forceforge_context_id_}
    assert np.allclose(result.prediction_abs_error,
                       abs(result.predicted_worst_util - result.worst_utilization))


def test_legacy_parser_understands_adjacent_chinese_and_exponents():
    parsed = parse_offline("跨度2米，载荷1e3牛顿，位移2毫米")
    assert (parsed.span_m, parsed.load_n, parsed.max_displacement_mm) == (2, 1000, 2)


@pytest.mark.parametrize("brief", [
    "Force 0.25 kN, mesh 1.2 cm, web 10 mm, E 200 GPa",
    "载荷250牛顿，网格12毫米，腹板厚度10毫米，弹性模量200GPa",
])
def test_cad_parser_does_not_apply_legacy_truss_defaults(brief):
    current = {"source": "generated", "force_n": 80, "token": None}
    proposal = propose_cad_inputs(brief, current)
    assert proposal.changes == {"force_n":250, "mesh_size_mm":12, "web_mm":10, "E_gpa":200}
    assert current["force_n"] == 80
    confirmed = confirm_cad_inputs(proposal, current)
    assert confirmed["force_n"] == 250
    assert "span_m" not in confirmed
    with pytest.raises(ValueError, match="Inputs changed"):
        confirm_cad_inputs(proposal, {**current, "token": "changed-CAD"})


@pytest.mark.parametrize("brief", [
    "force -100 N", "force 250 N, force 500 N", "force 250 kg",
    "web 9 mm", "mesh 30 mm", "E 1e999 GPa", "certify this as safe",
])
def test_cad_parser_rejects_ambiguous_unsupported_or_invalid_requests(brief):
    with pytest.raises(ValueError):
        propose_cad_inputs(brief, {"source":"generated"})


def test_cad_parser_cannot_rewrite_imported_geometry_or_worker_limits():
    with pytest.raises(ValueError, match="Imported STEP"):
        propose_cad_inputs("web 12 mm", {"source":"uploaded", "token":"a"*64})
    with pytest.raises(ValueError, match="out-of-range"):
        propose_cad_inputs("mesh 2 mm", {}, profile="stable")
    proposal = propose_cad_inputs("force 250 N", {})
    proposal.changes["max_tets"] = 999999
    with pytest.raises(ValueError, match="Unsupported"):
        confirm_cad_inputs(proposal, {})


@pytest.fixture(scope="module")
def cad_results():
    results = []
    digest = sha256(b"independent numerical test box; not real CAD measurements").hexdigest()
    for size, count in ((15, 4), (12, 6), (10, 8)):
        case = SolidCase(nx=1, ny=1, nz=count, force_n=100)
        nodes, cells = _solid_nodes_and_tets(case)
        volume = case.length_m * case.width_m * case.thickness_m
        mesh = CadMesh(nodes, cells, digest, "Numerical test fixture", size,
                       volume, volume, np.vstack((nodes.min(axis=0), nodes.max(axis=0))), 0., 1.)
        results.append(solve_cad_mesh(mesh, CadLoad(force_n=100)))
    return results


def test_cad_review_uses_actual_fe_outputs_and_exact_mesh_evidence(cad_results):
    baseline = cad_results[1]
    evidence = assess_mesh_evidence(cad_results, baseline.mesh.source_sha256, baseline.load)
    review = review_cad_result(baseline, mesh_evidence=evidence,
                               expected_source=baseline.mesh.source_sha256,
                               expected_load=baseline.load)
    assert review["metrics"]["tip_displacement_mm"] == baseline.tip_mm
    assert review["metrics"]["sampled_von_mises_mpa"] == baseline.peak_von_mises_mpa
    assert review["mesh_assessment"] == evidence.decision
    assert review["assessment"] != "SAFE"
    assert any("does not establish local peak-stress convergence" in s for s in review["limitations"])
    assert any("not applicable" in s for s in review["limitations"])
    assert review_cad_result(baseline)["mesh_assessment"] == "NOT_EVALUATED"


def test_cad_review_refuses_stale_or_nonfinite_evidence(cad_results):
    baseline = cad_results[1]
    with pytest.raises(ValueError, match="source SHA"):
        review_cad_result(baseline, expected_source="b"*64)
    with pytest.raises(ValueError, match="load/material"):
        review_cad_result(baseline, expected_load=replace(baseline.load, force_n=200))
    with pytest.raises(ValueError, match="Non-finite"):
        review_cad_result(replace(baseline, sampled_peak_stress_pa=float("nan")))
    evidence = assess_mesh_evidence(cad_results, baseline.mesh.source_sha256, baseline.load)
    with pytest.raises(ValueError, match="different CAD"):
        review_cad_result(baseline, mesh_evidence=replace(evidence, source_sha256="b"*64))


def test_preview_and_confirmation_http_do_not_invoke_solver(monkeypatch):
    import studio_server
    import studio_cad_api
    monkeypatch.setattr(studio_cad_api, "analyze", lambda *args: pytest.fail("Preview must not solve"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio_server.StudioHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def post(path, data):
        req = Request(f"http://127.0.0.1:{server.server_port}"+path,
                      json.dumps(data).encode(), {"Content-Type":"application/json"})
        with urlopen(req, timeout=5) as response:
            return json.load(response)
    try:
        preview = post("/api/cad/agent/preview", {"current":{}, "prompt":"force 300 N"})
        assert preview["proposal"]["changes"] == {"force_n":300}
        confirmed = post("/api/cad/agent/confirm", {"current":{}, "proposal":preview["proposal"]})
        assert confirmed["parameters"]["force_n"] == 300
        with pytest.raises(HTTPError) as error:
            post("/api/cad/agent/confirm", {"current":{"force_n":400}, "proposal":preview["proposal"]})
        assert error.value.code == 400
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
