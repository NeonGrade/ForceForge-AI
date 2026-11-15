"""Pluggable REAL STEP generators for the restricted product-family catalog.

The current L-bracket reuses the validated CAD worker. A wall fan receives an
explicitly conceptual multi-solid STEP assembly (blades, hub, guard, stand,
wall plate), built with Gmsh OpenCASCADE in a *separate* disposable process.
The fan has NO blade-airfoil, bolted joints, contact, CFD or qualified FEA.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

from .engineering_schema import (
    EngineeringRequest, FanGeometry, BracketGeometry, preflight_missing,
)
from .step_mesh import MAX_CAD_BYTES, _validate_step

_ROOT=Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CADProduct:
    family: str
    step_bytes: bytes
    sha256: str
    description: str
    concept_only: bool
    solid_parts: int | None
    preview_nodes_mm: np.ndarray | None = None
    preview_faces: np.ndarray | None = None

    def metadata(self) -> dict:
        return {
            "family":self.family,
            "source_sha256":self.sha256,
            "step_bytes":len(self.step_bytes),
            "description":self.description,
            "concept_only":self.concept_only,
            "solid_parts":self.solid_parts,
            "preview_surface_available":(
                self.preview_nodes_mm is not None
                and self.preview_faces is not None
            ),
        }


def _concept_fan_worker(params: dict, folder: Path) -> None:
    """Native geometry generation, executed ONLY from the worker process.

    The axial direction is +Z. Rotor is *one* conceptual OCC compound after
    fusion, surrounded by independent guard/motor/wall-mount bodies. There is
    no modeled load transfer, rotor interference check or motor torque.
    """
    from .step_mesh import _gmsh_session, _require_gmsh
    gmsh=_require_gmsh()
    D=float(params["diameter_mm"])
    hub_d=float(params["hub_diameter_mm"])
    blades=int(params["blade_count"])
    pitch_deg=float(params["blade_pitch_deg"])
    rotor_r=D/2
    hub_r=hub_d/2
    if not 100<=D<=800 or not 3<=blades<=9 or not 5<=pitch_deg<=45:
        raise ValueError("Invalid conceptual wall fan dimensions")
    if not 20<=hub_d<.55*D or hub_d>=D-35:
        raise ValueError("Concept wall fan hub diameter intersects blade envelope")
    source=folder/"concept_wall_fan.step"

    with _gmsh_session(gmsh):
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.model.add("ForceForge wall fan concept - NOT validated")
        occ=gmsh.model.occ

        # Impeller hub and constant-pitch plate blades, deliberately simple.
        hub=occ.addCylinder(0,0,-8,0,0,16,hub_r)
        span=rotor_r-hub_r-7.
        chord=max(12.,D*.12)
        tools=[]
        for k in range(blades):
            blade=occ.addBox(hub_r-3, -chord/2, -1.5, span+5., chord, 3.)
            occ.rotate([(3,blade)],0,0,0,1,0,0,math.radians(pitch_deg))
            occ.rotate([(3,blade)],0,0,0,0,0,1,2*math.pi*k/blades)
            tools.append((3,blade))
        fused,_=occ.fuse([(3,hub)],tools,removeObject=True,removeTool=True)
        if not any(dim==3 for dim,_ in fused):
            raise RuntimeError("Unable to construct the conceptual impeller")

        # Guard ring is a separate solid (no meshed contact or CFD domain).
        outer=occ.addCylinder(0,0,-13,0,0,26,rotor_r+10)
        inner=occ.addCylinder(0,0,-14,0,0,28,rotor_r+5)
        occ.cut([(3,outer)],[(3,inner)],removeObject=True,removeTool=True)

        # Motor housing, standoff and a wall plate are concept solids.
        motor=occ.addCylinder(0,0,-36,0,0,22,hub_r*.77)
        shaft=occ.addCylinder(0,0,-83,0,0,47,max(7.,hub_r*.32))
        plate_w=max(55.,D*.24)
        plate_h=max(55.,D*.24)
        plate=occ.addBox(-plate_w/2,-plate_h/2,-89,plate_w,plate_h,6.)
        occ.fuse([(3,motor)],[(3,shaft),(3,plate)],
                 removeObject=True,removeTool=True)
        occ.synchronize()

        solids=gmsh.model.getEntities(3)
        if not 2<=len(solids)<=25:
            raise ValueError(
                f"Concept assembly must have multiple bounded solid bodies; found {len(solids)}"
            )
        gmsh.write(str(source))

        # An actual OCC-meshed surface preview (not a fake result/cloud plot).
        # If tessellation fails the valid STEP remains exportable.
        try:
            gmsh.option.setNumber("Mesh.MeshSizeMin",max(4.,D/28))
            gmsh.option.setNumber("Mesh.MeshSizeMax",max(8.,D/15))
            gmsh.model.mesh.generate(2)
            node_tags, coords, _=gmsh.model.mesh.getNodes()
            tags=np.asarray(node_tags,dtype=np.int64)
            nodes=np.asarray(coords,dtype=float).reshape(-1,3)
            if 0<len(nodes)<=150000:
                lookup={int(tag):idx for idx,tag in enumerate(tags)}
                types,_,connectivity=gmsh.model.mesh.getElements(2)
                faces=[]
                for typ, group in zip(types,connectivity):
                    if int(typ)==2:
                        tri=np.asarray(group,dtype=np.int64).reshape(-1,3)
                        faces.extend([lookup[int(v)] for v in tri.flatten()])
                if faces:
                    triangles=np.asarray(faces,dtype=np.int32).reshape(-1,3)
                    if len(triangles)<=75000:
                        np.savez_compressed(
                            folder/"surface.npz",vertices_mm=nodes,faces=triangles
                        )
        except Exception:
            # An unavailable visual preview is not a failed CAD STEP export.
            pass
        (folder/"solid_count.json").write_text(
            json.dumps({"solids":len(solids)}),encoding="utf-8",
        )


def generate_wall_fan_safely(request: EngineeringRequest) -> CADProduct:
    """One-click conceptual STEP export with isolated native geometry work."""
    if request.family.value!="wall_fan" or not isinstance(request.geometry,FanGeometry):
        raise ValueError("Wall fan generator requires a matching fan product schema")
    missing=preflight_missing(request)
    if missing:
        raise ValueError("Fan concept CAD is blocked; missing: "+", ".join(missing))
    g=request.geometry
    assert g.diameter_mm is not None
    assert g.hub_diameter_mm is not None
    assert g.blade_count is not None
    assert g.blade_pitch_deg is not None
    params=g.model_dump(mode="json")
    with tempfile.TemporaryDirectory(prefix="fffan_") as temp:
        folder=Path(temp)
        (folder/"input.json").write_text(json.dumps(params),encoding="utf-8")
        env=dict(os.environ)
        for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
            env[name]="1"
        try:
            done=subprocess.run(
                [sys.executable,"-m","forceforge.product_cad","--concept-fan-worker",str(folder)],
                cwd=_ROOT,env=env,stdin=subprocess.DEVNULL,capture_output=True,
                text=True,check=False,timeout=45,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Concept fan OCC worker exceeded 45s. The main UI remains available."
            ) from exc
        if done.returncode!=0:
            detail=(done.stderr or done.stdout or "native crash").strip()[-950:]
            raise RuntimeError(
                f"Concept fan CAD worker failed ({done.returncode}); original app remains available: {detail}"
            )
        payload=(folder/"concept_wall_fan.step").read_bytes()
        _validate_step(payload)
        if len(payload)>MAX_CAD_BYTES:
            raise ValueError("Generated concept exceeds the STEP size cap")
        info=json.loads((folder/"solid_count.json").read_text(encoding="utf-8"))
        nodes=triangles=None
        preview=folder/"surface.npz"
        if preview.exists():
            with np.load(preview,allow_pickle=False) as arr:
                nodes=arr["vertices_mm"].copy()
                triangles=arr["faces"].copy()
        return CADProduct(
            family="wall_fan",
            step_bytes=payload,
            sha256=sha256(payload).hexdigest(),
            description="Simplified multi-solid wall-mounted axial fan: flat blades, guard ring, motor and mounting plate; NO verified airflow or wall connection",
            concept_only=True,
            solid_parts=int(info["solids"]),
            preview_nodes_mm=nodes,
            preview_faces=triangles,
        )


def _generate_bracket_product(request: EngineeringRequest) -> CADProduct:
    """Adapter for the already validated bracket STEP generator."""
    if not isinstance(request.geometry,BracketGeometry):
        raise ValueError("Invalid bracket geometry")
    if request.geometry.web_thickness_mm is None:
        raise ValueError("Select an explicit web thickness before generating")
    from .isolated_cad import generate_bracket_safely
    data=generate_bracket_safely(request.geometry.web_thickness_mm)
    return CADProduct(
        family="l_bracket",step_bytes=data,sha256=sha256(data).hexdigest(),
        description="Editable drilled L-bracket BRep generated by the existing isolated Gmsh worker",
        concept_only=False,solid_parts=1,
    )


# Every registered adapter receives a strict typed request and returns a
# provenance-linked genuine STEP. Adding a family requires explicit code and
# tests; neither user text nor AI output may import arbitrary Python modules.
CAD_GENERATORS = {
    "l_bracket": _generate_bracket_product,
    "wall_fan": generate_wall_fan_safely,
}


def generate_product(request: EngineeringRequest) -> CADProduct:
    """Dispatch through a fixed trusted CAD generator registry."""
    if not isinstance(request,EngineeringRequest):
        raise TypeError("Validated versioned EngineeringRequest required")
    generator=CAD_GENERATORS.get(request.family.value)
    if generator is None:
        raise ValueError("Unregistered CAD product family")
    product=generator(request)
    if product.family!=request.family.value:
        raise ValueError("CAD plugin returned geometry for a different product family")
    return product


if __name__=="__main__":
    if len(sys.argv)!=3 or sys.argv[1]!="--concept-fan-worker":
        raise SystemExit("Internal ForceForge CAD worker; do not run directly")
    folder=Path(sys.argv[2])
    try:
        configuration=json.loads((folder/"input.json").read_text(encoding="utf-8"))
        _concept_fan_worker(configuration,folder)
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(2)
