"""Small-strain isotropic tetrahedral solid FEA. Research/education prototype.

SI units throughout. Surface and volume meshing are performed by Gmsh OCC;
only first-order 4-node tetrahedra are accepted. No contact or fatigue.
"""
from dataclasses import dataclass
from pathlib import Path
import tempfile
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve


@dataclass
class Mesh:
    xyz: np.ndarray
    tet: np.ndarray


@dataclass
class Solution:
    displacement: np.ndarray
    von_mises_tet: np.ndarray
    von_mises_node: np.ndarray
    max_displacement: float
    reaction_sum: np.ndarray
    force_sum: np.ndarray


def make_box(length=0.1, width=0.02, height=0.02, mesh_size=0.01):
    """Generate a tetrahedral solid box, dimensions in metres."""
    if min(length, width, height, mesh_size) <= 0:
        raise ValueError("Dimensions and mesh size must be positive.")
    return _gmsh_mesh(None, mesh_size, (length, width, height))


def import_step(data: bytes, mesh_size=0.01):
    """Import STEP bytes with Gmsh OCC, mesh *all* solids; return Mesh in metres.

    Units: STEP coordinates are assumed millimetres (common CAD export).
    Caller must explicitly convert coordinates using a scale if different.
    """
    if not data or len(data) > 30_000_000:
        raise ValueError("STEP payload must be nonempty and <= 30 MB.")
    if mesh_size <= 0:
        raise ValueError("mesh_size must be positive.")
    return _gmsh_mesh(data, mesh_size)


def _gmsh_mesh(step_data, mesh_size, box=None):
    try:
        import gmsh
    except ImportError as exc:
        raise RuntimeError("Install optional 3D dependencies: pip install -r requirements-3d.txt") from exc
    if gmsh.isInitialized():
        raise RuntimeError("Gmsh already initialized; run meshing operations sequentially.")
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("forceforge_solid")
        if box is not None:
            gmsh.model.occ.addBox(0, 0, 0, *box)
        else:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "part.step"
                path.write_bytes(step_data)
                gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if not volumes:
            raise ValueError("STEP file has no closed solid volumes.")
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mesh_size)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_size)
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.model.mesh.generate(3)
        tags, coords, _ = gmsh.model.mesh.getNodes()
        xyz = np.asarray(coords, dtype=float).reshape(-1, 3)
        tag_to_index = {int(t): i for i, t in enumerate(tags)}
        types, _, node_groups = gmsh.model.mesh.getElements(3)
        tetra = []
        for kind, nodes in zip(types, node_groups):
            if int(kind) == 4:
                tetra.extend(np.asarray(nodes, dtype=np.int64).reshape(-1, 4).tolist())
        if not tetra:
            raise ValueError("No linear tetrahedral volume elements generated.")
        tet = np.asarray([[tag_to_index[int(t)] for t in row] for row in tetra], dtype=np.int64)
        return Mesh(xyz, tet)
    finally:
        gmsh.finalize()


def scale_mesh(mesh, coordinate_to_m):
    """Scale CAD coordinate units to SI metres, e.g. 0.001 for mm STEP."""
    if not np.isfinite(coordinate_to_m) or coordinate_to_m <= 0:
        raise ValueError("Coordinate scale must be positive and finite.")
    return Mesh(np.asarray(mesh.xyz, float) * coordinate_to_m, np.asarray(mesh.tet, int).copy())


def _elasticity(E, poisson):
    if E <= 0 or not (-1.0 < poisson < 0.5):
        raise ValueError("Require E > 0 and -1 < poisson < 0.5.")
    lam = E * poisson / ((1 + poisson) * (1 - 2 * poisson))
    mu = E / (2 * (1 + poisson))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[0, 0] += 2 * mu
    D[1, 1] += 2 * mu
    D[2, 2] += 2 * mu
    D[3:, 3:] = np.eye(3) * mu
    return D


def _tet_B(coords):
    M = np.column_stack((np.ones(4), coords))
    determinant = np.linalg.det(M)
    volume = abs(determinant) / 6
    if volume < 1e-20:
        raise ValueError("Degenerate or extremely small tetrahedron.")
    gradients = np.linalg.inv(M)[1:, :].T
    B = np.zeros((6, 12))
    for i, (gx, gy, gz) in enumerate(gradients):
        k = i * 3
        B[0, k] = gx
        B[1, k+1] = gy
        B[2, k+2] = gz
        B[3, k] = gy
        B[3, k+1] = gx
        B[4, k+1] = gz
        B[4, k+2] = gy
        B[5, k] = gz
        B[5, k+2] = gx
    return B, volume


