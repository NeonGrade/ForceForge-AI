"""Isolated 3D FEA subprocess gateway for the stable HTTP workspace.

Native Gmsh and SciPy solve in a disposable child process, never in the
long-lived server. A native crash or timeout must not kill the web workspace.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent
MAX_STEP_BYTES = 4_000_000
MAX_TETS = 6000
MAX_NODES = 10000
WORKER_TIMEOUT_S = 65
_WORKER_GATE = threading.BoundedSemaphore(1)


def _number(data, key, default, low, high):
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{key} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key} must be between {low:g} and {high:g}")
    return value


def validated_config(data):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    mode = data.get("geometry", "box")
    if mode not in ("box", "step"):
        raise ValueError("Geometry must be box or step")
    config = {
        "geometry": mode,
        "mesh_size_mm": _number(data, "mesh_size_mm", 8, 2, 25),
        "E_gpa": _number(data, "E_gpa", 200, .001, 500),
        "poisson": _number(data, "poisson", .3, -.9, .49),
        "force_n": _number(data, "force_n", 1000, -100000, 100000),
    }
    axis = data.get("axis", "X")
    if axis not in ("X", "Y", "Z"):
        raise ValueError("axis must be X, Y or Z")
    config["axis"] = axis
    if mode == "box":
        config.update(
            length_mm=_number(data, "length_mm", 100, 20, 500),
            width_mm=_number(data, "width_mm", 20, 5, 150),
            height_mm=_number(data, "height_mm", 20, 5, 150),
        )
    else:
        units = data.get("cad_unit", "mm")
        if units not in ("mm", "m", "inch"):
            raise ValueError("STEP coordinate unit must be mm, m or inch")
        encoded = data.get("step_base64", "")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Upload a STEP solid file first")
        if len(encoded) > (MAX_STEP_BYTES * 4 // 3) + 8:
            raise ValueError("STEP exceeds the 4 MB local demo limit")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid STEP file encoding") from exc
        if not decoded or len(decoded) > MAX_STEP_BYTES:
            raise ValueError("STEP must contain 1 byte to 4 MB")
        config.update(cad_unit=units, step_base64=encoded)
    return config


def run_study(data, *, timeout_s=WORKER_TIMEOUT_S):
    """Return a finite-JSON 3D result; crashes and exceptions are contained.

    One worker at a time limits native Gmsh memory and CPU pressure; concurrent
    browser requests receive a controlled message instead of an unstable UI.
    """
    config = validated_config(data)
    if not _WORKER_GATE.acquire(blocking=False):
        raise ValueError("A 3D solve is already running. Retry after it finishes.")
    try:
        with tempfile.TemporaryDirectory(prefix="forceforge3d_") as dirname:
            folder = Path(dirname)
            input_path = folder / "input.json"
            output_path = folder / "output.json"
            input_path.write_text(json.dumps(config), encoding="utf-8")
            env = dict(os.environ)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                env[name] = "1"
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "forceforge.solid3d_worker",
                     str(input_path), str(output_path)],
                    cwd=ROOT, env=env, capture_output=True, text=True,
                    timeout=timeout_s, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError(
                    f"3D meshing/solve exceeded {timeout_s} seconds. "
                    "Increase mesh size or simplify the CAD solid."
                ) from exc
            if proc.returncode:
                if output_path.exists():
                    try:
                        detail = json.loads(output_path.read_text(encoding="utf-8"))
                        if isinstance(detail, dict) and isinstance(detail.get("error"), str):
                            raise ValueError(detail["error"][:500])
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass
                raise ValueError(
                    "3D worker exited unexpectedly (code "
                    + str(proc.returncode)
                    + "). The main workspace is still running. "
                    "Try a coarser mesh or inspect the terminal log."
                )
            if not output_path.exists():
                raise ValueError("3D worker returned no result")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict) or not result.get("ok"):
                raise ValueError("Invalid 3D worker response")
            return result
    finally:
        _WORKER_GATE.release()
