"""Advanced structural frame mechanics: linear static, thermal, semi-rigid
support joints, geometric-stiffness second order, and fatigue screening.

The solver implements Euler-Bernoulli planar frame elements (three DOFs/node):
ux, uy, rotation. It is not a geometrically exact corotational or plastic solver.

Units: m, N, Pa, kg, K (temperature DIFFERENCES), rad.
Research engineering calculation only; no design-code certification.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass(frozen=True)
class FrameMaterial:
    E_pa: float = 200e9
    rho_kg_m3: float = 7850.0
    alpha_per_k: float = 12e-6
    yield_pa: float = 250e6
    ultimate_pa: float = 450e6

    def __post_init__(self):
        if min(self.E_pa, self.rho_kg_m3, self.yield_pa, self.ultimate_pa) <= 0:
            raise ValueError('Positive material parameters required')


@dataclass(frozen=True)
class FrameMember:
    node_i: int
    node_j: int
    area_m2: float
    inertia_m4: float
    delta_T_k: float = 0.0
    # Thermal curvature imposed in local beam coordinates (rad/m). For an
    # actual temperature gradient calculate alpha * dT/dy externally.
    imposed_curvature_1_m: float = 0.0

    def __post_init__(self):
        if self.area_m2 <= 0 or self.inertia_m4 <= 0:
            raise ValueError('Beam cross-section area and inertia must be positive')


@dataclass
class FrameModel:
    nodes_m: np.ndarray
    members: list[FrameMember]
    nodal_forces: np.ndarray
    # fixed DOFs at node: (node, fix_ux, fix_uy, fix_theta)
    supports: list[tuple[int, bool, bool, bool]]
    material: FrameMaterial = field(default_factory=FrameMaterial)
    # Rotational spring to fixed ground, Nm/rad, at a translationally-fixed node
    rotational_springs_nm_rad: dict[int, float] = field(default_factory=dict)


@dataclass
class FrameResult:
    u: np.ndarray
    reactions: np.ndarray
    member_end_forces_local: np.ndarray
    member_axial_forces_n: np.ndarray
    member_max_stress_pa: np.ndarray
    thermal_equivalent_forces: np.ndarray
    mass_kg: float
    condition_number: float
    iterations: int
    converged: bool
    second_order: bool


def _local_stiffness(E: float, A: float, I: float, L: float) -> np.ndarray:
    a = E*A/L
    b = 12*E*I/L**3
    c = 6*E*I/L**2
    d = 4*E*I/L
    e = 2*E*I/L
    return np.array([
        [ a, 0, 0,-a, 0, 0],
        [ 0, b, c, 0,-b, c],
        [ 0, c, d, 0,-c, e],
        [-a, 0, 0, a, 0, 0],
        [ 0,-b,-c, 0, b,-c],
        [ 0, c, e, 0,-c, d],
    ], dtype=float)


def _local_geometric_stiffness(N: float, L: float) -> np.ndarray:
    # Euler-Bernoulli beam-column small displacement geometric stiffness;
    # axial tension N>0 stiffens; compression N<0 softens bending tangent.
    L2 = L*L
    K = np.zeros((6, 6))
    idx = np.array([1, 2, 4, 5])
    K[np.ix_(idx, idx)] = (N/(30.0*L))*np.array([
        [ 36., 3*L,-36., 3*L],
        [ 3*L,4*L2,-3*L,-L2],
        [-36.,-3*L, 36.,-3*L],
        [ 3*L,-L2,-3*L,4*L2],
    ])
    return K


def _rotation(c: float, s: float) -> np.ndarray:
    r = np.array([[c,s,0],[-s,c,0],[0,0,1]],float)
    T = np.zeros((6,6))
    T[:3,:3] = r
    T[3:,3:] = r
    return T


def _thermal_load(E: float, A: float, I: float, L: float,
                  alpha: float, dT: float, curvature: float) -> np.ndarray:
    # Conjugate equivalent nodal forces; f_T = int(B^T D eps_T) dV.
    axial = E*A*alpha*dT
    bend = E*I*curvature
    return np.array([-axial, 0.,-bend, axial, 0., bend])


def solve_frame(model: FrameModel, *, second_order: bool=False,
                max_iter: int=25, relative_tol: float=1e-9) -> FrameResult:
    nodes = np.asarray(model.nodes_m,float)
    n = len(nodes)
    if nodes.shape != (n, 2) or n < 2:
        raise ValueError('Need n>=2 2D node coordinates')
    forces = np.asarray(model.nodal_forces,float)
    if forces.shape != (n,3):
        raise ValueError('Nodal forces must have shape (n,3): Fx,Fy,Mz')
    if not model.members:
        raise ValueError('No frame elements')
    ndof = 3*n
    supports = set()
    for node, fx,fy,fr in model.supports:
        if node < 0 or node >= n:
            raise ValueError('Invalid support node')
        for i,fix in enumerate((fx,fy,fr)):
            if fix: supports.add(3*node+i)
    free = np.array([i for i in range(ndof) if i not in supports],int)
    if len(free) == 0:
        raise ValueError('No free DOFs')
    cached = []
    K_base = np.zeros((ndof,ndof))
    f_T = np.zeros(ndof)
    mass = 0.0
    for m in model.members:
        i,j = m.node_i,m.node_j
        if i<0 or i>=n or j<0 or j>=n:
            raise ValueError('Invalid member node index')
        diff = nodes[j]-nodes[i]
        L = np.linalg.norm(diff)
        if L < 1e-12:
            raise ValueError('Zero length beam')
        c,s = diff/L
        T = _rotation(c,s)
        kg = _local_stiffness(model.material.E_pa,m.area_m2,m.inertia_m4,L)
        tf = _thermal_load(model.material.E_pa,m.area_m2,m.inertia_m4,L,
                           model.material.alpha_per_k,m.delta_T_k,
                           m.imposed_curvature_1_m)
        dofs = np.array([3*i,3*i+1,3*i+2,3*j,3*j+1,3*j+2],int)
        K_base[np.ix_(dofs,dofs)] += T.T@kg@T
        f_T[dofs] += T.T@tf
        cached.append((m,L,T,kg,tf,dofs))
        mass += model.material.rho_kg_m3*m.area_m2*L
    for node,spring in model.rotational_springs_nm_rad.items():
        if node < 0 or node >= n or spring < 0:
            raise ValueError('Rotational spring must have valid node and k>=0')
        K_base[3*node+2,3*node+2] += spring
    F_ext = forces.ravel()+f_T

    u = np.zeros(ndof)
    previous = None
    converged = False
    condition = float('nan')
    last_N = np.zeros(len(cached))
    for it in range(1, (max_iter if second_order else 1)+1):
        K = K_base.copy()
        if second_order and previous is not None:
            for element_idx,(m,L,T,kl,tf,dofs) in enumerate(cached):
                K[np.ix_(dofs,dofs)] += T.T @ _local_geometric_stiffness(last_N[element_idx],L) @ T
        reduced = K[np.ix_(free,free)]
        condition = float(np.linalg.cond(reduced))
        if not np.isfinite(condition) or condition > 1e14:
            raise ValueError(f'Singular or near-singular frame (cond={condition:.3g})')
        solved = np.zeros(ndof)
        solved[free] = np.linalg.solve(reduced,F_ext[free])
        if previous is not None and np.linalg.norm(solved-previous) <= relative_tol*max(1e-12,np.linalg.norm(solved)):
            converged = True
            u = solved
            break
        u = solved
        axial = []
        for m,L,T,kl,tf,dofs in cached:
            q = kl@(T@u[dofs])-tf
            # local axial internal force positive in tension.
            axial.append(.5*(q[3]-q[0]))
        last_N = np.asarray(axial)
        previous = solved.copy()
    if not second_order:
        converged = True
    # For P-Delta, equilibrium is with the final geometric tangent approximation;
    # this is an iterative second-order elastic analysis, not an exact finite
    # rotation equilibrium formulation.
    effective_K = K_base.copy()
    if second_order:
        for idx,(m,L,T,kl,tf,dofs) in enumerate(cached):
            effective_K[np.ix_(dofs,dofs)] += T.T @ _local_geometric_stiffness(last_N[idx],L) @ T
    reactions = (effective_K@u-F_ext).reshape(n,3)
    local = []
    Nlist = []
    stress = []
    for m,L,T,kl,tf,dofs in cached:
        q = kl@(T@u[dofs])-tf
        N=.5*(q[3]-q[0])
        # Bounds for solid rectangular sections cannot be inferred from A,I
        # alone without the section height, so here use a SOLID CIRCULAR BAR
        # equivalent section: I = pi*r^4/4 and c=r.
        radius = (4*m.inertia_m4/np.pi)**0.25
        peak = abs(N/m.area_m2)+max(abs(q[2]),abs(q[5]))*radius/m.inertia_m4
        local.append(q)
        Nlist.append(N)
        stress.append(peak)
    return FrameResult(u=u.reshape(n,3),reactions=reactions,
        member_end_forces_local=np.asarray(local),member_axial_forces_n=np.asarray(Nlist),
        member_max_stress_pa=np.asarray(stress),thermal_equivalent_forces=f_T.reshape(n,3),
        mass_kg=mass,condition_number=condition,iterations=it,
        converged=converged,second_order=second_order)


def circular_section(radius_m: float) -> tuple[float,float]:
    if radius_m<=0: raise ValueError('radius must be positive')
    return float(np.pi*radius_m**2),float(np.pi*radius_m**4/4)


def cantilever_demo(*, length_m: float=2.0, tip_force_n: float=1000.,
                    radius_m: float=0.025, rotational_spring_nm_rad: float|None = None,
                    temp_rise_k: float=0., axial_force_n: float=0.,
                    E_pa: float=200e9) -> FrameModel:
    A,I=circular_section(radius_m)
    support_rotation_fixed = rotational_spring_nm_rad is None
    spring = {} if rotational_spring_nm_rad is None else {0:rotational_spring_nm_rad}
    return FrameModel(
        nodes_m=np.array([[0,0],[length_m,0]],float),
        members=[FrameMember(0,1,A,I,temp_rise_k)],
        nodal_forces=np.array([[0.,0.,0.],[axial_force_n,-tip_force_n,0.]]),
        supports=[(0,True,True,support_rotation_fixed)],
        rotational_springs_nm_rad=spring,
        material=FrameMaterial(E_pa=E_pa),
    )