def solve(mesh, E=200e9, poisson=0.3, force_n=1000.0, axis=0, face_tol=None):
    """Clamp min-axis face, distribute signed total force on max-axis face.

    These are simplified nodal BCs, NOT a pressure traction or contact model.
    Reactions and forces use global axes. Connected volumes only: disconnected
    subassemblies without constraints raise a singular-system error.
    """
    xyz = np.asarray(mesh.xyz, dtype=float)
    tet = np.asarray(mesh.tet, dtype=np.int64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or tet.ndim != 2 or tet.shape[1] != 4:
        raise ValueError("Expected N x 3 nodes and M x 4 tetrahedra.")
    if len(xyz) < 4 or not len(tet) or not np.isfinite(xyz).all() or not np.isfinite(force_n):
        raise ValueError("Invalid mesh or force.")
    if np.any(tet < 0) or np.any(tet >= len(xyz)):
        raise ValueError("Element node index outside mesh.")
    if axis not in (0, 1, 2):
        raise ValueError("axis must be 0, 1 or 2.")
    D = _elasticity(E, poisson)
    span = np.ptp(xyz[:, axis])
    tol = span * 0.005 if face_tol is None else face_tol
    if span <= 0 or tol < 0:
        raise ValueError("Invalid loading-axis span or tolerance.")
    fixed_nodes = np.where(xyz[:, axis] <= xyz[:, axis].min() + tol)[0]
    loaded_nodes = np.where(xyz[:, axis] >= xyz[:, axis].max() - tol)[0]
    if not len(fixed_nodes) or not len(loaded_nodes) or np.intersect1d(fixed_nodes, loaded_nodes).size:
        raise ValueError("Unable to identify distinct fixed and loaded faces.")
    n = len(xyz)
    I, J, V = [], [], []
    element_B = []
    for ids in tet:
        B, vol = _tet_B(xyz[ids])
        element_B.append(B)
        k = (B.T @ D @ B) * vol
        dofs = (ids[:, None] * 3 + np.arange(3)).reshape(-1)
        I.extend(np.repeat(dofs, 12))
        J.extend(np.tile(dofs, 12))
        V.extend(k.ravel())
    K = coo_matrix((V, (I, J)), shape=(3*n, 3*n)).tocsr()
    forces = np.zeros((n, 3), float)
    forces[loaded_nodes, axis] = force_n / len(loaded_nodes)
    f = forces.ravel()
    fixed = (fixed_nodes[:, None]*3 + np.arange(3)).ravel()
    free = np.setdiff1d(np.arange(3*n), fixed)
    if not len(free):
        raise ValueError("No free degrees of freedom.")
    import warnings
    from scipy.sparse.linalg import MatrixRankWarning
    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        u = np.zeros(3*n)
        try:
            u[free] = spsolve(K[free][:, free], f[free])
        except MatrixRankWarning as exc:
            raise ValueError("Singular stiffness: disconnected solids or insufficient supports.") from exc
    if not np.isfinite(u).all():
        raise ValueError("Non-finite displacement: singular/ill-conditioned stiffness.")
    vm = np.empty(len(tet))
    for i, (ids, B) in enumerate(zip(tet, element_B)):
        dofs = (ids[:, None]*3 + np.arange(3)).reshape(-1)
        s = D @ (B @ u[dofs])
        sx, sy, sz, txy, tyz, txz = s
        vm[i] = np.sqrt(max(0., .5*((sx-sy)**2 + (sy-sz)**2 + (sz-sx)**2) + 3*(txy*txy + tyz*tyz + txz*txz)))
    accum = np.zeros(n)
    counts = np.zeros(n)
    for ids, stress in zip(tet, vm):
        np.add.at(accum, ids, stress)
        np.add.at(counts, ids, 1)
    reactions = (K @ u - f).reshape(-1, 3)
    return Solution(u.reshape(-1, 3), vm, accum/np.maximum(counts, 1),
                    float(np.max(np.linalg.norm(u.reshape(-1,3), axis=1))),
                    reactions[fixed_nodes].sum(axis=0), forces.sum(axis=0))


def boundary_triangles(tets):
    """Extract exterior tetrahedral faces. Internal faces occur exactly twice."""
    faces = np.concatenate([tets[:, [0,1,2]], tets[:, [0,1,3]],
                            tets[:, [0,2,3]], tets[:, [1,2,3]]])
    ordered = np.sort(faces, axis=1)
    _, inverse, counts = np.unique(ordered, axis=0, return_inverse=True, return_counts=True)
    return faces[counts[inverse] == 1]
