"""Disposable native Gmsh + tetrahedral FEA worker.

Invoked only by solid3d_service.py. Do not import this into Streamlit or the
long-lived HTTP server, because native C/C++ meshing crashes bypass try/except.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import sys

import numpy as np

from forceforge.solid3d import (
    boundary_triangles, import_step, make_box, scale_mesh, solve,
)
from solid3d_service import MAX_NODES, MAX_TETS


def calculate(config):
    size_m = config["mesh_size_mm"] / 1000
    if config["geometry"] == "box":
        mesh = make_box(
            config["length_mm"] / 1000,
            config["width_mm"] / 1000,
            config["height_mm"] / 1000,
            size_m,
        )
    elif config["geometry"] == "step":
        units_to_m = {"mm": .001, "m": 1., "inch": .0254}
        scale = units_to_m[config["cad_unit"]]
        mesh = scale_mesh(
            import_step(
                base64.b64decode(config["step_base64"], validate=True),
                mesh_size=size_m / scale,
            ),
            scale,
        )
    else:
        raise ValueError("Unsupported solid geometry")

    if len(mesh.tet) > MAX_TETS or len(mesh.xyz) > MAX_NODES:
        raise ValueError(
            f"Mesh too dense ({len(mesh.tet)} tetrahedra, {len(mesh.xyz)} nodes). "
            f"This stability-limited demo allows {MAX_TETS} tetrahedra / "
            f"{MAX_NODES} nodes. Increase target tetrahedral size."
        )

    result = solve(
        mesh, E=config["E_gpa"] * 1e9, poisson=config["poisson"],
        force_n=config["force_n"], axis=("X", "Y", "Z").index(config["axis"]),
    )
    triangles = boundary_triangles(mesh.tet)
    force_balance = float(np.linalg.norm(result.reaction_sum + result.force_sum))
    if force_balance > max(1e-5, abs(config["force_n"]) * 1e-5):
        raise ValueError(
            f"Force balance check failed ({force_balance:.6g} N); "
            "the FEA results have been rejected."
        )
    xyz_mm = np.round(mesh.xyz * 1000, 6)
    displacement_mm = np.round(result.displacement * 1000, 9)
    nodal_vm = np.round(result.von_mises_node / 1e6, 6)
    if not (np.isfinite(xyz_mm).all() and np.isfinite(displacement_mm).all()
            and np.isfinite(nodal_vm).all()):
        raise ValueError("Non-finite FEA output")
    return {
        "ok": True,
        "mesh": {
            "node_count": int(len(mesh.xyz)),
            "tetrahedra": int(len(mesh.tet)),
            "surface_triangles": int(len(triangles)),
        },
        "metrics": {
            "max_von_mises_mpa": float(np.max(result.von_mises_tet) / 1e6),
            "max_displacement_mm": float(result.max_displacement * 1000),
            "equilibrium_residual_n": force_balance,
        },
        "vertices_mm": xyz_mm.tolist(),
        "displacements_mm": displacement_mm.tolist(),
        "boundary_faces": triangles.tolist(),
        "nodal_von_mises_mpa": nodal_vm.tolist(),
        "assumptions": (
            "Isotropic small-strain linear-elastic 4-node tetrahedra. "
            "Minimum axis face fixed, equal nodal loading on maximum axis face. "
            "No contact, pressure, fatigue, plasticity or mesh convergence. "
            "Nodal colors are averaged from elements."
        ),
    }


def main():
    if len(sys.argv) != 3:
        print("Expected input and output paths", file=sys.stderr)
        return 2
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    try:
        config = json.loads(input_path.read_text(encoding="utf-8"))
        result = calculate(config)
        output_path.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
        return 0
    except Exception as exc:
        output_path.write_text(
            json.dumps({"error": str(exc)[:500]}), encoding="utf-8"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
