"""2D truss linear-elastic, small-deformation finite element solver.

Units: m, N, Pa, kg. Members are pin-jointed axial elements.
Euler buckling is only a screening estimate for ideal pin-pinned round bars.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Material:
    E_pa: float = 200e9
    density_kg_m3: float = 7850.0
    yield_pa: float = 250e6


@dataclass
class Truss:
    nodes_m: np.ndarray  # shape (n,2)
    elements: tuple[tuple[int, int], ...]
    supports: tuple[tuple[int, bool, bool], ...]  # (node, fix_x, fix_y)
    forces_n: np.ndarray  # shape (n,2)
    areas_m2: np.ndarray  # shape (n_members,)
    material: Material
    topology: str = "Triangle"


@dataclass
class Result:
    disp_m: np.ndarray
    reactions_n: np.ndarray
    force_n: np.ndarray
    stress_pa: np.ndarray
    buckling_critical_n: np.ndarray
    lengths_m: np.ndarray
    mass_kg: float
    condition_number: float

    @property
    def max_disp_m(self) -> float:
        return float(np.linalg.norm(self.disp_m, axis=1).max())

    @property
    def max_stress_pa(self) -> float:
        return float(np.abs(self.stress_pa).max())


def solve(truss: Truss, *, e_factor: float = 1.0, area_factor: float = 1.0, load_factor: float = 1.0) -> Result:
    nodes = np.asarray(truss.nodes_m, dtype=float)
    areas = np.asarray(truss.areas_m2, dtype=float) * area_factor
    forces = np.asarray(truss.forces_n, dtype=float) * load_factor
    if nodes.ndim != 2 or nodes.shape[1] != 2 or forces.shape != nodes.shape:
        raise ValueError("nodes/forces must both be (n_nodes, 2)")
    if len(areas) != len(truss.elements) or np.any(areas <= 0):
        raise ValueError("Need positive area for every truss element")
    E = truss.material.E_pa * e_factor
    if E <= 0 or any(v <= 0 for v in (e_factor, area_factor, load_factor)):
        raise ValueError("All scenario scale factors must be positive")

    ndof = 2 * len(nodes)
    K = np.zeros((ndof, ndof), dtype=float)
    lengths = np.zeros(len(truss.elements), dtype=float)
    cos_sin = []
    for idx, (a, b) in enumerate(truss.elements):
        diff = nodes[b] - nodes[a]
        length = float(np.linalg.norm(diff))
        if length < 1e-12:
            raise ValueError("Zero-length member")
        c, s = diff / length
        lengths[idx] = length
        cos_sin.append((c, s))
        d = np.array([c, s, -c, -s])
        ke = E * areas[idx] / length * np.outer(d, d)
        ids = np.array([2*a, 2*a+1, 2*b, 2*b+1], dtype=int)
        K[np.ix_(ids, ids)] += ke

    fixed = set()
    for node, fx, fy in truss.supports:
        if fx:
            fixed.add(2 * node)
        if fy:
            fixed.add(2 * node + 1)
    free = np.array([idx for idx in range(ndof) if idx not in fixed], dtype=int)
    if len(free) == 0:
        raise ValueError("No free degrees of freedom")
    reduced = K[np.ix_(free, free)]
    cond = float(np.linalg.cond(reduced))
    if not np.isfinite(cond) or cond > 1e12:
        raise ValueError(f"Unstable, ill-conditioned or singular structure (cond={cond:.2g})")
    u = np.zeros(ndof)
    f = forces.flatten()
    u[free] = np.linalg.solve(reduced, f[free])
    reactions = K @ u - f

    N = np.zeros(len(truss.elements))
    stress = np.zeros(len(truss.elements))
    pcr = np.zeros(len(truss.elements))
    for idx, (a, b) in enumerate(truss.elements):
        c, s = cos_sin[idx]
        axial_extension = np.array([-c, -s, c, s]) @ u[[2*a, 2*a+1, 2*b, 2*b+1]]
        N[idx] = E * areas[idx] / lengths[idx] * axial_extension
        stress[idx] = N[idx] / areas[idx]
        # Solid circular bar; pin-pin effective length factor K=1.
        second_moment = areas[idx] ** 2 / (4 * np.pi)
        pcr[idx] = np.pi**2 * E * second_moment / lengths[idx]**2
    mass = float(np.dot(areas, lengths) * truss.material.density_kg_m3)
    return Result(
        disp_m=u.reshape(-1, 2), reactions_n=reactions.reshape(-1, 2),
        force_n=N, stress_pa=stress, buckling_critical_n=pcr,
        lengths_m=lengths, mass_kg=mass, condition_number=cond,
    )
