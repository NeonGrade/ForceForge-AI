"""True 3D quadratic tetrahedral displacement-based linear elastic FEA.

This is a small, independent C3D10-style isotropic SOLID engine for a solid
rectangular cantilever benchmark. It is not a general STEP/BRep CAD importer
or an industrial-certified solver.

Length 120 mm, width 30 mm, thickness 12 mm by default. The geometry is
a parametric computational test specimen, NOT a measured laboratory sample.
The published Hannover 1524mm laboratory beam lives in the separate
modal and 1D beam validation pages.

Units: m, N, Pa, kg. 3 displacement DOFs / node.
Tetra10 stiffness integrated at four degree-2 exact barycentric quadrature
points. End traction integrated consistently over quadratic face elements.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from functools import lru_cache
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

EDGES=((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))
GAUSS=(
(.5854101966249685,.1381966011250105,.1381966011250105,.1381966011250105),
(.1381966011250105,.5854101966249685,.1381966011250105,.1381966011250105),
(.1381966011250105,.1381966011250105,.5854101966249685,.1381966011250105),
(.1381966011250105,.1381966011250105,.1381966011250105,.5854101966249685),
)


@dataclass(frozen=True)
class SolidCase:
    length_m: float=.12
    width_m: float=.030
    thickness_m: float=.012
    force_n: float=100.0
    E_pa: float=210e9
    nu: float=.30
    density: float=7850.0
    yield_pa: float=250e6
    nx: int=2
    ny: int=2
    nz: int=12

    def __post_init__(self):
        if min(self.length_m,self.width_m,self.thickness_m,self.E_pa,
               self.density,self.yield_pa)<=0:
            raise ValueError("Dimensions and material values must be positive")
        if not 0<self.nu<.49:
            raise ValueError("Poisson ratio must be between 0 and 0.49")
        if not 0<=self.force_n<=10000:
            raise ValueError("Tip transverse load must be in [0,10000] N")
        if not 1<=min(self.nx,self.ny,self.nz) and min(self.nx,self.ny,self.nz)>0:
            raise ValueError("Each mesh axis needs at least one division")
        if max(self.nx,self.ny,self.nz)>48:
            raise ValueError("Mesh too large for interactive prototype")


@dataclass
class SolidResult:
    case: SolidCase
    nodes_m: np.ndarray
    tets10: np.ndarray
    displacements_m: np.ndarray
    von_mises_pa: np.ndarray
    stress_voigt_pa: np.ndarray
    surface_faces: np.ndarray
    surface_element_ids: np.ndarray
    tip_displacement_m: float
    support_reaction_n: np.ndarray
    relative_reaction_residual: float
    mass_kg: float
    element_volumes_m3: np.ndarray

    @property
    def max_mises_mpa(self):
        return float(np.max(self.von_mises_pa)/1e6)

    @property
    def tip_displacement_mm(self):
        return float(abs(self.tip_displacement_m)*1000)

    @property
    def beam_reference_tip_mm(self):
        c=self.case
        I=c.width_m*c.thickness_m**3/12.
        return 1000*c.force_n*c.length_m**3/(3*c.E_pa*I)

    @property
    def beam_reference_error_pct(self):
        ref=self.beam_reference_tip_mm
        return 100*(self.tip_displacement_mm/ref-1) if ref>0 else 0.0


def _solid_nodes_and_tets(c: SolidCase):
    x=np.linspace(-c.width_m/2,c.width_m/2,c.nx+1)
    y=np.linspace(-c.thickness_m/2,c.thickness_m/2,c.ny+1)
    z=np.linspace(0,c.length_m,c.nz+1)
    def idx(i,j,k):
        return (k*(c.ny+1)+j)*(c.nx+1)+i
    nodes=np.array([(x[i],y[j],z[k])
        for k in range(c.nz+1)
        for j in range(c.ny+1)
        for i in range(c.nx+1)],float)
    tets=[]
    pattern=((0,1,2,6),(0,2,3,6),(0,3,7,6),
             (0,7,4,6),(0,4,5,6),(0,5,1,6))
    for k in range(c.nz):
        for j in range(c.ny):
            for i in range(c.nx):
                v=(idx(i,j,k),idx(i+1,j,k),idx(i+1,j+1,k),
                   idx(i,j+1,k),idx(i,j,k+1),idx(i+1,j,k+1),
                   idx(i+1,j+1,k+1),idx(i,j+1,k+1))
                for t in pattern:
                    tets.append(tuple(v[q] for q in t))
    return nodes,np.asarray(tets,int)


def _quadratic_connectivity(nodes,tets):
    points=nodes.tolist()
    edge_to_middle={}
    conn=[]
    for tet in tets:
        midpoint_ids=[]
        for i,j in EDGES:
            key=tuple(sorted((int(tet[i]),int(tet[j]))))
            if key not in edge_to_middle:
                edge_to_middle[key]=len(points)
                points.append(((nodes[key[0]]+nodes[key[1]])/2).tolist())
            midpoint_ids.append(edge_to_middle[key])
        conn.append(tuple(tet)+tuple(midpoint_ids))
    return np.array(points,float),np.array(conn,int),edge_to_middle


def _D(E,nu):
    lam=E*nu/((1+nu)*(1-2*nu))
    mu=E/(2*(1+nu))
    D=np.zeros((6,6))
    D[:3,:3]=lam
    D[np.arange(3),np.arange(3)]=lam+2*mu
    D[3,3]=D[4,4]=D[5,5]=mu
    return D


def _B(corners,lam):
    jac=(corners[1:]-corners[0]).T
    det=float(np.linalg.det(jac))
    volume=abs(det)/6.0
    if volume<=1e-18:
        raise ValueError("Degenerate tetrahedral element")
    grads=np.zeros((4,3))
    grads[1:]=np.linalg.inv(jac)
    grads[0]=-grads[1:].sum(axis=0)
    dg=np.zeros((10,3))
    for k in range(4):
        dg[k]=(4*lam[k]-1)*grads[k]
    for k,(a,b) in enumerate(EDGES):
        dg[4+k]=4*(lam[a]*grads[b]+lam[b]*grads[a])
    B=np.zeros((6,30))
    for k,(dx,dy,dz) in enumerate(dg):
        p=3*k
        B[0,p]=dx
        B[1,p+1]=dy
        B[2,p+2]=dz
        B[3,p]=dy;B[3,p+1]=dx
        B[4,p+1]=dz;B[4,p+2]=dy
        B[5,p]=dz;B[5,p+2]=dx
    return B,volume


def _surface(tets):
    faces={}
    for element,cell in enumerate(tets):
        for q in ((0,1,2),(0,1,3),(0,2,3),(1,2,3)):
            key=tuple(sorted(int(cell[i]) for i in q))
            if key in faces:
                faces[key]=-1
            else:
                faces[key]=element
    items=[(face,element) for face,element in faces.items() if element>=0]
    return np.asarray([i[0] for i in items],int),np.asarray([i[1] for i in items],int)


def _von_mises(sigma):
    sx,sy,sz,txy,tyz,txz=sigma
    return float(np.sqrt(((sx-sy)**2+(sy-sz)**2+(sz-sx)**2)/2+
                         3*(txy*txy+tyz*tyz+txz*txz)))


def solve_solid(c: SolidCase=SolidCase()) -> SolidResult:
    corners,tets=_solid_nodes_and_tets(c)
    points,conn,edges=_quadratic_connectivity(corners,tets)
    D=_D(c.E_pa,c.nu)
    size=3*len(points)
    I=[];J=[];vals=[];volumes=[]
    for element in conn:
        outer=points[element[:4]]
        local=np.zeros((30,30))
        for gauss in GAUSS:
            B,volume=_B(outer,np.array(gauss))
            local+=(volume/4.0)*(B.T@D@B)
        degrees=(3*element[:,None]+np.arange(3)).reshape(-1)
        I.extend(np.repeat(degrees,30))
        J.extend(np.tile(degrees,30))
        vals.extend(local.ravel())
        volumes.append(volume)
    stiffness=coo_matrix((vals,(I,J)),shape=(size,size)).tocsr()
    F=np.zeros(size)
    boundary,element_ids=_surface(tets)
    tip_faces=boundary[np.all(np.isclose(corners[boundary,2],c.length_m),axis=1)]
    tip_area=c.width_m*c.thickness_m
    for face in tip_faces:
        a,b,d=corners[face]
        area=float(np.linalg.norm(np.cross(b-a,d-a))/2)
        for u,v in ((0,1),(1,2),(2,0)):
            key=tuple(sorted((int(face[u]),int(face[v]))))
            # Exact uniform traction loading for a quadratic triangular face:
            # three corner shape functions integrate to zero; each mid-edge
            # shape function integrates to area/3.
            F[3*edges[key]+1]+=-c.force_n*area/(3*tip_area)
    if abs(F[1::3].sum()+c.force_n)>1e-7:
        raise AssertionError("Quadratic traction integration failed")
    support=np.where(np.isclose(points[:,2],0))[0]
    fixed=(3*support[:,None]+np.arange(3)).reshape(-1)
    free=np.ones(size,dtype=bool)
    free[fixed]=False
    u=np.zeros(size)
    u[free]=spsolve(stiffness[free][:,free],F[free])
    if not np.all(np.isfinite(u)):
        raise ValueError("Non-finite 3D solid solution")
    reactions=(stiffness@u-F).reshape(-1,3)
    reaction=reactions[support].sum(axis=0)
    residual=float(np.linalg.norm(reaction+np.array([0,-c.force_n,0]))/
                   max(1.,c.force_n))
    vm=[];stress=[]
    for tet in conn:
        B,_=_B(points[tet[:4]],np.array([.25]*4))
        dofs=(3*tet[:,None]+np.arange(3)).reshape(-1)
        sigma=D@(B@u[dofs])
        vm.append(_von_mises(sigma))
        stress.append(sigma)
    tip=np.isclose(points[:,2],c.length_m)
    tip_disp=float(u.reshape(-1,3)[tip,1].mean())
    return SolidResult(
        case=c,nodes_m=points,tets10=conn,
        displacements_m=u.reshape(-1,3),von_mises_pa=np.array(vm),
        stress_voigt_pa=np.array(stress),
        surface_faces=boundary,surface_element_ids=element_ids,
        tip_displacement_m=tip_disp,support_reaction_n=reaction,
        relative_reaction_residual=residual,
        mass_kg=float(c.density*np.sum(volumes)),
        element_volumes_m3=np.asarray(volumes)
    )


def surface_figure(r: SolidResult, *, deformation_scale: float=60,
                   stress_cmax_mpa: float|None=None):
    """Display genuine 3D volumetric-element von Mises data on external facets.

    Each visible triangle takes the stress recovered at its adjacent quadratic
    volume element centroid. This is a discontinuous elementwise FE stress
    display, not a smoothed CAD illustration.
    """
    import plotly.graph_objects as go
    # Boundary facets are from tetra corner nodes; each triangle is duplicated
    # so its stress remains an actual element stress rather than interpolated.
    faces=r.surface_faces
    tris=r.nodes_m[faces]
    u=r.displacements_m[faces]
    scale=1000.0
    position=(tris+deformation_scale*u).reshape(-1,3)*scale
    per_face_mpa=r.von_mises_pa[r.surface_element_ids]/1e6
    intensity=np.repeat(per_face_mpa,3)
    cmax=float(max(np.max(intensity),1e-12) if stress_cmax_mpa is None
               else stress_cmax_mpa)
    if cmax+1e-8<np.max(intensity):
        raise ValueError("Shared stress cmax would clip actual solid stress")
    nelem=len(faces)
    figure=go.Figure(data=[go.Mesh3d(
        x=position[:,0],y=position[:,1],z=position[:,2],
        i=np.arange(nelem)*3,j=np.arange(nelem)*3+1,
        k=np.arange(nelem)*3+2,intensity=intensity,
        colorscale="Turbo",cmin=0,cmax=cmax,
        flatshading=True,opacity=1,
        lighting=dict(ambient=.7,diffuse=.55),
        colorbar=dict(title="von Mises (MPa)",len=.77,thickness=17)
    )])
    figure.update_layout(
        height=590,template="plotly_white",
        margin=dict(l=0,r=0,t=35,b=0),
        title=f"3D tetra10 SOLID FEA · {len(r.tets10)} volume elements",
        scene=dict(aspectmode="data",
            xaxis_title="Width X (mm)",yaxis_title="Thickness Y (mm)",
            zaxis_title="Length Z (mm)",
            camera=dict(eye=dict(x=1.6,y=1.7,z=.8)))
    )
    return figure
