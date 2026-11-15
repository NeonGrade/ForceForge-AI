"""No synthetic CFD fields are ever accepted as solved OpenFOAM results.

These tests validate the case editing, safe job identifiers and *actual
VTK-file-only* data import. They do not pretend a VTK fixture is a CFD
simulation: a separate Docker job must independently run pimpleFoam.
"""
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from forceforge.rotating_cfd import (
    ReferenceControls, _replace_scalar, adapt_reference_case,
    _valid_job_root, _collect_vtk, SCENE_KIND,
)


def test_transient_rotation_units_exact():
    req=ReferenceControls(rpm=1500,end_time_s=.04,write_interval_s=.004)
    assert req.angular_velocity_rad_s==pytest.approx(50*np.pi)
    assert req.end_time_s*req.rpm/60==pytest.approx(1.)
    assert req.as_dict()["geometry_origin"]==SCENE_KIND


@pytest.mark.parametrize("rpm,time,write",[
    (0,.04,.004),(5001,.04,.004),(1500,.001,.001),
    (1500,.1,.004),(1500,.04,.03),(1500,.008,.006),
])
def test_reject_nonphysical_or_excessive_demo_budget(rpm,time,write):
    with pytest.raises(ValueError):
        ReferenceControls(rpm=rpm,end_time_s=time,write_interval_s=write)


def test_no_silent_dictionary_rewriting_or_missing_motion(tmp_path):
    case=tmp_path
    (case/"constant").mkdir()
    (case/"system").mkdir()
    (case/"constant"/"dynamicMeshDict").write_text(
        "cellZone rotatingZone;\nsolidBodyMotionFunction rotatingMotion;\n"
        "origin (0 0 0);\naxis (0 0 1);\nomega 10;\n"
    )
    (case/"system"/"controlDict").write_text(
        "application pimpleFoam;\nendTime 1;\n"
        "writeControl timeStep;\nwriteInterval 5;\n"
    )
    result=adapt_reference_case(case,ReferenceControls())
    assert result["motion"]=="rotatingMotion"
    assert "omega 157.079632679;" in (
        case/"constant"/"dynamicMeshDict"
    ).read_text()
    control=(case/"system"/"controlDict").read_text()
    assert "endTime 0.04;" in control
    assert "writeInterval 0.004;" in control
    assert "writeControl runTime;" in control
    assert len(result["dynamic_mesh_sha256"])==64


def test_dictionary_requires_single_entry_for_every_control():
    with pytest.raises(ValueError,match="exactly one"):
        _replace_scalar("omega 10;\nomega 20;\n","omega","30")
    with pytest.raises(ValueError,match="exactly one"):
        _replace_scalar("no omega defined","omega","30")


@pytest.mark.parametrize("value",["../../etc/passwd","myjob","0"*15, "g"*16])
def test_job_path_rejects_traversal_and_unapproved_location(value):
    with pytest.raises(ValueError):
        _valid_job_root(value)


def test_parser_reads_numeric_fields_only_from_real_vtk_files(tmp_path):
    meshio=pytest.importorskip("meshio")
    root=tmp_path
    out=root/"case"/"VTK"
    out.mkdir(parents=True)
    points=np.zeros((30,3),dtype=float)
    points[:,0]=np.linspace(0,1,30)
    points[:,1]=np.linspace(.1,.6,30)
    cells=[("triangle",np.array([[0,1,2]],dtype=int))]
    for k in (1,2,3):
        U=np.tile([1.0+k*.25,0.05,0.0],(30,1))
        p=np.full(30,k*.01)
        # The names encode real **record indices** here, not time values.
        meshio.write(
            out/f"fan_{k:04d}.vtk",
            meshio.Mesh(points=points,cells=cells,point_data={"U":U,"p":p}),
            file_format="vtk",binary=False,
        )
    evidence=_collect_vtk(root)
    assert evidence["frame_count"]==3
    assert evidence["sample_points_per_frame"]==30
    with np.load(root/"actual_cfd_frames.npz",allow_pickle=False) as data:
        assert data["velocity_m_s"].shape==(3,30,3)
        assert data["kinematic_pressure_m2_s2"].shape==(3,30)
        assert data["vtk_record_indices"].tolist()==[1,2,3]
        assert data["velocity_m_s"][0,0,0]==pytest.approx(1.25)
    assert len(evidence["source_vtk_files"])==3
    assert all(len(x["sha256"])==64 for x in evidence["source_vtk_files"])


def test_missing_genuine_solver_fields_never_yields_fake_animation(tmp_path):
    meshio=pytest.importorskip("meshio")
    folder=tmp_path/"case"/"VTK"
    folder.mkdir(parents=True)
    meshio.write(
        folder/"fan_0001.vtk",
        meshio.Mesh(points=np.zeros((30,3)),cells=[]),
        file_format="vtk",binary=False,
    )
    with pytest.raises(ValueError,match="Unable to validate"):
        _collect_vtk(tmp_path)
    assert not (tmp_path/"actual_cfd_frames.npz").exists()
