"""Isolate an actual rotating blade solid from the user's genuine STEP.

Exports a closed-manifold STL in SI metres, centred in the OFFICIAL
OpenFOAM reference room. Other fan solids stay stationary / unmodeled.
The reference-room flow is not a wall-mounted installation model.
Native OpenCASCADE work runs in a crash-isolated subprocess.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

from .engineering_schema import EngineeringRequest, FanGeometry
from .step_mesh import _validate_step

ROOT = Path(__file__).resolve().parents[1]
ROOM_CENTRE_M = (-3., 2., 2.6)
MAX_TRIANGLES = 130000
MAX_STL_BYTES = 22 * 1024 * 1024


@dataclass(frozen=True)
class RotorSTL:
    stl_bytes: bytes
    cad_source_sha256: str
    stl_sha256: str
    triangles: int
    source_bbox_mm: tuple[float, ...]
    reference_room_centre_m: tuple[float,float,float]

    def as_dict(self):
        return {
            "stl_bytes":len(self.stl_bytes),
            "cad_source_sha256":self.cad_source_sha256,
            "stl_sha256":self.stl_sha256,
            "triangles":self.triangles,
            "source_bbox_mm":list(self.source_bbox_mm),
            "reference_room_centre_m":list(self.reference_room_centre_m),
            "geometry_scope":"USER_ROTOR_IN_OFFICIAL_REFERENCE_ROOM_NOT_WALL_FAN",
        }


def _native_worker(folder:Path):
    from .step_mesh import _require_gmsh, _gmsh_session
    params=json.loads((folder/"input.json").read_text(encoding="utf-8"))
    source=(folder/"source.step").read_bytes()
    if sha256(source).hexdigest()!=params["sha256"]:
        raise ValueError("Actual STEP provenance hash differs")
    _validate_step(source)
    D=float(params["diameter_mm"])
    if not 100<=D<=800:
        raise ValueError("Out-of-bounds rotor diameter")
    gmsh=_require_gmsh()
    with _gmsh_session(gmsh):
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.model.add("True source-STEP rotor extraction")
        occ=gmsh.model.occ
        occ.importShapes(str(folder/"source.step"))
        occ.synchronize()
        solids=gmsh.model.getEntities(3)
        if not 2<=len(solids)<=20:
            raise ValueError("Source fan must contain distinct actual STEP solids")
        found=[]
        for _,tag in solids:
            bb=occ.getBoundingBox(3,tag)
            radial=.5*((bb[3]-bb[0])+(bb[4]-bb[1]))
            z_height=bb[5]-bb[2]
            if (.70*D<=radial<=D+4 and z_height<.5*D
                    and bb[2]<0<bb[5]):
                found.append((abs(radial-D),int(tag),bb))
        if len(found)!=1:
            raise ValueError(
                f"No unique real rotating rotor solid found: {len(found)} candidates"
            )
        _,tag,bb=found[0]
        occ.remove([(3,int(t)) for _,t in solids if int(t)!=tag],recursive=True)
        occ.synchronize()
        if len(gmsh.model.getEntities(3))!=1:
            raise ValueError("Removing non-rotor CAD did not yield one solid")
        gmsh.option.setNumber("Mesh.MeshSizeMin",max(2.5,D/80))
        gmsh.option.setNumber("Mesh.MeshSizeMax",max(6.,D/32))
        gmsh.model.mesh.generate(2)
        tags,coords,_=gmsh.model.mesh.getNodes()
        nodes=np.asarray(coords,dtype=float).reshape(-1,3)
        idx={int(t):i for i,t in enumerate(tags)}
        triangles=[]
        for _,face in gmsh.model.getEntities(2):
            types,_,connectivity=gmsh.model.mesh.getElements(2,face)
            for typ,tri_tags in zip(types,connectivity):
                if int(typ)==2:
                    tris=np.asarray(tri_tags,dtype=np.int64).reshape(-1,3)
                    for tri in tris:
                        triangles.append([idx[int(q)] for q in tri])
        if not 50<=len(triangles)<=MAX_TRIANGLES:
            raise ValueError("Source rotor triangulation is empty or too large")
        tri=np.asarray(triangles,dtype=np.int64)
        edges=np.concatenate([
            tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]],
        ])
        edges.sort(axis=1)
        _,counts=np.unique(edges,axis=0,return_counts=True)
        if np.any(counts!=2):
            raise ValueError("Rotor surface is not a watertight manifold")
        pts=nodes/1000+np.asarray(ROOM_CENTRE_M)
        normal=np.cross(
            pts[tri[:,1]]-pts[tri[:,0]],
            pts[tri[:,2]]-pts[tri[:,0]],
        )
        length=np.linalg.norm(normal,axis=1)
        if not np.isfinite(length).all() or np.any(length<1e-13):
            raise ValueError("STL has degenerate rotor face")
        normal/=length[:,None]
        output=folder/"actual_rotor.stl"
        with output.open("w",encoding="ascii") as stream:
            stream.write("solid fan\n")
            for face,n in zip(tri,normal):
                stream.write("  facet normal "+" ".join(f"{v:.8e}" for v in n)+"\n")
                stream.write("    outer loop\n")
                for k in face:
                    stream.write("      vertex "+" ".join(f"{v:.8e}" for v in pts[int(k)])+"\n")
                stream.write("    endloop\n  endfacet\n")
            stream.write("endsolid fan\n")
        if output.stat().st_size>MAX_STL_BYTES:
            raise ValueError("Rotor surface STL too large")
        (folder/"result.json").write_text(json.dumps({
            "bbox_mm":list(bb),"triangles":len(tri),
            "sha256":sha256(output.read_bytes()).hexdigest(),
            "cad_source_sha256":params["sha256"],
        }),encoding="utf-8")


def extract_rotor_from_step(
    request:EngineeringRequest,source_step:bytes,
) -> RotorSTL:
    if request.family.value!="wall_fan" or not isinstance(request.geometry,FanGeometry):
        raise ValueError("Only a validated wall-fan schema supports rotor extraction")
    if not request.concept_assumptions_confirmed:
        raise ValueError("User approval required for conceptual blade CAD")
    if request.geometry.diameter_mm is None:
        raise ValueError("Explicit real fan diameter required")
    _validate_step(source_step)
    digest=sha256(source_step).hexdigest()
    with tempfile.TemporaryDirectory(prefix="forceforge_rotor_") as tmp:
        folder=Path(tmp)
        (folder/"source.step").write_bytes(source_step)
        (folder/"input.json").write_text(json.dumps({
            "sha256":digest,
            "diameter_mm":request.geometry.diameter_mm,
        }),encoding="utf-8")
        env=os.environ.copy()
        for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
            env[key]="1"
        try:
            done=subprocess.run(
                [sys.executable,"-m","forceforge.rotor_surface",
                 "--worker",str(folder)],
                cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                capture_output=True,text=True,timeout=55,check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("True STEP rotor extraction timed out") from exc
        if done.returncode:
            raise RuntimeError(
                "Real source-STEP rotor extraction failed: "
                +(done.stderr or done.stdout)[-1000:]
            )
        blob=(folder/"actual_rotor.stl").read_bytes()
        result=json.loads((folder/"result.json").read_text())
        if result["cad_source_sha256"]!=digest or result["sha256"]!=sha256(blob).hexdigest():
            raise ValueError("STL provenance mismatch")
        return RotorSTL(
            stl_bytes=blob,
            cad_source_sha256=digest,
            stl_sha256=result["sha256"],
            triangles=int(result["triangles"]),
            source_bbox_mm=tuple(result["bbox_mm"]),
            reference_room_centre_m=ROOM_CENTRE_M,
        )


if __name__=="__main__":
    if len(sys.argv)!=3 or sys.argv[1]!="--worker":
        raise SystemExit("Internal ForceForge native rotor STL worker")
    try:
        _native_worker(Path(sys.argv[2]))
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(2)
