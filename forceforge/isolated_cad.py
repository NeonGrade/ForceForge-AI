"""Crash-isolated CAD and 3D FEA jobs for Streamlit on macOS.

Streamlit's main server never loads Gmsh's native library or runs a sparse 3D
factorization. Each explicitly requested CAD/FEA job is executed by the same
Python interpreter in a bounded child process. If native Gmsh exits/segfaults,
runs out of memory or times out, the web server remains alive and reports the
failure. Input/output uses JSON, STEP and NumPy NPZ with allow_pickle=False.

Engineering scope/solver physics remain those of step_mesh.py + cad_solid.py.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from threading import Lock
import json
import os
import subprocess
import sys
import tempfile
import traceback

import numpy as np

from .cad_solid import CadLoad, CADFEAResult
from .step_mesh import CadMesh, MAX_CAD_BYTES, _validate_step

ROOT = Path(__file__).resolve().parents[1]
MAX_INTERACTIVE_TETS = 1400
RUN_TIMEOUT_SECONDS = 85
CAD_GENERATE_TIMEOUT_SECONDS = 35
# Prevent several browser tabs from concurrently allocating large native FE jobs.
_ACTIVE_WORKER = Lock()


class CadJobError(RuntimeError):
    """Native worker failed without taking the Streamlit server down."""


def _save_result(folder: Path, mesh: CadMesh, result: CADFEAResult) -> None:
    np.savez_compressed(
        folder / "fea.npz",
        mesh_nodes=mesh.nodes_m,
        mesh_tets4=mesh.tets4,
        mesh_bbox=mesh.bbox_m,
        solution_nodes=result.nodes_m,
        solution_tets10=result.tets10,
        solution_displacements=result.displacements_m,
        solution_mises=result.von_mises_pa,
        solution_stress=result.stress_voigt_pa,
        solution_faces=result.surface_faces,
        solution_face_elements=result.surface_element_ids,
        solution_reaction=result.support_reaction_n,
        gauss_points=result.gauss_points_m,
        gauss_mises=result.gauss_von_mises_pa,
        gauss_weights=result.gauss_weights_m3,
        sampled_peak_location=result.sampled_peak_location_m,
    )
    metadata = {
        "mesh": {
            "source_sha256": mesh.source_sha256,
            "source_label": mesh.source_label,
            "mesh_size_mm": mesh.mesh_size_mm,
            "cad_volume_m3": mesh.cad_volume_m3,
            "mesh_volume_m3": mesh.mesh_volume_m3,
            "relative_volume_difference": mesh.relative_volume_difference,
            "min_shape_quality": mesh.min_shape_quality,
        },
        "load": asdict(result.load),
        "result": {
            "relative_reaction_residual": result.relative_reaction_residual,
            "load_face_area_m2": result.load_face_area_m2,
            "average_tip_displacement_m": result.average_tip_displacement_m,
            "max_displacement_m": result.max_displacement_m,
            "mass_kg": result.mass_kg,
            "sampled_peak_stress_pa": result.sampled_peak_stress_pa,
            "strain_energy_j": result.strain_energy_j,
        },
    }
    (folder / "result.json").write_text(json.dumps(metadata), encoding="utf-8")


def _read_result(folder: Path, source: bytes) -> CADFEAResult:
    metadata = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    expected_hash = sha256(source).hexdigest()
    if metadata["mesh"]["source_sha256"] != expected_hash:
        raise CadJobError("Worker result does not match the supplied CAD SHA-256")
    with np.load(folder / "fea.npz", allow_pickle=False) as data:
        arrays = {key: np.array(data[key], copy=True) for key in data.files}
    m = metadata["mesh"]
    mesh = CadMesh(
        nodes_m=arrays["mesh_nodes"],
        tets4=arrays["mesh_tets4"],
        source_sha256=expected_hash,
        source_label=m["source_label"],
        mesh_size_mm=float(m["mesh_size_mm"]),
        cad_volume_m3=float(m["cad_volume_m3"]),
        mesh_volume_m3=float(m["mesh_volume_m3"]),
        bbox_m=arrays["mesh_bbox"],
        relative_volume_difference=float(m["relative_volume_difference"]),
        min_shape_quality=float(m["min_shape_quality"]),
    )
    r = metadata["result"]
    return CADFEAResult(
        mesh=mesh,
        load=CadLoad(**metadata["load"]),
        nodes_m=arrays["solution_nodes"],
        tets10=arrays["solution_tets10"],
        displacements_m=arrays["solution_displacements"],
        von_mises_pa=arrays["solution_mises"],
        stress_voigt_pa=arrays["solution_stress"],
        surface_faces=arrays["solution_faces"],
        surface_element_ids=arrays["solution_face_elements"],
        support_reaction_n=arrays["solution_reaction"],
        relative_reaction_residual=float(r["relative_reaction_residual"]),
        load_face_area_m2=float(r["load_face_area_m2"]),
        average_tip_displacement_m=float(r["average_tip_displacement_m"]),
        max_displacement_m=float(r["max_displacement_m"]),
        mass_kg=float(r["mass_kg"]),
        sampled_peak_stress_pa=float(r["sampled_peak_stress_pa"]),
        strain_energy_j=float(r["strain_energy_j"]),
        gauss_points_m=arrays["gauss_points"],
        gauss_von_mises_pa=arrays["gauss_mises"],
        gauss_weights_m3=arrays["gauss_weights"],
        sampled_peak_location_m=arrays["sampled_peak_location"],
    )


def _invoke(kind: str, settings: dict, source: bytes | None,
            timeout: float) -> bytes | CADFEAResult:
    if kind not in ("generate", "analyze"):
        raise ValueError("Unsupported CAD worker operation")
    if source is not None:
        _validate_step(source)
    with tempfile.TemporaryDirectory(prefix="forceforge_safe_") as temporary:
        folder = Path(temporary)
        (folder / "config.json").write_text(json.dumps(settings), encoding="utf-8")
        if source is not None:
            (folder / "source.step").write_bytes(source)
        env = os.environ.copy()
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                    "NUMEXPR_NUM_THREADS"):
            env[key] = "1"
        command = [sys.executable, "-m", "forceforge.isolated_cad",
                   "--worker", kind, str(folder)]
        if not _ACTIVE_WORKER.acquire(blocking=False):
            raise CadJobError(
                "Another CAD or FEA job is already running in this "
                "ForceForge server (possibly another browser tab). "
                "Allow the existing solve to finish before starting another."
            )
        try:
            try:
                completed = subprocess.run(
                    command, cwd=str(ROOT), env=env,
                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                    timeout=timeout, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise CadJobError(
                    f"{kind.capitalize()} exceeded {timeout:g} seconds. "
                    "The native worker was stopped; ForceForge remains available. "
                    "Use a coarser mesh or a smaller CAD part."
                ) from exc
        finally:
            _ACTIVE_WORKER.release()
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()
            detail = detail[-1700:] if detail else "no Python error reported (possible native crash)"
            raise CadJobError(
                f"Isolated CAD {kind} exited with code {completed.returncode}. "
                "The server stays running. Details: " + detail
            )
        if kind == "generate":
            content = (folder / "generated.step").read_bytes()
            _validate_step(content)
            return content
        return _read_result(folder, source)


def generate_bracket_safely(web_mm: float) -> bytes:
    """Produce an editable real STEP file without loading Gmsh in Streamlit."""
    if float(web_mm) not in (8., 10., 12., 14.):
        raise ValueError("Allowed web thicknesses: 8, 10, 12, 14 mm")
    return _invoke(
        "generate", {"web_mm": float(web_mm)}, None,
        CAD_GENERATE_TIMEOUT_SECONDS,
    )


def analyze_step_safely(
    source: bytes, *, source_label: str, mesh_size_mm: float,
    unit: str, load: CadLoad, max_tets: int = MAX_INTERACTIVE_TETS,
) -> CADFEAResult:
    """A bounded, independent STEP → volume mesh → tetra10 FE solve."""
    if not 50 <= max_tets <= MAX_INTERACTIVE_TETS:
        raise ValueError("Unsafe CAD solver tetra element cap")
    settings = {
        "source_label": str(source_label)[:180],
        "mesh_size_mm": float(mesh_size_mm),
        "unit": str(unit),
        "max_tets": int(max_tets),
        "load": asdict(load),
    }
    return _invoke("analyze", settings, source, RUN_TIMEOUT_SECONDS)


def _worker_main(kind: str, folder: Path) -> None:
    # Import Gmsh only in this dedicated child process.
    from .step_mesh import generated_bracket_step, mesh_step_bytes
    from .cad_solid import solve_cad_mesh
    payload = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    if kind == "generate":
        blob = generated_bracket_step(web_mm=float(payload["web_mm"]))
        (folder / "generated.step").write_bytes(blob)
    elif kind == "analyze":
        source = (folder / "source.step").read_bytes()
        mesh = mesh_step_bytes(
            source,
            source_label=payload["source_label"],
            mesh_size_mm=payload["mesh_size_mm"],
            unit=payload["unit"],
            max_tets=payload["max_tets"],
        )
        result = solve_cad_mesh(mesh, CadLoad(**payload["load"]))
        _save_result(folder, mesh, result)
    else:
        raise ValueError("Unsupported worker action")


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--worker":
        raise SystemExit("Worker module is internal to ForceForge")
    try:
        _worker_main(sys.argv[2], Path(sys.argv[3]))
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(2)
