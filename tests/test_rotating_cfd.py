"""No synthetic CFD fields are ever accepted as solved OpenFOAM results.

These tests validate the case editing, safe job identifiers and *actual
VTK-file-only* data import. They do not pretend a VTK fixture is a CFD
simulation: a separate Docker job must independently run pimpleFoam.
"""
from hashlib import sha256
import json
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest

from forceforge.rotating_cfd import (
    ReferenceControls, _replace_scalar, adapt_reference_case,
    _valid_job_root, _collect_vtk, _select_export_time_names, SCENE_KIND,
    _export_verified_fields, recover_fields_only,
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



def test_vtk_export_only_selects_written_nonzero_u_and_p_times(tmp_path):
    for name in ("0","0.002","0.004","0.006","0.008","notes"):
        folder=tmp_path/name
        folder.mkdir()
        (folder/"U").write_text("fixture")
        if name!="0.004":
            (folder/"p").write_text("fixture")
    assert _select_export_time_names(tmp_path)==[
        "0.002","0.006","0.008"
    ]


def test_vtk_export_refuses_missing_real_solver_times(tmp_path):
    folder=tmp_path/"0.002"
    folder.mkdir()
    (folder/"U").write_text("fixture")
    (folder/"p").write_text("fixture")
    with pytest.raises(ValueError,match="Fewer than two"):
        _select_export_time_names(tmp_path)


def test_reject_vtk_frame_count_mismatch_and_preserve_real_seconds(tmp_path):
    meshio=pytest.importorskip("meshio")
    out=tmp_path/"case"/"VTK"
    out.mkdir(parents=True)
    pts=np.column_stack([np.linspace(0,1,30),np.zeros(30),np.zeros(30)])
    for k in (1,2):
        meshio.write(
            out/f"fan_{k:04d}.vtk",
            meshio.Mesh(
                points=pts,
                cells=[("triangle",np.array([[0,1,2]],dtype=int))],
                point_data={"U":np.tile([1.,0.,0.],(30,1)),
                            "p":np.full(30,k*.01)},
            ),file_format="vtk",binary=False,
        )
    with pytest.raises(ValueError,match="expected 3 genuine solver"):
        _collect_vtk(tmp_path,selected_time_names=["0.002","0.004","0.008"])
    assert not (tmp_path/"actual_cfd_frames.npz").exists()
    evidence=_collect_vtk(tmp_path,selected_time_names=["0.002","0.008"])
    assert "Physical seconds" in evidence["time_axis_note"]
    with np.load(tmp_path/"actual_cfd_frames.npz",allow_pickle=False) as saved:
        assert saved["physical_time_s"].tolist()==[.002,.008]



def test_polyhedron_resistance_and_field_only_recovery(tmp_path, monkeypatch):
    import forceforge.rotating_cfd as cfd
    meshio=pytest.importorskip("meshio")
    store=tmp_path/"jobs"
    store.mkdir()
    monkeypatch.setattr(cfd,"ROOT",store)
    monkeypatch.setattr(cfd,"docker_ready",lambda:(True,"sha256:installed"))
    jid="a"*16
    root=store/jid
    case=root/"case"
    case.mkdir(parents=True)
    for t in ("0","0.002","0.004","0.006"):
        folder=case/t
        folder.mkdir()
        (folder/"U").write_text("solver field fixture")
        (folder/"p").write_text("solver field fixture")
    solver="Courant Number mean: 0.02 max: 0.1\nTime = 0.002\nTime = 0.004\nTime = 0.006\nEnd\n"
    (root/"log.pimpleFoam").write_text(solver)
    status={
        "status":"SOLVER_FINISHED_UNVERIFIED_FIELDS",
        "stage":"POSTPROCESS_REAL_FIELDS",
        "job_id":jid,"geometry_origin":SCENE_KIND,
        "solved":True,"solver_log_sha256":sha256(solver.encode()).hexdigest(),
        "controls":{"end_time_s":0.006},
    }
    (root/"status.json").write_text(json.dumps(status))
    scripts=[]
    def fake_docker(folder,script,limit,logname):
        assert folder==root
        scripts.append(script)
        assert "pimpleFoam" not in script
        assert "-poly-decomp" not in script
        assert "-no-point-data" in script
        assert "-time '0.002,0.004,0.006'" in script
        match=re.search(r"-name (FFFields_[0-9a-f]+)",script)
        assert match
        out=case/match.group(1)
        out.mkdir()
        pts=np.column_stack([np.linspace(0,1,30),np.zeros(30),np.zeros(30)])
        for index in (1,2,3):
            meshio.write(out/f"case_{index}.vtk",
                meshio.Mesh(
                    points=pts,
                    cells=[("triangle",np.array([[0,1,2]],dtype=int))],
                    point_data={"U":np.tile([1.0+index,0.,0.],(30,1)),
                                "p":np.full(30,index*.01)}
                ),file_format="vtk",binary=False)
        (root/"foamToVTK.log").write_text(
            "Time: 0.002\nTime: 0.004\nTime: 0.006\nEnd\n"
        )
    monkeypatch.setattr(cfd,"_docker",fake_docker)
    result=recover_fields_only(jid)
    assert result["status"]=="COMPLETED"
    assert result["result"]["frame_count"]==3
    assert result["result"]["polyhedron_handling"].startswith("meshio")
    assert len(scripts)==1
    assert len(list((case/"0.002").iterdir()))==2
    with np.load(root/"actual_cfd_frames.npz",allow_pickle=False) as f:
        assert f["physical_time_s"].tolist()==[.002,.004,.006]



def _make_polyhedron_vtk_fixture(path: Path, flow_speed: float):
    """Construct VTK type-42 cells with U/p data; NOT a CFD solver."""
    vtk=pytest.importorskip("vtk")
    from vtkmodules.util.numpy_support import numpy_to_vtk
    volume=vtk.vtkUnstructuredGrid()
    points=vtk.vtkPoints()
    volume.SetPoints(points)
    offsets=((0,0,0),(1,0,0),(1,1,0),(0,1,0),
             (0,0,1),(1,0,1),(1,1,1),(0,1,1))
    faces=((0,3,2,1),(4,5,6,7),(0,1,5,4),
           (1,2,6,5),(2,3,7,6),(3,0,4,7))
    for j in range(30):
        ids=[points.InsertNextPoint(j*.2+dx*.1,dy*.1,dz*.1)
             for dx,dy,dz in offsets]
        face_stream=vtk.vtkCellArray()
        for face in faces:
            face_stream.InsertNextCell(4,[ids[k] for k in face])
        volume.InsertNextCell(vtk.VTK_POLYHEDRON,8,ids,face_stream)
    u=numpy_to_vtk(np.tile([flow_speed,.1,0.],(30,1)),deep=True)
    u.SetName("U")
    volume.GetCellData().AddArray(u)
    p=numpy_to_vtk(np.linspace(.1,.3,30),deep=True)
    p.SetName("p")
    volume.GetCellData().AddArray(p)
    writer=vtk.vtkUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetFileTypeToASCII()
    writer.SetInputData(volume)
    assert writer.Write()==1


def test_old_type42_vtk_recovers_without_docker(tmp_path,monkeypatch):
    import forceforge.rotating_cfd as cfd
    root_dir=tmp_path/"jobs"
    job_id="f"*16
    root=root_dir/job_id
    vdir=root/"case"/"VTK"
    vdir.mkdir(parents=True)
    for index in (1,2,3):
        _make_polyhedron_vtk_fixture(vdir/f"case_{index}.vtk",float(index))
    solver=("Courant Number mean: 0.01 max: 0.1\n"
            "Time = 0.002\nTime = 0.004\nTime = 0.006\nEnd\n")
    (root/"log.pimpleFoam").write_text(solver)
    (root/"status.json").write_text(json.dumps({
        "status":"FAILED",
        "stage":"POSTPROCESS_RECOVERY_FAILED",
        "solved":True,
        "geometry_origin":SCENE_KIND,
        "solver_log_sha256":sha256(solver.encode()).hexdigest(),
        "controls":{"end_time_s":0.006},
    }))
    monkeypatch.setattr(cfd,"ROOT",root_dir)
    def no_docker(*args,**kwargs):
        raise AssertionError("No Docker or foamToVTK allowed for existing VTK")
    monkeypatch.setattr(cfd,"docker_ready",no_docker)
    monkeypatch.setattr(cfd,"_docker",no_docker)
    solved=recover_fields_only(job_id)
    assert solved["status"]=="COMPLETED"
    assert solved["stage"]=="REAL_TRANSIENT_FIELDS_READY"
    assert solved["recovery_method"]=="EXISTING_VTK_NO_DOCKER"
    assert solved["result"]["frame_count"]==3
    assert "type 42" in solved["result"]["polyhedron_handling"]
    assert len(solved["result"]["source_vtk_files"])==3
    with np.load(root/"actual_cfd_frames.npz",allow_pickle=False) as result:
        assert result["physical_time_s"].tolist()==[.002,.004,.006]
        assert result["velocity_m_s"].shape==(3,30,3)
        assert result["velocity_m_s"][2,0,0]==pytest.approx(3.0)
    assert recover_fields_only(job_id)["status"]=="COMPLETED"


def test_old_vtk_time_mapping_uses_verified_solver_log(tmp_path):
    import forceforge.rotating_cfd as cfd
    vtk_dir=tmp_path/"case"/"VTK"
    vtk_dir.mkdir(parents=True)
    for index in (0,2,4,8):
        (vtk_dir/f"case_{index}.vtk").write_text("fixture marker")
    records=cfd._legacy_vtk_records(
        tmp_path,[.001,.002,.003,.004,.005,.006,.007,.008]
    )
    assert [path.name for path,t in records]==[
        "case_2.vtk","case_4.vtk","case_8.vtk"
    ]
    assert [t for path,t in records]==[.002,.004,.008]


def test_meshio_system_exit_fails_closed_instead_of_stale_running(
    tmp_path,monkeypatch
):
    import meshio
    folder=tmp_path/"case"/"VTK"
    folder.mkdir(parents=True)
    (folder/"case_1.vtk").write_text("not supported")
    (folder/"case_2.vtk").write_text("not supported")
    def polyhedron_not_supported(path):
        raise SystemExit("File contains cells that meshio cannot handle (types 42)")
    monkeypatch.setattr(meshio,"read",polyhedron_not_supported)
    with pytest.raises(ValueError,match="SystemExit"):
        _collect_vtk(tmp_path)


def test_recovery_refuses_missing_completed_solver_proof(tmp_path,monkeypatch):
    import forceforge.rotating_cfd as cfd
    monkeypatch.setattr(cfd,"ROOT",tmp_path)
    folder=tmp_path/("b"*16)
    folder.mkdir()
    (folder/"status.json").write_text(json.dumps({
        "status":"SOLVER_FINISHED_UNVERIFIED_FIELDS",
        "stage":"POSTPROCESS_REAL_FIELDS","solved":True,
        "controls":{"end_time_s":0.04},
    }))
    with pytest.raises(ValueError,match="solver log"):
        cfd.recover_fields_only("b"*16)


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
    with pytest.raises(ValueError,match="No real time-dependent|Unable to validate"):
        _collect_vtk(tmp_path)
    assert not (tmp_path/"actual_cfd_frames.npz").exists()
