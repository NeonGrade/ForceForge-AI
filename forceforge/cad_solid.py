"""3D elastic tetra10 FEM for an independently imported STEP-derived mesh.

Geometry comes from CAD BRep; boundary conditions and material are explicit
user assumptions. Source geometry is not experimental static validation.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from .solid3d import _B, _D, _surface, _von_mises, GAUSS, _quadratic_connectivity
from .step_mesh import CadMesh

@dataclass(frozen=True)
class CadLoad:
    force_n: float=250.
    force_axis: int=0
    force_sign: int=1
    boundary_axis: int=2
    E_pa: float=200e9
    nu: float=.29
    density: float=8190.
    yield_pa: float=900e6
    def __post_init__(self):
        if not 0<=self.force_n<=50000:
            raise ValueError('Applied force out of interactive range')
        if self.force_axis not in (0,1,2) or self.boundary_axis not in (0,1,2):
            raise ValueError('Invalid coordinate axis')
        if self.force_axis==self.boundary_axis:
            raise ValueError('Load must be transverse to base-to-tip axis')
        if self.force_sign not in (-1,1):
            raise ValueError('Load sign must be +1 or -1')
        if not self.E_pa>0 or not 0<self.nu<.49 or self.density<=0 or self.yield_pa<=0:
            raise ValueError('Invalid elastic material data')

@dataclass
class CADFEAResult:
    mesh: CadMesh
    load: CadLoad
    nodes_m: np.ndarray
    tets10: np.ndarray
    displacements_m: np.ndarray
    von_mises_pa: np.ndarray
    stress_voigt_pa: np.ndarray
    surface_faces: np.ndarray
    surface_element_ids: np.ndarray
    support_reaction_n: np.ndarray
    relative_reaction_residual: float
    load_face_area_m2: float
    average_tip_displacement_m: float
    max_displacement_m: float
    mass_kg: float
    sampled_peak_stress_pa: float
    strain_energy_j: float
    @property
    def tip_mm(self):
        return abs(self.average_tip_displacement_m)*1e3
    @property
    def peak_von_mises_mpa(self):
        return self.sampled_peak_stress_pa/1e6

def solve_cad_mesh(mesh:CadMesh, case:CadLoad=CadLoad()) -> CADFEAResult:
    corners=mesh.nodes_m
    tetra=mesh.tets4
    if len(tetra)>5000:
        raise ValueError('Volume solver cap is 5000 input tets')
    points, cells, edges=_quadratic_connectivity(corners,tetra)
    D=_D(case.E_pa,case.nu)
    ndof=3*len(points)
    rowparts=[];colparts=[];valparts=[]
    for nodes in cells:
        xyz=points[nodes[:4]]
        local=np.zeros((30,30))
        for g in GAUSS:
            B,v=_B(xyz,np.array(g))
            local+=(v/4)*(B.T@D@B)
        idx=(3*nodes[:,None]+np.arange(3)).reshape(-1)
        rowparts.append(np.repeat(idx,30))
        colparts.append(np.tile(idx,30))
        valparts.append(local.reshape(-1))
    stiff=coo_matrix((np.concatenate(valparts),
                      (np.concatenate(rowparts),np.concatenate(colparts))),
                      shape=(ndof,ndof)).tocsr()
    faces,face_elem=_surface(tetra)
    axis=case.boundary_axis
    minimum,maximum=mesh.bbox_m[:,axis]
    tol=max(1e-9,(maximum-minimum)*1e-7)
    top=faces[np.all(np.abs(corners[faces,axis]-maximum)<tol,axis=1)]
    if not len(top):
        raise ValueError('No planar load-bearing facets on maximum boundary plane')
    support=np.flatnonzero(np.abs(points[:,axis]-minimum)<tol)
    if len(support)<3:
        raise ValueError('Insufficient fixed-base nodes on CAD minimum plane')
    areas=np.array([.5*np.linalg.norm(np.cross(*(corners[face[1:]]-corners[face[0]])))
                    for face in top])
    total_area=float(areas.sum())
    if total_area<=1e-14:
        raise ValueError('Top load face has negligible area')
    F=np.zeros(ndof)
    for face,area in zip(top,areas):
        for a,b in ((0,1),(1,2),(2,0)):
            key=tuple(sorted((int(face[a]),int(face[b]))))
            F[3*edges[key]+case.force_axis]+=case.force_sign*case.force_n*area/(3*total_area)
    applied=np.zeros(3)
    applied[case.force_axis]=case.force_sign*case.force_n
    if not np.allclose(F.reshape(-1,3).sum(axis=0),applied,atol=1e-7):
        raise AssertionError('Distributed traction does not sum to specified load')
    fixed=(3*support[:,None]+np.arange(3)).reshape(-1)
    isfree=np.ones(ndof,dtype=bool)
    isfree[fixed]=False
    u=np.zeros(ndof)
    u[isfree]=spsolve(stiff[isfree][:,isfree],F[isfree])
    if not np.isfinite(u).all():
        raise ValueError('Imported CAD FEA solution is not finite')
    reaction=(stiff@u-F).reshape(-1,3)[support].sum(axis=0)
    eqerror=float(np.linalg.norm(reaction+applied)/max(case.force_n,1.))
    if eqerror>1e-5:
        raise ValueError('Reaction equilibrium failed; check the mesh and support faces')
    mids=[];vm=[]
    for nodes in cells:
        xyz=points[nodes[:4]]
        local_u=u[(3*nodes[:,None]+np.arange(3)).reshape(-1)]
        B,_=_B(xyz,np.array([.25]*4))
        mids.append(D@(B@local_u))
        sampling=[]
        for g in GAUSS:
            Bi,_=_B(xyz,np.asarray(g))
            sampling.append(_von_mises(D@(Bi@local_u)))
        vm.append(max(sampling))
    node_u=u.reshape(-1,3)
    topnode=np.flatnonzero(np.abs(points[:,axis]-maximum)<tol)
    tip=float(np.mean(node_u[topnode,case.force_axis]))
    return CADFEAResult(
        mesh=mesh,load=case,nodes_m=points,tets10=cells,
        displacements_m=node_u,von_mises_pa=np.asarray(vm),stress_voigt_pa=np.asarray(mids),
        surface_faces=faces,surface_element_ids=face_elem,
        support_reaction_n=reaction,relative_reaction_residual=eqerror,
        load_face_area_m2=total_area,average_tip_displacement_m=tip,
        max_displacement_m=float(np.linalg.norm(node_u,axis=1).max()),
        mass_kg=case.density*mesh.mesh_volume_m3,
        sampled_peak_stress_pa=float(np.max(vm)),
        strain_energy_j=float(.5*u.dot(stiff@u))
    )
