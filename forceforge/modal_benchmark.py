"""Physical benchmark model for a documented 1.524 m laboratory steel beam.

Numerical modal calculations are ours, not the Abaqus results from the paper.
The simplified 2D Euler-Bernoulli solver omits sensor point masses, Timoshenko
shear, mounting details and laboratory instrumentation calibration.

Source: Thurn et al., Wind Energy Science 11, 3359-3376 (2026),
DOI 10.5194/wes-11-3359-2026, CC BY 4.0.
Raw experiment and author Abaqus FE model: DOI 10.25835/lyav246d, CC BY 3.0.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.linalg import eigh
from scipy.optimize import brentq

LENGTH_M = 1.524
WIDTH_M = 0.03
THICKNESS_M = 0.0052
SANDED_THICKNESS_M = 0.0050
SANDED_HALF_LENGTH_M = 0.030
SENSOR_HEIGHTS_M = {
    "MP1": 1.462, "MP2": 1.098, "MP3": 0.829,
    "MP4": 0.798, "MP5": 0.393,
}
MEASURED_HZ = np.array([1.569, 10.389, 29.619])
PUBLISHED_FE_HZ = np.array([1.698, 10.775, 30.590])
PUBLISHED_MAC = np.array([0.9989, 0.9999, 0.9999])
AUTHOR = "Thurn, J., Jonscher, C., Hofmeister, B., Zorzi, G., & Rolfes, R. (2026)"
ARTICLE_DOI = "10.5194/wes-11-3359-2026"
DATASET_DOI = "10.25835/lyav246d"

@dataclass
class ModalResult:
    heights_m: np.ndarray
    frequencies_hz: np.ndarray
    transverse_shapes: np.ndarray
    rotations_rad: np.ndarray
    mass_kg: float
    base_stiffness_nm_rad: float | None
    K: np.ndarray
    M: np.ndarray
    free: np.ndarray
    density_kg_m3: float
    E_pa: float


def section_properties(z_m: float, reduce_gauges: bool = True) -> tuple[float,float]:
    h = THICKNESS_M
    if reduce_gauges and any(abs(z_m - SENSOR_HEIGHTS_M[name]) <= SANDED_HALF_LENGTH_M
                             for name in ("MP4", "MP5")):
        h = SANDED_THICKNESS_M
    area = WIDTH_M * h
    inertia = WIDTH_M * h**3 / 12.0
    return area, inertia


def element_matrices(length: float, E: float, I: float, rho: float, A: float):
    L = float(length)
    kl=(E*I/L**3)*np.array([[12,6*L,-12,6*L],
                              [6*L,4*L*L,-6*L,2*L*L],
                              [-12,-6*L,12,-6*L],
                              [6*L,2*L*L,-6*L,4*L*L]])
    ml=(rho*A*L/420)*np.array([[156,22*L,54,-13*L],
                                [22*L,4*L*L,13*L,-3*L*L],
                                [54,13*L,156,-22*L],
                                [-13*L,-3*L*L,-22*L,4*L*L]])
    return kl,ml


def build_matrices(n_elements: int = 32,
                   E_pa: float=210e9,
                   rho_kg_m3: float=7850.0,
                   base_stiffness_nm_rad: float | None=1e3,
                   reduce_gauges: bool=True):
    if not 8 <= n_elements <= 200:
        raise ValueError('Use between 8 and 200 beam elements')
    if E_pa <= 0 or rho_kg_m3 <= 0:
        raise ValueError('Young modulus and density must be positive')
    if base_stiffness_nm_rad is not None and base_stiffness_nm_rad <= 0:
        raise ValueError('Base stiffness must be positive, or None for a perfect clamp')
    z=np.linspace(0,LENGTH_M,n_elements+1)
    ndof=2*(n_elements+1)
    K=np.zeros((ndof,ndof)); M=np.zeros_like(K)
    mass=0.0
    for e in range(n_elements):
        Le=z[e+1]-z[e]; A,I=section_properties(.5*(z[e]+z[e+1]),reduce_gauges)
        kl,ml=element_matrices(Le,E_pa,I,rho_kg_m3,A)
        idx=[2*e,2*e+1,2*e+2,2*e+3]
        K[np.ix_(idx,idx)] += kl
        M[np.ix_(idx,idx)] += ml
        mass += rho_kg_m3*A*Le
    if base_stiffness_nm_rad is None:
        fixed={0,1}
    else:
        fixed={0}
        K[1,1]+=base_stiffness_nm_rad
    free=np.array([i for i in range(ndof) if i not in fixed])
    return z,K,M,free,mass


def solve_modes(*, n_elements: int=32,E_pa: float=210e9,
                rho_kg_m3: float=7850.0,
                base_stiffness_nm_rad: float | None=1e3,
                reduce_gauges: bool=True,
                count: int=3) -> ModalResult:
    z,K,M,free,mass=build_matrices(n_elements,E_pa,rho_kg_m3,
                                    base_stiffness_nm_rad,reduce_gauges)
    if count not in (1,2,3):
        raise ValueError('Count must be 1, 2 or 3')
    if len(free)<=count:
        raise ValueError('Too few unrestrained DOFs')
    vals,vecs=eigh(K[np.ix_(free,free)],M[np.ix_(free,free)],subset_by_index=[0,count-1])
    if not np.all(vals>0):
        raise ValueError('Negative or zero eigenvalue; verify model stiffness')
    modes=np.zeros((K.shape[0],count))
    modes[free,:]=vecs
    transverse=modes[0::2,:]
    for j in range(count):
        scale=np.max(np.abs(transverse[:,j]))
        if scale < 1e-12:
            raise ValueError('Purely rotational mode unexpectedly identified')
        sign=np.sign(transverse[-1,j])
        if sign==0: sign=1
        modes[:,j] *= sign / scale
    return ModalResult(z,np.sqrt(vals)/(2*np.pi),modes[0::2,:],
                       modes[1::2,:],mass,base_stiffness_nm_rad,K,M,free,
                       rho_kg_m3,E_pa)


def solve_static(*,tip_force_n: float=10., n_elements: int=32,
                E_pa: float=210e9,rho_kg_m3: float=7850.0,
                base_stiffness_nm_rad: float | None=1e3,
                reduce_gauges: bool=True):
    z,K,M,free,mass=build_matrices(n_elements,E_pa,rho_kg_m3,
                                    base_stiffness_nm_rad,reduce_gauges)
    F=np.zeros(K.shape[0]); F[-2]=tip_force_n
    u=np.zeros_like(F)
    u[free]=np.linalg.solve(K[np.ix_(free,free)],F[free])
    reactions=K@u-F
    return z,u[0::2],u[1::2],reactions,mass


def fit_base_stiffness(*,target_hz: float=float(MEASURED_HZ[0]),
                       n_elements: int=32,E_pa: float=210e9,
                       rho_kg_m3: float=7850.0,
                       reduce_gauges: bool=True):
    """Fit only the first measured eigenfrequency; modes 2/3 are held out."""
    def first_freq(log10_stiffness):
        return solve_modes(n_elements=n_elements,E_pa=E_pa,
                           rho_kg_m3=rho_kg_m3,
                           base_stiffness_nm_rad=10**log10_stiffness,
                           reduce_gauges=reduce_gauges,count=1).frequencies_hz[0]
    low,high=-1.0,9.0
    fmin,fmax=first_freq(low),first_freq(high)
    if not fmin < target_hz < fmax:
        raise ValueError(f'Target {target_hz} Hz is outside achievable [{fmin:.3f}, {fmax:.3f}] Hz')
    logk=brentq(lambda lk: first_freq(lk)-target_hz,low,high,xtol=1e-6)
    return 10**logk,solve_modes(n_elements=n_elements,E_pa=E_pa,
                                rho_kg_m3=rho_kg_m3,
                                base_stiffness_nm_rad=10**logk,
                                reduce_gauges=reduce_gauges,count=3)


def frequency_comparison(calculated_hz: np.ndarray) -> list[dict]:
    c=np.asarray(calculated_hz)
    if c.shape!=(3,) or not np.all(np.isfinite(c)):
        raise ValueError('Need exactly three computed natural frequencies')
    return [{"Mode":f"B{i+1}x","Measured (Hz)":float(MEASURED_HZ[i]),
             "Our reduced FEM (Hz)":float(c[i]),
             "Published Abaqus FE (Hz)":float(PUBLISHED_FE_HZ[i]),
             "Our error (%)":float(100*(c[i]/MEASURED_HZ[i]-1)),
             "Published FE error (%)":float(100*(PUBLISHED_FE_HZ[i]/MEASURED_HZ[i]-1))}
            for i in range(3)]


def holdout_mape(result: ModalResult)->float:
    """Mode-1 was used for support tuning. Validate modes 2 & 3 only."""
    return float(100*np.mean(np.abs(result.frequencies_hz[1:]/MEASURED_HZ[1:]-1)))


def prism_surface(heights_m: np.ndarray,
                  lateral_offset_m: np.ndarray,
                  *,section_width_m: float=WIDTH_M,
                  default_thickness_m: float=THICKNESS_M,
                  include_gauge_areas: bool=True):
    """Construct true-dimension rectangular beam prism for a 3D viewer.

    x is the measured lateral displacement direction, z is vertical; the
    original laboratory sensors and magnet are not modelled as solids.
    The renderer can exaggerate x separately, but geometry dimensions are real.
    """
    z=np.asarray(heights_m,dtype=float)
    w=np.asarray(lateral_offset_m,dtype=float)
    if z.ndim!=1 or z.shape!=w.shape or z.size<2:
        raise ValueError('Heights and lateral offset must be same-length 1D arrays')
    vertices=[]; intensity=[]; faces=[]
    for height,dx in zip(z,w):
        t=SANDED_THICKNESS_M if (include_gauge_areas and
           any(abs(height-SENSOR_HEIGHTS_M[p])<=SANDED_HALF_LENGTH_M
               for p in ('MP4','MP5'))) else default_thickness_m
        for x,y in [(-t/2,-section_width_m/2),(t/2,-section_width_m/2),
                    (t/2,section_width_m/2),(-t/2,section_width_m/2)]:
            vertices.append([x+dx,y,height])
            intensity.append(float(abs(dx)))
    for i in range(len(z)-1):
        for side in range(4):
            a=4*i+side; b=4*i+(side+1)%4
            c=4*(i+1)+(side+1)%4; d=4*(i+1)+side
            faces.extend([(a,b,c),(a,c,d)])
    faces.extend([(0,2,1),(0,3,2)])
    n=4*(len(z)-1)
    faces.extend([(n,n+1,n+2),(n,n+2,n+3)])
    return np.asarray(vertices),np.asarray(faces,dtype=int),np.asarray(intensity)


def read_abaqus_inp(text: str, *,max_nodes: int=150_000):
    """Read node positions and beam/truss connectivity for VIEW ONLY.

    Does not solve Abaqus assemblies or apply *Instance transforms, *Nset,
    materials, boundary conditions or element section definitions.
    """
    section=None
    nodes={};elements=[];element_types=set()
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('**'): continue
        if line.startswith('*'):
            heading=line.upper()
            section='node' if heading.startswith('*NODE') else ('element' if heading.startswith('*ELEMENT') else None)
            if section=='element':
                import re
                mt=re.search(r'TYPE\s*=\s*([A-Z0-9_-]+)',heading)
                if mt:element_types.add(mt.group(1))
            continue
        if section not in ('node','element'):continue
        tokens=[part.strip() for part in line.split(',') if part.strip()]
        if len(tokens)<2:continue
        try:
            idx=int(tokens[0])
            if section=='node':
                coords=[float(x) for x in tokens[1:4]]
                coords=(coords+[0.,0.,0.])[:3]
                nodes[idx]=coords
                if len(nodes)>max_nodes:raise ValueError('Model too large for this preview')
            else:
                indices=[int(v) for v in tokens[1:]]
                if len(indices)>=2: elements.append(tuple(indices))
        except (ValueError,OverflowError):
            continue
    return {'nodes':nodes,'elements':elements,'types':sorted(element_types),
            'node_count':len(nodes),'element_count':len(elements)}
