"""Verified static bending FEM for the published Hannover 1.524-m steel beam.

Uses an Euler-Bernoulli 2 DOF/node bending element, with stepped rectangular
thickness, and reconstructs its axial bending-stress field on a 3D surface.
This is a 1D BEAM finite element solver with 3D SURFACE postprocessing,
NOT a 3D solid FEA or independently measured static stress experiment.

Physical source: Thurn et al. (2026), DOI: 10.5194/wes-11-3359-2026.
Section dimensions reconstructed from published article, CC BY 4.0.
SI units: N, m, Pa, kg.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import numpy as np

LENGTH_M = 1.524
WIDTH_M = .030
NOMINAL_THICKNESS_M = .0052
GAUGE_THICKNESS_M = .0050
GAUGE_REGIONS_M = ((.363, .423), (.768, .828))


@dataclass(frozen=True)
class StaticCase:
    force_n: float = .15
    thickness_ratio: float = 1.0
    e_pa: float = 210e9  # assumption, NOT measured by experiment
    rho_kg_m3: float = 7850.0  # assumption, NOT measured by experiment
    yield_pa: float = 250e6  # illustrative, NOT measured by experiment
    displacement_limit_mm: float = 2.0  # illustrative service limit
    n_nominal_elements: int = 84

    def __post_init__(self):
        if not 0 <= self.force_n <= 100:
            raise ValueError('transverse tip force must be in [0, 100] N')
        if not .65 <= self.thickness_ratio <= 2.0:
            raise ValueError('thickness ratio must be 0.65 to 2.0')
        if min(self.e_pa, self.rho_kg_m3, self.yield_pa, self.displacement_limit_mm) <= 0:
            raise ValueError('material data and limits must be positive')
        if not 8 <= self.n_nominal_elements <= 300:
            raise ValueError('n_nominal_elements must be 8 to 300')


@dataclass
class StaticResult:
    z_m: np.ndarray
    dofs: np.ndarray  # transverse u_x, theta_y at nodes (sign convention)
    support_reaction_n: float
    support_reaction_nm: float
    tip_mm: float
    stress_max_mpa: float
    mass_kg: float
    stress_utilization: float
    displacement_utilization: float
    governing_utilization: float
    relative_equilibrium_residual: float
    case: StaticCase


def thickness_at(z_m: float | np.ndarray, ratio: float = 1.0) -> float | np.ndarray:
    z=np.asarray(z_m)
    values=np.full_like(z, NOMINAL_THICKNESS_M*ratio, dtype=float)
    for a,b in GAUGE_REGIONS_M:
        values=np.where((z > a+1e-12)&(z < b-1e-12), GAUGE_THICKNESS_M*ratio, values)
    return float(values) if values.ndim==0 else values


def _mesh(case: StaticCase) -> np.ndarray:
    stations=np.linspace(0,LENGTH_M,case.n_nominal_elements+1)
    for a,b in GAUGE_REGIONS_M:
        stations=np.r_[stations,a,b]
    return np.unique(stations)


def _local(EI: float, span: float) -> np.ndarray:
    q=EI/span**3
    return q*np.array([
        [12,6*span,-12,6*span],
        [6*span,4*span**2,-6*span,2*span**2],
        [-12,-6*span,12,-6*span],
        [6*span,2*span**2,-6*span,4*span**2],
    ],dtype=float)


def solve_static(case: StaticCase = StaticCase()) -> StaticResult:
    stations=_mesh(case)
    N=len(stations)
    K=np.zeros((2*N,2*N),dtype=float)
    mass=0.0
    for e in range(N-1):
        mid=(stations[e]+stations[e+1])/2
        span=stations[e+1]-stations[e]
        t=thickness_at(mid,case.thickness_ratio)
        I=WIDTH_M*t**3/12
        k=_local(case.e_pa*I,span)
        indices=np.arange(2*e,2*e+4)
        K[np.ix_(indices,indices)]+=k
        mass+=case.rho_kg_m3*WIDTH_M*t*span
    F=np.zeros(2*N)
    F[-2]=case.force_n
    u=np.zeros(2*N)
    u[2:]=np.linalg.solve(K[2:,2:],F[2:])
    R=K@u-F
    tip_mm=float(u[-2]*1000)
    # Euler Bernoulli maximum extreme fibre stress along the beam's surface.
    sample=np.r_[stations,(stations[:-1]+stations[1:])/2]
    t=thickness_at(sample,case.thickness_ratio)
    moment=np.abs(case.force_n*(LENGTH_M-sample))
    stress=moment*(t/2)/(WIDTH_M*t**3/12)
    stress_max=float(np.max(stress))
    force_residual=abs(R[0]+case.force_n)/max(case.force_n,1e-14)
    moment_residual=abs(R[1]+case.force_n*LENGTH_M)/max(case.force_n*LENGTH_M,1e-14)
    return StaticResult(
        z_m=stations,dofs=u.reshape(-1,2),
        support_reaction_n=float(R[0]),support_reaction_nm=float(R[1]),
        tip_mm=tip_mm,stress_max_mpa=stress_max/1e6,
        mass_kg=mass,
        stress_utilization=stress_max/case.yield_pa,
        displacement_utilization=abs(tip_mm)/case.displacement_limit_mm,
        governing_utilization=max(stress_max/case.yield_pa,abs(tip_mm)/case.displacement_limit_mm),
        relative_equilibrium_residual=max(force_residual,moment_residual),case=case,
    )


def displacement_at(result: StaticResult, z_m: np.ndarray | float) -> np.ndarray | float:
    locations=np.asarray(z_m,dtype=float)
    flat=np.clip(locations.ravel(),0,LENGTH_M)
    idx=np.minimum(np.searchsorted(result.z_m,flat,side='right')-1,len(result.z_m)-2)
    s=result.z_m[idx+1]-result.z_m[idx]
    x=(flat-result.z_m[idx])/s
    h1=1-3*x*x+2*x*x*x
    h2=s*(x-2*x*x+x*x*x)
    h3=3*x*x-2*x*x*x
    h4=s*(-x*x+x*x*x)
    val=h1*result.dofs[idx,0]+h2*result.dofs[idx,1]+h3*result.dofs[idx+1,0]+h4*result.dofs[idx+1,1]
    return float(val[0]) if locations.ndim==0 else val.reshape(locations.shape)


def axial_stress_at(result: StaticResult,z_m: np.ndarray,x_m: np.ndarray) -> np.ndarray:
    z=np.asarray(z_m,dtype=float)
    x=np.asarray(x_m,dtype=float)
    t=thickness_at(z,result.case.thickness_ratio)
    I=WIDTH_M*t**3/12
    return -result.case.force_n*(LENGTH_M-z)*x/I  # signed axial bending stress, Pa


def redesign(case: StaticCase, ratios: tuple[float,...] | None=None) -> tuple[StaticResult|None,list[StaticResult]]:
    if ratios is None:
        ratios=(.7,.75,.8,.85,.9,.95,1.,1.05,1.1,1.15,1.2,1.3,1.4,1.55,1.7)
    choices=[solve_static(replace(case,thickness_ratio=float(r))) for r in ratios]
    feasible=[c for c in choices if c.governing_utilization <=1.0+1e-10]
    return (min(feasible,key=lambda r:r.mass_kg) if feasible else None),choices


def _surface_grid(nz:int=101,ratio:float=1.0):
    """High-resolution triangulated 3D section surface, derived from CAD dimensions.

    Returns vertex coords and triangle connectivity. Should not be mistaken for
    volumetric solid finite element mesh.
    """
    boundaries=[p for a,b in GAUGE_REGIONS_M for p in (a,b)]
    z=np.unique(np.r_[np.linspace(0,LENGTH_M,nz),boundaries])
    # x direction: thickness; y direction: 30 mm width
    corners=np.array([[-1,-1],[-1,1],[1,1],[1,-1]])
    verts=[]
    for level in z:
        thick=float(thickness_at(level,ratio))
        for u,v in corners:
            verts.append([u*thick/2,v*WIDTH_M/2,level])
    tris=[]
    for k in range(len(z)-1):
        for edge in range(4):
            a=4*k+edge;b=4*k+(edge+1)%4
            c=4*(k+1)+edge;d=4*(k+1)+(edge+1)%4
            tris.extend([(a,b,c),(c,b,d)])
    tris.extend([(0,2,1),(0,3,2)])
    top=(len(z)-1)*4
    tris.extend([(top,top+1,top+2),(top,top+2,top+3)])
    return np.asarray(verts,float),np.asarray(tris,int)


def plotly_surface(result: StaticResult, *, exaggeration: float=18,
                   normalized_stress_color: bool=False):
    import plotly.graph_objects as go
    vertices,faces=_surface_grid(ratio=result.case.thickness_ratio)
    z=vertices[:,2];local_x=vertices[:,0]
    # Deformed 3D surface: axial stress is from beam-section recovery, not 3D solid FE.
    vertices_deformed=vertices.copy()
    vertices_deformed[:,0]+=exaggeration*displacement_at(result,z)
    stress=np.abs(axial_stress_at(result,z,local_x))/1e6
    cmax=max(float(stress.max()),1e-9)
    scale=[[0.,'#10273b'],[.2,'#2675b4'],[.48,'#1ad8c7'],[.7,'#f6d54c'],[.86,'#fd6c4b'],[1.,'#ef43b4']]
    fmt=dict(i=faces[:,0],j=faces[:,1],k=faces[:,2],flatshading=False,
             lighting=dict(ambient=.56,diffuse=.68,roughness=.42,specular=.2))
    fig=go.Figure()
    fig.add_trace(go.Mesh3d(x=vertices[:,0]*1000,y=vertices[:,1]*1000,z=vertices[:,2]*1000,
                            color='#718b9d',opacity=.12,name='Unloaded geometry',
                            showlegend=True,showscale=False,**fmt))
    fig.add_trace(go.Mesh3d(x=vertices_deformed[:,0]*1000,y=vertices_deformed[:,1]*1000,
                            z=vertices_deformed[:,2]*1000,intensity=stress,colorscale=scale,
                            cmin=0,cmax=cmax,opacity=1.0,
                            name='FE-derived axial bending stress',showlegend=True,
                            colorbar=dict(title='|σzz| MPa',len=.70,thickness=16),**fmt))
    fig.update_layout(
        height=575,margin=dict(l=2,r=2,b=0,t=40),template='plotly_dark',
        paper_bgcolor='#091624',plot_bgcolor='#091624',
        title=dict(text=f'3D CAD surface + FE stress  ·  deformation ×{exaggeration:g}',font=dict(size=17)),
        scene=dict(aspectmode='data',xaxis_title='thickness X (mm)',
                   yaxis_title='width Y (mm)',zaxis_title='beam height Z (mm)',
                   bgcolor='#091624',
                   camera=dict(eye=dict(x=1.6,y=2.1,z=.95))),
        legend=dict(orientation='h',y=.02,x=.05)
    )
    return fig
