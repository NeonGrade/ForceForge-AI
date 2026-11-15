"""No fake CFD: rotor loop is actual sourced STL motion over a fixed snapshot."""
import gzip
from hashlib import sha256
from pathlib import Path
import struct

import numpy as np
import pytest

from forceforge.continuous_rotor import (
    read_stl_payload,sample_stl,source_motion,load_completed_case_rotor,
    rigid_loop,make_loop_html,
)


def stl_ascii():
    triangles=[]
    for i in range(40):
        triangles.append(
            "facet normal 0 0 1\nouter loop\n"
            f"vertex {i*.01} 0 0\n"
            f"vertex {i*.01+.01} .01 0\n"
            f"vertex {i*.01} .02 0\n"
            "endloop\nendfacet\n"
        )
    return ("solid fan\n"+"".join(triangles)+"endsolid fan\n").encode()


def test_read_actual_ascii_and_gzip_binary_rotor(tmp_path):
    blob=stl_ascii()
    path=tmp_path/"fan.stl.gz"
    with gzip.open(path,"wb") as f:
        f.write(blob)
    assert read_stl_payload(path)==blob
    triangles=sample_stl(blob,limit=26)
    assert triangles.shape==(26,3,3)
    header=b"real binary STL".ljust(80,b" ")
    one=struct.pack("<12fH",0,0,1,0,0,0,1,0,0,0,1,0,0)
    payload=header+struct.pack("<I",40)+one*40
    parsed=sample_stl(payload,limit=25)
    assert parsed.shape==(25,3,3)
    assert np.isfinite(parsed).all()


def test_motion_uses_explicit_axis_and_smooth_periodic_rodrigues():
    centre,axis=source_motion(
        "dynamicFvMesh solidBodyMotionFvMesh;"
        "\nsolidBodyMotionFunction rotatingMotion;\n"
        "origin (-3 2 2.6);\naxis (0 1 0);\nomega 62.8;\n"
    )
    tri=np.asarray([[[1.,0,0],[0,1,0],[0,0,1]]])
    t,vertices=rigid_loop(
        tri,origin=np.zeros(3),axis=axis,rpm=600,count=49
    )
    assert np.allclose(vertices[0],vertices[-1],atol=1e-13)
    assert not np.allclose(vertices[0],vertices[12])
    assert t[-1]==pytest.approx(.1)
    assert centre==pytest.approx([-3,2,2.6])
    assert np.allclose(
        np.linalg.norm(vertices,axis=2),
        np.linalg.norm(vertices[0],axis=1)[None,:]
    )


def test_source_validation_fails_closed_and_original_case_links(tmp_path,monkeypatch):
    import forceforge.rotating_cfd as cfd
    job_id="c"*16
    monkeypatch.setattr(cfd,"ROOT",tmp_path)
    root=tmp_path/job_id
    tri_dir=root/"case"/"constant"/"triSurface"
    tri_dir.mkdir(parents=True)
    (tri_dir/"fan.stl").write_bytes(stl_ascii())
    (root/"case"/"constant"/"dynamicMeshDict").write_text(
        "solidBodyMotionFunction rotatingMotion;\n"
        "origin (-3 2 2.6);\naxis (0 0 1);\nomega 62.8;\n"
    )
    monkeypatch.setattr(cfd,"job_status",lambda id:{
        "status":"COMPLETED","solved":True,
        "geometry_origin":"OFFICIAL_OPENFOAM_ROTATING_FAN_REFERENCE_GEOMETRY",
        "controls":{"rpm":600}
    })
    sample=load_completed_case_rotor(job_id)
    assert sample["sha256"]==sha256(stl_ascii()).hexdigest()
    assert sample["triangles"].shape==(40,3,3)
    assert sample["origin_m"]==pytest.approx([-3,2,2.6])
    monkeypatch.setattr(cfd,"job_status",lambda id:{
        "status":"FAILED","solved":True
    })
    with pytest.raises(ValueError,match="verified"):
        load_completed_case_rotor(job_id)


def test_loop_html_keeps_real_solver_snapshot_frozen():
    triangles=sample_stl(stl_ascii())
    source={
        "triangles":triangles,
        "origin_m":np.array([0.,0.,0.]),
        "axis":np.array([0.,0.,1.]),
        "sha256":sha256(stl_ascii()).hexdigest(),"rpm":600,
    }
    xyz=np.zeros((3,40,3),dtype=float)
    xyz[:,:,0]=np.linspace(-.4,.4,40)
    xyz[:,:,1]=.15
    vel=np.zeros_like(xyz)
    vel[:,:,0]=1.7
    p=np.ones((3,40),dtype=float)*.2
    model={
        "sample_points":xyz,
        "velocity_m_s":vel,
        "kinematic_pressure_m2_s2":p,
        "physical_time_s":np.array([.004,.023,.04]),
    }
    html=make_loop_html(source,model)
    assert "ff-real-rotor" in html
    assert "Play continuous rotor" in html
    assert "Plotly.restyle" in html
    assert "ffRotorSteps" in html
    assert "frozen" in html.lower()
    assert "0.040000 s" in html
    assert "No computed fields between solver frames" in html
    with pytest.raises(ValueError,match="Verified"):
        make_loop_html(source,{**model,"velocity_m_s":np.zeros((2,40,3))})
