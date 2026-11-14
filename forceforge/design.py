"""Two verified finite-element topology families; not arbitrary CAD geometry."""
import numpy as np
from .physics import Truss, Material

TOPOLOGIES = ("Triangle", "Warren-2", "Fan")


def make_truss(
    topology: str = "Triangle", span_m: float = 2.0,
    height_m: float = 1.0, area_mm2: float = 150.0,
    load_n: float = 1000.0, material: Material | None = None,
) -> Truss:
    if topology not in TOPOLOGIES:
        raise ValueError(f"Topology must be one of {TOPOLOGIES}")
    if min(span_m, height_m, area_mm2, load_n) <= 0:
        raise ValueError("Span, height, area and load must be positive")
    if topology == "Triangle":
        nodes = np.array([[0, 0], [span_m, 0], [span_m/2, height_m]], float)
        elements = ((0, 1), (0, 2), (1, 2))
        load_node = 2
        supports = ((0, True, True), (1, False, True))
    elif topology == "Fan":
        nodes = np.array([[0, 0], [span_m/2, 0], [span_m, 0], [span_m/2, height_m]], float)
        elements = ((0, 1), (1, 2), (0, 3), (2, 3), (1, 3))
        load_node = 3
        supports = ((0, True, True), (2, False, True))
    else:  # Warren-2: same top-center load position as the other families.
        nodes = np.array([
            [0, 0], [span_m/2, 0], [span_m, 0],
            [span_m/4, height_m], [span_m/2, height_m], [3*span_m/4, height_m]
        ], float)
        elements = (
            (0, 1), (1, 2), (0, 3), (3, 1), (1, 5), (5, 2),
            (3, 4), (4, 5), (1, 4),
        )
        load_node = 4
        supports = ((0, True, True), (2, False, True))
    forces = np.zeros_like(nodes)
    forces[load_node, 1] = -load_n
    areas = np.full(len(elements), area_mm2 * 1e-6)
    return Truss(nodes, elements, supports, forces, areas, material or Material(), topology)
