"""ForceForge X Studio: local single-page UI backed by the existing FEA solvers.

This is a presentation/API adapter, not a new physics implementation.
- /api/solve: real modal experiment or 3D tet10 solid simulation.
- /api/calibrate: fit only measured Mode 1, reserve Modes 2/3 as holdouts.
- /api/redesign: re-solve independently meshed thickness candidates.
- /studio/*: dependency-free front-end assets.

Run with: python3 studio_server.py
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import webbrowser

import numpy as np

from forceforge.modal_benchmark import (
    LENGTH_M, WIDTH_M, THICKNESS_M, SENSOR_HEIGHTS_M,
    MEASURED_HZ, PUBLISHED_FE_HZ, solve_modes, solve_static,
    fit_base_stiffness, prism_surface,
)
from forceforge.solid3d import SolidCase, solve_solid
import studio_cad_api as cad_api
from forceforge.engineering_agent import CadProposal, propose_cad_inputs, confirm_cad_inputs

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "studio"
STEP = ROOT / "assets/benchmark/hannover_steel_beam_reconstructed.step"
STL = ROOT / "assets/benchmark/hannover_steel_beam_reconstructed_ascii.stl"
PAPER = "https://wes.copernicus.org/articles/11/3359/2026/index.html"
DATASET = "https://data.uni-hannover.de/en/dataset/a-benchmark-structure-for-virtual-sensing-on-tower-structures"
DESIGN_CANDIDATES_MM = (8, 10, 11, 12, 13, 14, 16, 18, 20)


def number(payload: dict, name: str, default: float, lo: float, hi: float) -> float:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return value


def choice(payload: dict, name: str, options: tuple, default):
    value = payload.get(name, default)
    if value not in options:
        raise ValueError(f"{name} must be one of {options}")
    return value


def _as_mesh(points_m, faces, values=None, *, reference_points_m=None,
             displacements_m=None):
    """Serialize rendered mesh plus undeformed coordinates for accurate probing.

    The displayed positions may have greatly exaggerated deformations.
    Reference coordinates and actual FEA displacement remain separate.
    Surface scalar is a per-face stress sample, not a point-exact value.
    """
    pts = np.asarray(points_m, dtype=float)
    indices = np.asarray(faces, dtype=int)
    if pts.ndim != 2 or pts.shape[1] != 3 or not np.all(np.isfinite(pts)):
        raise ValueError("Invalid mesh coordinates")
    data = {
        "vertices": np.round(pts * 1000, 6).tolist(),
        "faces": indices.tolist(),
        "scalar": None,
        "unit": "mm",
    }
    if reference_points_m is not None:
        reference = np.asarray(reference_points_m, dtype=float)
        if reference.shape != pts.shape or not np.all(np.isfinite(reference)):
            raise ValueError("Reference geometry must match display vertices")
        data["reference_vertices"] = np.round(reference * 1000, 6).tolist()
    if displacements_m is not None:
        displacements = np.asarray(displacements_m, dtype=float)
        if displacements.shape != pts.shape or not np.all(np.isfinite(displacements)):
            raise ValueError("Displacement array must match display vertices")
        data["displacements_mm"] = np.round(displacements * 1000, 8).tolist()
    if values is not None:
        scalars = np.asarray(values, dtype=float)
        if scalars.shape != (len(indices),) or not np.all(np.isfinite(scalars)):
            raise ValueError("Per-face scalar values must match surface faces")
        data["scalar"] = np.round(scalars, 5).tolist()
    return data


def _lab_options(p: dict) -> dict:
    return {
        "log10_k": number(p, "log10_k", 3.0, 0.0, 6.0),
        "E_gpa": number(p, "E_gpa", 210.0, 150.0, 240.0),
        "density": number(p, "density", 7850.0, 6500.0, 8500.0),
        "elements": int(choice(p, "elements", (16, 24, 32, 48, 64), 32)),
        "gauges": bool(choice(p, "gauges", (True, False), True)),
        "mode": int(choice(p, "mode", (1, 2, 3), 1)),
        "view": choice(p, "view", ("modes", "static"), "modes"),
        "amplitude_mm": number(p, "amplitude_mm", 28, 5, 65),
        "tip_force_n": number(p, "tip_force_n", .30, .05, 1.0),
        "static_scale": number(p, "static_scale", 15, 1, 30),
    }


def lab_analysis(p: dict) -> dict:
    a = _lab_options(p)
    k = 10 ** a["log10_k"]
    result = solve_modes(
        base_stiffness_nm_rad=k,
        E_pa=a["E_gpa"] * 1e9,
        rho_kg_m3=a["density"],
        n_elements=a["elements"],
        reduce_gauges=a["gauges"],
        count=3,
    )
    static_tip_mm = None
    if a["view"] == "static":
        _, deflection, _, _, _ = solve_static(
            tip_force_n=a["tip_force_n"],
            base_stiffness_nm_rad=k,
            E_pa=a["E_gpa"] * 1e9,
            rho_kg_m3=a["density"],
            n_elements=a["elements"],
            reduce_gauges=a["gauges"],
        )
        offset = deflection * a["static_scale"]
        static_tip_mm = float(deflection[-1] * 1000.0)
    else:
        offset = result.transverse_shapes[:, a["mode"] - 1] * a["amplitude_mm"] / 1000
    verts, faces, _ = prism_surface(
        result.heights_m, offset,
        include_gauge_areas=a["gauges"],
    )
    reference, reference_faces, _ = prism_surface(
        result.heights_m, np.zeros_like(offset),
        include_gauge_areas=a["gauges"],
    )
    if reference.shape != verts.shape or not np.array_equal(faces, reference_faces):
        raise ValueError("Reference modal mesh topology differs from displayed mesh")
    # Static displacements are genuine FEM values; mode-shape amplitudes
    # are visualization choices and must never be labeled actual movement.
    actual_u = (verts - reference) / a["static_scale"] if a["view"] == "static" else None
    sensors = [
        {
            "id": name,
            "height_mm": round(z * 1000, 1),
            "position": [
                float(np.interp(z, result.heights_m, offset) * 1000),
                23.0,
                round(z * 1000, 1),
            ],
            "type": "Accelerometer / laser" if name in ("MP1", "MP2", "MP3")
                    else "Strain gauge",
        }
        for name, z in SENSOR_HEIGHTS_M.items()
    ]
    frequencies = [float(f) for f in result.frequencies_hz]
    errors = [
        100 * (frequencies[i] / float(MEASURED_HZ[i]) - 1)
        for i in range(3)
    ]
    return {
        "workspace": "lab",
        "model_title": "Hannover steel beam",
        "analysis_label": "Measured modal reference / simplified FEM",
        "model_type": "Published geometry reconstructed; original Abaqus mesh not bundled",
        "mesh": _as_mesh(verts, faces, reference_points_m=reference,
                         displacements_m=actual_u),
        "sensors": sensors,
        "frequencies_hz": frequencies,
        "measured_hz": MEASURED_HZ.tolist(),
        "published_abaqus_hz": PUBLISHED_FE_HZ.tolist(),
        "error_percent": [round(e, 4) for e in errors],
        "mass_kg": round(float(result.mass_kg), 6),
        "support_stiffness_nm_rad": round(k, 4),
        "dimensions_mm": [round(LENGTH_M * 1000, 1),
                          round(WIDTH_M * 1000, 1),
                          round(THICKNESS_M * 1000, 1)],
        "assumed_material": {
            "E_gpa": a["E_gpa"], "density_kg_m3": a["density"]
        },
        "mode": a["mode"],
        "view": a["view"],
        "static_tip_mm": static_tip_mm,
        "static_force_n": a["tip_force_n"] if a["view"] == "static" else None,
        "visual_deformation": (
            f"Mode shape amplitude {a['amplitude_mm']:.0f} mm (display only)"
            if a["view"] == "modes" else
            f"Static movement multiplied by {a['static_scale']:.0f} (display only)"
        ),
        "validation": "Published physical modal frequencies; simplified independent model. No safety certification.",
        "measurement_source": PAPER,
        "dataset_source": DATASET,
    }


def lab_calibrate(p: dict) -> dict:
    a = _lab_options(p)
    fitted_k, fitted = fit_base_stiffness(
        E_pa=a["E_gpa"] * 1e9,
        rho_kg_m3=a["density"],
        n_elements=a["elements"],
        reduce_gauges=a["gauges"],
    )
    log_k = math.log10(fitted_k)
    if not 0 <= log_k <= 6:
        raise ValueError("Fitted support parameter is outside the editable range")
    errors = [
        100 * (fitted.frequencies_hz[i] / MEASURED_HZ[i] - 1)
        for i in range(3)
    ]
    return {
        "log10_k": round(log_k, 7),
        "k_nm_rad": round(float(fitted_k), 5),
        "frequencies_hz": [float(f) for f in fitted.frequencies_hz],
        "error_percent": [round(float(e), 5) for e in errors],
        "holdout_mape_percent": round(float(np.mean(np.abs(errors[1:]))), 5),
        "method": "Only published measured Mode 1 was used to fit effective rotational stiffness. Modes 2/3 are held out.",
        "qualification": "A fitted model parameter is not a measured connection stiffness.",
    }


def _solid_options(p: dict) -> tuple[SolidCase, float, float]:
    thickness_mm = number(p, "thickness_mm", 12, 8, 20)
    force_n = number(p, "force_n", 200, 50, 500)
    allowed_mm = number(p, "allowed_mm", .12, .04, .30)
    visual_scale = number(p, "visual_scale", 60, 1, 120)
    resolution = choice(p, "resolution", ("fast", "refined", "high"), "refined")
    grid = {
        "fast": (2, 2, 8),
        "refined": (2, 2, 12),
        "high": (3, 3, 12),
    }[resolution]
    case = SolidCase(
        length_m=.120, width_m=.030,
        thickness_m=thickness_mm / 1000,
        force_n=force_n, nx=grid[0], ny=grid[1], nz=grid[2],
    )
    return case, allowed_mm, visual_scale


@lru_cache(maxsize=48)
def _cached_solid(case: SolidCase):
    return solve_solid(case)


def _solid_summary(result, allowed_mm: float):
    return {
        "tip_displacement_mm": round(result.tip_displacement_mm, 6),
        "max_von_mises_mpa": round(result.max_mises_mpa, 5),
        "mass_kg": round(result.mass_kg, 6),
        "element_count": len(result.tets10),
        "node_count": len(result.nodes_m),
        "reaction_residual": float(result.relative_reaction_residual),
        "theoretical_beam_tip_mm": round(result.beam_reference_tip_mm, 6),
        "reference_difference_percent": round(result.beam_reference_error_pct, 4),
        "passes_assumed_limit": (
            result.tip_displacement_mm <= allowed_mm and
            result.max_mises_mpa <= 250
        ),
        "assumed_limit_mm": allowed_mm,
    }


def solid_analysis(p: dict) -> dict:
    case, allowed_mm, scale = _solid_options(p)
    result = _cached_solid(case)
    deformed = result.nodes_m + result.displacements_m * scale
    vm = result.von_mises_pa[result.surface_element_ids] / 1e6
    payload = {
        "workspace": "solid",
        "model_title": "3D tetra10 solid specimen",
        "analysis_label": "Genuine quadratic tetrahedral volume FEA",
        "model_type": "Parametric computational specimen; NOT a tested physical bracket",
        "mesh": _as_mesh(deformed, result.surface_faces, vm,
                         reference_points_m=result.nodes_m,
                         displacements_m=result.displacements_m),
        "stress_cmax_mpa": round(result.max_mises_mpa, 6),
        "dimensions_mm": [120, 30, round(case.thickness_m * 1000, 2)],
        "mesh_resolution": [case.nx, case.ny, case.nz],
        "force_n": case.force_n,
        "visual_deformation": f"Displacement multiplied by {scale:.0f} for display only",
        "validation": "Independent beam-theory comparison and numerical regression tests; no measured static test, no certification.",
        "source_document": "docs/TRUE_3D_SOLID_FEA.md",
    }
    payload.update(_solid_summary(result, allowed_mm))
    return payload


def solid_redesign(p: dict) -> dict:
    case, allowed_mm, _ = _solid_options(p)
    current = _cached_solid(case)
    options = []
    best = None
    for thickness in DESIGN_CANDIDATES_MM:
        candidate = replace(case, thickness_m=thickness / 1000)
        result = _cached_solid(candidate)
        feasible = (
            result.tip_displacement_mm <= allowed_mm and
            result.max_mises_mpa <= 250
        )
        options.append({
            "thickness_mm": thickness,
            "tip_mm": round(result.tip_displacement_mm, 6),
            "stress_mpa": round(result.max_mises_mpa, 5),
            "mass_kg": round(result.mass_kg, 6),
            "feasible": bool(feasible),
        })
        if feasible and (best is None or result.mass_kg < best.mass_kg):
            best = result
    if best is None:
        return {
            "workspace": "solid", "candidates": options,
            "best": None, "tested_count": len(options),
            "note": "No available thickness candidate meets both user-assumed displacement and yield limits.",
        }
    verified = _cached_solid(best.case)
    return {
        "workspace": "solid", "candidates": options,
        "tested_count": len(options),
        "best": {
            "thickness_mm": round(best.case.thickness_m * 1000, 2),
            **_solid_summary(verified, allowed_mm),
            "mass_delta_percent": round(
                (verified.mass_kg / current.mass_kg - 1) * 100, 3
            ),
        },
        "note": "Each option is a newly solved 3D tet10 mesh under the current assumed loading and model limits.",
    }


CATALOG = {
    "product": "ForceForge X Studio",
    "ui_version": "0.2.1",
    "modules": [
        {
            "id": "solid", "name": "Solid mechanics",
            "subtitle": "3D volumetric FEA · tetra10",
            "evidence": "Numerically verified · not physically measured",
        },
        {
            "id": "cad", "name": "Real CAD",
            "subtitle": "Actual STEP BRep to tet10 volume FEA",
            "evidence": "NIST geometry source or original generated bracket; loading is assumed",
        },
        {
            "id": "lab", "name": "Real laboratory",
            "subtitle": "Experimental modal correlation",
            "evidence": "Published physical measurements · simplified FE model",
        },
    ],
    "source_paper": PAPER,
    "engineering_version": "1.0",
    "modules_notice": "Original Streamlit advanced/industry/ML workspaces remain preserved in app.py and pages/.",
    "source_dataset": DATASET,
    "limitations": (
        "Research prototype. No real service qualification, certification, "
        "single-body STEP meshing requires optional Gmsh; no contact, CFD or nonlinear plasticity."
    ),
}


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "ForceForgeStudio/0.2"

    def log_message(self, fmt: str, *args):
        print(f"[studio] {self.address_string()} - {fmt % args}")

    def _json(self, obj, status=200):
        blob = json.dumps(obj, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _bytes(self, path: Path, mimetype: str, *, download: bool = False):
        if not path.is_file():
            self.send_error(404, "File not found")
            return
        blob = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetype)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/catalog":
            return self._json(CATALOG)
        if route in ("/", "/studio", "/studio/"):
            return self._bytes(WEB / "index.html", "text/html; charset=utf-8")
        assets = {
            "/studio/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/studio/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/studio/viewport3d.js": ("viewport3d.js", "text/javascript; charset=utf-8"),
            "/studio/adaptive.js": ("adaptive.js", "text/javascript; charset=utf-8"),
            "/studio/adaptive.css": ("adaptive.css", "text/css; charset=utf-8"),
            "/studio/inspection.js": ("inspection.js", "text/javascript; charset=utf-8"),
        }
        if route in assets:
            filename, mimetype = assets[route]
            return self._bytes(WEB / filename, mimetype)
        if route.startswith("/download/cad/") and route.endswith(".step"):
            token = route[len("/download/cad/"):-len(".step")]
            try:
                source, label = cad_api.get_step(token)
            except ValueError:
                self.send_error(404, "CAD source not available")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/step")
            self.send_header("Content-Disposition", 'attachment; filename="forceforge-cad.step"')
            self.send_header("Content-Length", str(len(source)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(source)
            return
        if route == "/download/beam.step":
            return self._bytes(STEP, "application/step", download=True)
        if route == "/download/beam.stl":
            return self._bytes(STL, "model/stl", download=True)
        self.send_error(404, "Endpoint does not exist")

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route not in ("/api/solve", "/api/calibrate", "/api/redesign",
                         "/api/cad/solve", "/api/cad/revise", "/api/cad/import",
                         "/api/cad/fetch-nist", "/api/cad/agent/preview",
                         "/api/cad/agent/confirm"):
            self.send_error(404, "Unknown API endpoint")
            return
        try:
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}",
                                        f"http://localhost:{self.server.server_port}"):
                raise ValueError("Cross-origin requests are not supported")
            size = int(self.headers.get("Content-Length", "0"))
            if route == "/api/cad/import":
                if not 100 < size <= cad_api.MAX_CAD_BYTES:
                    raise ValueError("STEP upload must be between 101 bytes and 32 MiB")
                raw = self.rfile.read(size)
                name = self.headers.get("X-Cad-Name", "Imported STEP")
                return self._json(cad_api.store_step(raw, name))
            if not 0 < size <= 65536:
                raise ValueError("JSON request body must be smaller than 64 KiB")
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Body must be a JSON object")
            if route in ("/api/cad/agent/preview", "/api/cad/agent/confirm"):
                if not isinstance(payload.get("current"), dict):
                    raise ValueError("Current CAD parameters must be a JSON object")
                current = cad_api.options(payload["current"])
                if route.endswith("preview"):
                    proposal = propose_cad_inputs(payload["prompt"], current)
                    return self._json({"proposal": proposal.model_dump(),
                                       "note": "Preview only; no geometry or FEA calculation started."})
                confirmed = confirm_cad_inputs(CadProposal.model_validate(payload["proposal"]), current)
                return self._json({"parameters": confirmed,
                                   "note": "Confirmed inputs only; an explicit solve is still required."})
            if route == "/api/cad/solve":
                return self._json(cad_api.analyze(payload))
            if route == "/api/cad/revise":
                return self._json(cad_api.revise(payload))
            if route == "/api/cad/fetch-nist":
                return self._json(cad_api.fetch_published_nist())
            if route == "/api/solve":
                workspace = choice(payload, "workspace", ("lab", "solid"), "solid")
                output = lab_analysis(payload) if workspace == "lab" else solid_analysis(payload)
            elif route == "/api/calibrate":
                if payload.get("workspace", "lab") != "lab":
                    raise ValueError("Calibration is supported for the real lab model only")
                output = lab_calibrate(payload)
            else:
                if payload.get("workspace", "solid") != "solid":
                    raise ValueError("3D solid redesign requires the solid model")
                output = solid_redesign(payload)
            self._json(output)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception:
            self.log_exception()
            self._json({"error": "Solver failed; inspect the terminal for details."}, status=500)

    def log_exception(self):
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="ForceForge X Studio local web experience")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true",
                        help="Do not open a browser automatically")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port from 1024 to 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), StudioHandler)
    address = f"http://127.0.0.1:{args.port}"
    print(f"ForceForge X Studio UI v0.2.1 / Engineering v1.0 + ML/Agent integration — {address}")
    print("Press Control+C to stop. Real CAD requires the optional gmsh Python package.")
    if not args.no_open:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
