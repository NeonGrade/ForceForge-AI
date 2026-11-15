"""Real 3D air-volume / actuator-zone preprocessor, NOT a CFD solver.

This opt-in stage builds a conforming two-zone Gmsh tetrahedral fluid mesh,
with tagged upstream/downstream/farfield patches and an internal rotor region.
The geometry is a SIMPLIFIED ACTUATOR ZONE based on an explicitly confirmed
fan diameter; it DOES NOT subtract the blades or evaluate fluid flow.
OpenFOAM solver coupling, fan curves, turbulence and wall effects remain
BLOCKED. All native Gmsh calls occur inside a bounded disposable subprocess.
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
from threading import Lock

import numpy as np

from .engineering_schema import EngineeringRequest, FanGeometry
from .step_mesh import MAX_CAD_BYTES, _validate_step

_ROOT=Path(__file__).resolve().parents[1]
_FLUID_JOB_LOCK=Lock()
MAX_MESH_BYTES=28*1024*1024
MAX_TETRA=90000
TIMEOUT_S=70

# Do not expose arbitrary Gmsh expressions or shell commands to user text.
PHYSICAL_TAGS={
    "upstream_open":101,
    "downstream_open":102,
    "lateral_farfield":103,
    "rotor_interface":104,
    "rotor_source_zone":201,
    "ambient_air_zone":202,
}


@dataclass(frozen=True)
class FluidDomainEvidence:
    model_kind: str
    cad_source_sha256: str
    fluid_mesh_sha256: str
    mesh_bytes: bytes
    diameter_mm: float
    outer_width_mm: float
    upstream_length_mm: float
    downstream_length_mm: float
    rotor_zone_radius_mm: float
    rotor_zone_height_mm: float
    volumes_mm3: dict[str,float]
    mesh_volume_mm3: float
    relative_volume_error: float
    tetrahedra: int
    nodes: int
    boundary_triangles: dict[str,int]
    patch_ids: dict[str,int]
    preview_points_mm: np.ndarray | None=None
    preview_faces: np.ndarray | None=None

    def as_dict(self) -> dict:
        return {
            "model_kind":self.model_kind,
            "cad_source_sha256":self.cad_source_sha256,
            "fluid_mesh_sha256":self.fluid_mesh_sha256,
            "msh_bytes":len(self.mesh_bytes),
            "diameter_mm":self.diameter_mm,
            "outer_width_mm":self.outer_width_mm,
            "upstream_length_mm":self.upstream_length_mm,
            "downstream_length_mm":self.downstream_length_mm,
            "rotor_zone_radius_mm":self.rotor_zone_radius_mm,
            "rotor_zone_height_mm":self.rotor_zone_height_mm,
            "volumes_mm3":self.volumes_mm3,
            "mesh_volume_mm3":self.mesh_volume_mm3,
            "relative_volume_error":self.relative_volume_error,
            "tetrahedra":self.tetrahedra,
            "nodes":self.nodes,
            "boundary_triangles":self.boundary_triangles,
            "patch_ids":self.patch_ids,
            "solver_status":"NOT_RUN_NO_CFD_VELOCITIES_OR_PRESSURES",
            "idealizations":[
                "Axial rotor source region, no explicit blade-fluid interface",
                "Freestanding farfield box, NOT a resolved nearby wall or mounted fan",
                "No fan curve or momentum source; no inlet/outlet velocity condition",
                "Tagged 3D fluid mesh only; NOT Navier-Stokes, convergence or physical validation",
            ],
        }


def _bounded_settings(request: EngineeringRequest, source: bytes) -> dict:
    if request.family.value!="wall_fan" or not isinstance(request.geometry,FanGeometry):
        raise ValueError("Actuator-volume mesh only supports the registered wall_fan family")
    if not request.concept_assumptions_confirmed:
        raise ValueError("Explicit consent to the labeled fan geometry assumptions required")
    if not request.analyses.fluid_cfd:
        raise ValueError("Request a CFD/airflow investigation before building a fluid mesh")
    if request.geometry.diameter_mm is None:
        raise ValueError("Explicit fan diameter required; no assumed size")
    D=float(request.geometry.diameter_mm)
    if not 100<=D<=800 or not math.isfinite(D):
        raise ValueError("Fan diameter outside bounded fluid-domain range")
    _validate_step(source)
    if len(source)>MAX_CAD_BYTES:
        raise ValueError("CAD STEP is too large for the interactive preprocessor")
    return {
        "diameter_mm":D,
        "source_sha256":sha256(source).hexdigest(),
        # Always document that the air box excludes nearby-wall modeling.
        "air_halfwidth_mm":1.5*D,
        "upstream_mm":1.0*D,
        "downstream_mm":2.5*D,
        "rotor_radius_mm":.5*D,
        "rotor_halfheight_mm":.15*D,
        "mesh_size_mm":max(45.,D/2.8),
    }


def _internal_worker(directory: Path) -> None:
    """Called only as a child process; parent Streamlit never loads libgmsh."""
    from .step_mesh import _require_gmsh, _gmsh_session
    source=directory/"source.step"
    settings=json.loads((directory/"input.json").read_text(encoding="utf-8"))
    blob=source.read_bytes()
    if sha256(blob).hexdigest()!=settings["source_sha256"]:
        raise ValueError("CAD STEP SHA-256 mismatch inside the native fluid worker")
    _validate_step(blob)
    D=float(settings["diameter_mm"])
    half=float(settings["air_halfwidth_mm"])
    up=float(settings["upstream_mm"])
    down=float(settings["downstream_mm"])
    rot_r=float(settings["rotor_radius_mm"])
    rot_h=float(settings["rotor_halfheight_mm"])
    size=float(settings["mesh_size_mm"])
    gmsh=_require_gmsh()
    with _gmsh_session(gmsh):
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.model.add("Audit source CAD first")
        gmsh.model.occ.importShapes(str(source))
        gmsh.model.occ.synchronize()
        n_solid=len(gmsh.model.getEntities(3))
        if not 2<=n_solid<=30:
            raise ValueError("The source CAD is not a plausible bounded multi-solid fan assembly")
        # The STEP import proves provenance.  Rotor blades are intentionally
        # NOT embedded in the fluid mesh; modeling them requires a body-fitted
        # rotating zone and a turbulence/moving-mesh solver.
        gmsh.clear()
        gmsh.model.add("Idealized fan actuator-zone AIR volume")
        occ=gmsh.model.occ
        outer=occ.addBox(-half,-half,-up,2*half,2*half,up+down)
        rotor=occ.addCylinder(0,0,-rot_h,0,0,2*rot_h,rot_r)
        occ.fragment([(3,outer)],[(3,rotor)])
        occ.synchronize()
        entities=gmsh.model.getEntities(3)
        if len(entities)!=2:
            raise ValueError(
                f"Expected exactly two conforming fluid volume zones; got {len(entities)}"
            )
        expected_rotor=math.pi*rot_r**2*(2*rot_h)
        occ_mass={tag:float(occ.getMass(3,tag)) for _,tag in entities}
        rotor_tag=min(occ_mass,key=lambda tag:abs(occ_mass[tag]-expected_rotor))
        ambient_tag=next(tag for tag in occ_mass if tag!=rotor_tag)
        if abs(occ_mass[rotor_tag]-expected_rotor)/expected_rotor>.005:
            raise ValueError("Rotor source region CAD volume not as specified")
        expected_outer=(2*half)**2*(up+down)
        relative_boolean=abs(sum(occ_mass.values())-expected_outer)/expected_outer
        if relative_boolean>.005:
            raise ValueError("Air domain is not watertight or volume-conserving")
        for name,tag in (("rotor_source_zone",rotor_tag),
                         ("ambient_air_zone",ambient_tag)):
            marker=PHYSICAL_TAGS[name]
            gmsh.model.addPhysicalGroup(3,[tag],marker)
            gmsh.model.setPhysicalName(3,marker,name)

        patches={"upstream_open":[],"downstream_open":[],
                 "lateral_farfield":[],"rotor_interface":[]}
        eps=max(1e-5,D*1e-7)
        all_boundaries={tag for _,tag in gmsh.model.getBoundary(entities,combined=False,oriented=False)}
        for surface_tag in all_boundaries:
            upper,_=gmsh.model.getAdjacencies(2,surface_tag)
            bbox=gmsh.model.getBoundingBox(2,surface_tag)
            count_adj=len({int(x) for x in upper})
            if count_adj==2:
                name="rotor_interface"
            elif count_adj!=1:
                raise ValueError(
                    f"Unexpected fluid-domain surface adjacency {count_adj} for {surface_tag}"
                )
            elif abs(bbox[2]+up)<eps and abs(bbox[5]+up)<eps:
                name="upstream_open"
            elif abs(bbox[2]-down)<eps and abs(bbox[5]-down)<eps:
                name="downstream_open"
            elif (abs(bbox[0]+half)<eps and abs(bbox[3]+half)<eps
                  or abs(bbox[0]-half)<eps and abs(bbox[3]-half)<eps
                  or abs(bbox[1]+half)<eps and abs(bbox[4]+half)<eps
                  or abs(bbox[1]-half)<eps and abs(bbox[4]-half)<eps):
                name="lateral_farfield"
            else:
                raise ValueError(f"Unclassified air boundary surface {surface_tag}: {bbox}")
            patches[name].append(surface_tag)

        if any(not tags for tags in patches.values()):
            raise ValueError("An air inlet/outlet/farfield/rotor-interface patch is absent")
        if sum(len(x) for x in patches.values())!=len(all_boundaries):
            raise AssertionError("Not all fluid-domain surfaces received physical tags")
        for name,tags in patches.items():
            marker=PHYSICAL_TAGS[name]
            gmsh.model.addPhysicalGroup(2,tags,marker)
            gmsh.model.setPhysicalName(2,marker,name)

        gmsh.option.setNumber("Mesh.MeshSizeMin",size*.75)
        gmsh.option.setNumber("Mesh.MeshSizeMax",size)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints",0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature",0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary",0)
        gmsh.option.setNumber("Mesh.MshFileVersion",2.2)
        gmsh.option.setNumber("Mesh.Binary",0)
        gmsh.model.mesh.generate(3)
        types,elem_tags,conn=gmsh.model.mesh.getElements(3)
        if any(int(typ)!=4 for typ in types):
            raise ValueError("Fluid mesh has unexpected non-tetrahedral volume elements")
        n_tets=sum(len(tags) for tags in elem_tags)
        if not 100<=n_tets<=MAX_TETRA:
            raise ValueError(f"3D fluid tetrahedral mesh limit exceeded: {n_tets}")
        node_tags,xyz,_=gmsh.model.mesh.getNodes()
        nodes=np.asarray(xyz,dtype=float).reshape(-1,3)
        mapping={int(tag):idx for idx,tag in enumerate(node_tags)}
        tet_nodes=np.asarray(conn[0],dtype=np.int64).reshape(-1,4)
        ids=np.fromiter(
            (mapping[int(key)] for key in tet_nodes.flat),
            dtype=np.int64,count=tet_nodes.size,
        ).reshape(-1,4)
        v=nodes[ids]
        triple=np.einsum(
            "ij,ij->i", np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]),v[:,3]-v[:,0]
        )
        mesh_volume=float(np.abs(triple).sum()/6)
        if not np.isfinite(mesh_volume) or mesh_volume<=0:
            raise ValueError("Non-finite or empty true tetrahedron mesh volume")
        relative_error=abs(mesh_volume-expected_outer)/expected_outer
        if relative_error>.08:
            raise ValueError(
                f"Curved/tetra fluid mesh volume differs from CAD domain by {relative_error:.2%}"
            )
        counts={}
        for name,tags in patches.items():
            n=0
            for tag in tags:
                ty,el,_=gmsh.model.mesh.getElements(2,tag)
                n+=sum(len(ids) for tt,ids in zip(ty,el) if int(tt)==2)
            if n<2:
                raise ValueError(f"No real meshed boundary triangles on '{name}'")
            counts[name]=n
        gmsh.write(str(directory/"tagged_air_volume.msh"))
        # Preview ONLY the physical rotor-interface triangulation, no invented
        # CFD pressure or velocity field.
        flat_faces=[]
        for tag in patches["rotor_interface"]:
            t,_,data=gmsh.model.mesh.getElements(2,tag)
            for typ,connectivity in zip(t,data):
                if int(typ)==2:
                    flat_faces.extend([mapping[int(v)] for v in connectivity])
        triangles=np.asarray(flat_faces,dtype=np.int32).reshape(-1,3)
        np.savez_compressed(
            directory/"rotor_surface.npz",
            points_mm=nodes,faces=triangles,
        )
        (directory/"evidence.json").write_text(json.dumps({
            "diameter_mm":D,"outer_width_mm":2*half,
            "upstream_length_mm":up,"downstream_length_mm":down,
            "rotor_zone_radius_mm":rot_r,"rotor_zone_height_mm":2*rot_h,
            "cad_source_sha256":settings["source_sha256"],
            "volumes_mm3":{
                "rotor_source_zone":occ_mass[rotor_tag],
                "ambient_air_zone":occ_mass[ambient_tag],
            },
            "mesh_volume_mm3":mesh_volume,"relative_volume_error":relative_error,
            "tetrahedra":n_tets,"nodes":len(nodes),
            "boundary_triangles":counts,"patch_ids":PHYSICAL_TAGS,
        },indent=2),encoding="utf-8")


def generate_fan_air_domain_safely(
    request: EngineeringRequest,source_step:bytes,
) -> FluidDomainEvidence:
    """Independent 3D air mesh, not CFD, with user-confirmed concept scope."""
    settings=_bounded_settings(request,source_step)
    if not _FLUID_JOB_LOCK.acquire(blocking=False):
        raise RuntimeError("A 3D air-domain mesh is already running")
    try:
        with tempfile.TemporaryDirectory(prefix="ff_air_domain_") as tmp:
            folder=Path(tmp)
            (folder/"source.step").write_bytes(source_step)
            (folder/"input.json").write_text(json.dumps(settings),encoding="utf-8")
            env=os.environ.copy()
            for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS",
                        "MKL_NUM_THREADS","VECLIB_MAXIMUM_THREADS"):
                env[key]="1"
            try:
                proc=subprocess.run(
                    [sys.executable,"-m","forceforge.fluid_domain",
                     "--worker",str(folder)],
                    cwd=_ROOT,env=env,stdin=subprocess.DEVNULL,
                    capture_output=True,text=True,timeout=TIMEOUT_S,check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "Native 3D air-volume meshing timed out; Streamlit stays alive"
                ) from exc
            if proc.returncode:
                detail=(proc.stderr or proc.stdout or "native crash")[-1700:]
                raise RuntimeError(
                    f"3D air volume meshing failed ({proc.returncode}): {detail}"
                )
            mesh=(folder/"tagged_air_volume.msh").read_bytes()
            if not 300<len(mesh)<=MAX_MESH_BYTES:
                raise ValueError("Tagged air mesh file size outside bounds")
            metadata=json.loads((folder/"evidence.json").read_text(encoding="utf-8"))
            if metadata["cad_source_sha256"]!=settings["source_sha256"]:
                raise ValueError("Air-domain mesh linked to wrong input STEP")
            with np.load(folder/"rotor_surface.npz",allow_pickle=False) as a:
                points=a["points_mm"].copy()
                faces=a["faces"].copy()
            return FluidDomainEvidence(
                model_kind="CONCEPT_FAN_TWO_ZONE_ACTUATOR_DOMAIN_NOT_CFD",
                cad_source_sha256=metadata["cad_source_sha256"],
                fluid_mesh_sha256=sha256(mesh).hexdigest(),
                mesh_bytes=mesh,diameter_mm=metadata["diameter_mm"],
                outer_width_mm=metadata["outer_width_mm"],
                upstream_length_mm=metadata["upstream_length_mm"],
                downstream_length_mm=metadata["downstream_length_mm"],
                rotor_zone_radius_mm=metadata["rotor_zone_radius_mm"],
                rotor_zone_height_mm=metadata["rotor_zone_height_mm"],
                volumes_mm3=metadata["volumes_mm3"],
                mesh_volume_mm3=metadata["mesh_volume_mm3"],
                relative_volume_error=metadata["relative_volume_error"],
                tetrahedra=metadata["tetrahedra"],nodes=metadata["nodes"],
                boundary_triangles=metadata["boundary_triangles"],
                patch_ids=metadata["patch_ids"],
                preview_points_mm=points,preview_faces=faces,
            )
    finally:
        _FLUID_JOB_LOCK.release()


if __name__=="__main__":
    if len(sys.argv)!=3 or sys.argv[1]!="--worker":
        raise SystemExit("Internal bounded Gmsh air-domain worker")
    try:
        _internal_worker(Path(sys.argv[2]))
    except Exception:
        import traceback
        traceback.print_exc()
        raise SystemExit(2)
