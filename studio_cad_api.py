"""Spatial Studio adapter for engineering v0.8 actual STEP/Gmsh -> tet10 FEA.

No substitute geometry or fabricated solver results. Keep a small bounded
process-local CAD source cache, use the original v0.8 source/mesh/FE modules.
"""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
from threading import RLock
import json
import math
import urllib.request

import numpy as np

from forceforge.step_mesh import (
    MAX_CAD_BYTES, NIST_BRIDGE_URL, NIST_PINNED_SHA256,
    NIST_DATASET_DOI, generated_bracket_step, mesh_step_bytes,
)
from forceforge.cad_solid import CadLoad, solve_cad_mesh

_MAX_CACHE_BYTES = 32 * 1024 * 1024
_CACHE: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
_LOCK = RLock()
ALLOWED_WEB_MM = (8, 10, 12, 14)


def _number(p, key, default, low, high):
    value = p.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key} must be between {low} and {high}")
    return value


def _choice(p, key, options, default):
    val = p.get(key, default)
    if val not in options:
        raise ValueError(f"{key} must be one of {options}")
    return val


def store_step(raw: bytes, name: str = "Imported STEP") -> dict:
    if not isinstance(raw, bytes) or not 100 < len(raw) <= MAX_CAD_BYTES:
        raise ValueError("STEP source must contain between 101 bytes and 32 MiB")
    if b"ISO-10303-21" not in raw[:1000].upper():
        raise ValueError("The source is not an ISO-10303-21 STEP Part 21 file")
    digest = sha256(raw).hexdigest()
    name = (name or "Imported STEP").strip()[:100]
    name = "".join(ch for ch in name if 32 <= ord(ch) <= 126) or "Imported STEP"
    with _LOCK:
        _CACHE[digest] = (raw, name)
        _CACHE.move_to_end(digest)
        total = sum(len(blob) for blob, _ in _CACHE.values())
        while total > _MAX_CACHE_BYTES and len(_CACHE) > 1:
            _, (blob, _) = _CACHE.popitem(last=False)
            total -= len(blob)
    return {"token": digest, "sha256": digest, "name": name,
            "bytes": len(raw), "source": "NIST published original"
            if digest == NIST_PINNED_SHA256 else "User-supplied STEP"}


def get_step(token: str) -> tuple[bytes, str]:
    if not isinstance(token, str) or len(token) != 64:
        raise ValueError("Invalid CAD source token")
    with _LOCK:
        value = _CACHE.get(token)
        if value is None:
            raise ValueError("CAD source is not in this local session. Please import it again.")
        _CACHE.move_to_end(token)
        return value


def fetch_published_nist() -> dict:
    req = urllib.request.Request(
        NIST_BRIDGE_URL, headers={"User-Agent": "ForceForge-X-Spatial-0.2"}
    )
    with urllib.request.urlopen(req, timeout=35) as response:
        raw = response.read(MAX_CAD_BYTES + 1)
    if len(raw) > MAX_CAD_BYTES:
        raise ValueError("Official STEP is over the 32 MiB safety cap")
    digest = sha256(raw).hexdigest()
    if digest != NIST_PINNED_SHA256:
        raise ValueError("Official NIST CAD SHA-256 differs from the pinned original")
    return store_step(raw, "NIST AMB2022-01 official STEP")


def options(p: dict) -> dict:
    source = _choice(p, "source", ("generated", "uploaded"), "generated")
    web_mm = int(_choice(p, "web_mm", ALLOWED_WEB_MM, 8))
    mesh_size_mm = _number(p, "mesh_size_mm", 10, 2, 20)
    force_n = _number(p, "force_n", 250, 20, 2000)
    direction = _choice(p, "direction", ("+X", "-X", "+Y", "-Y"), "+X")
    boundary = _choice(p, "boundary", ("Z", "X", "Y"), "Z")
    if direction[-1] == boundary:
        raise ValueError("The applied force axis must be transverse to the base axis")
    e_gpa = _number(p, "E_gpa", 200, 10, 400)
    nu = _number(p, "nu", .29, .1, .45)
    density = _number(p, "density", 8190, 1000, 20000)
    yield_mpa = _number(p, "yield_mpa", 900, 10, 1800)
    unit = _choice(p, "unit", ("mm", "m"), "mm")
    visual_scale = _number(p, "visual_scale", 35, 1, 150)
    token = p.get("token") if source == "uploaded" else None
    if source == "uploaded" and not token:
        raise ValueError("Import a STEP file before analyzing it")
    return dict(source=source, web_mm=web_mm, mesh_size_mm=mesh_size_mm,
                force_n=force_n, direction=direction, boundary=boundary,
                E_gpa=e_gpa, nu=nu, density=density, yield_mpa=yield_mpa,
                unit=unit, visual_scale=visual_scale, token=token)


def source_bytes(p: dict) -> tuple[bytes, str, str]:
    if p["source"] == "generated":
        raw = generated_bracket_step(web_mm=float(p["web_mm"]))
        label = f"Generated demonstration bracket / {p['web_mm']} mm web"
        token = store_step(raw, label)["token"]
        return raw, label, token
    raw, label = get_step(p["token"])
    return raw, label, p["token"]


def _solve(p: dict):
    raw, label, token = source_bytes(p)
    mesh = mesh_step_bytes(
        raw, source_label=label, mesh_size_mm=p["mesh_size_mm"],
        unit=p["unit"], max_tets=5000
    )
    case = CadLoad(force_n=p["force_n"],
                   force_axis="XYZ".index(p["direction"][-1]),
                   force_sign=1 if p["direction"][0] == "+" else -1,
                   boundary_axis="XYZ".index(p["boundary"]),
                   E_pa=p["E_gpa"] * 1e9, nu=p["nu"],
                   density=p["density"], yield_pa=p["yield_mpa"] * 1e6)
    return solve_cad_mesh(mesh, case), token


def _mesh_payload(result, scale):
    displaced = result.nodes_m + scale * result.displacements_m
    values = result.von_mises_pa[result.surface_element_ids] / 1e6
    return {
        "vertices": np.round(displaced * 1000, 6).tolist(),
        "faces": np.asarray(result.surface_faces, dtype=int).tolist(),
        "scalar": np.round(values, 5).tolist(),
        "unit": "mm",
    }


def _report(result, token, scale, include_mesh=True) -> dict:
    m, load = result.mesh, result.load
    bbox = np.asarray(m.bbox_m) * 1000
    body = {
        "workspace": "cad", "model_title": m.source_label,
        "source_sha256": m.source_sha256,
        "source_type": "Original NIST geometry" if m.source_sha256 == NIST_PINNED_SHA256
                       else "Generated CAD example" if m.source_label.startswith("Generated")
                       else "Imported STEP",
        "cad_token": token,
        "mesh_count": int(m.num_tets),
        "mesh_volume_mm3": float(m.mesh_volume_m3 * 1e9),
        "cad_volume_mm3": float(m.cad_volume_m3 * 1e9),
        "volume_difference_percent": float(m.relative_volume_difference * 100),
        "min_quality_proxy": float(m.min_shape_quality),
        "bbox_mm": bbox.tolist(),
        "tip_displacement_mm": round(float(result.tip_mm), 6),
        "max_von_mises_mpa": round(float(result.peak_von_mises_mpa), 5),
        "stress_cmax_mpa": round(float(result.peak_von_mises_mpa), 5),
        "mass_kg": round(float(result.mass_kg), 6),
        "reaction_residual": float(result.relative_reaction_residual),
        "force_n": float(load.force_n),
        "direction": ("+" if load.force_sign == 1 else "-") + "XYZ"[load.force_axis],
        "boundary": "XYZ"[load.boundary_axis],
        "assumed_yield_mpa": float(load.yield_pa / 1e6),
        "yield_ratio": float(result.peak_von_mises_mpa / (load.yield_pa / 1e6)),
        "visual_deformation": f"Displacement shown x{scale:g}; display only",
        "validation": "True STEP-derived volume mesh, linear elastic tet10 FEA; "
                      "no independently measured static displacement or safety certification.",
        "nist_source": f"https://doi.org/{NIST_DATASET_DOI}",
    }
    if include_mesh:
        body["mesh"] = _mesh_payload(result, scale)
    return body


def analyze(payload: dict) -> dict:
    p = options(payload)
    result, token = _solve(p)
    return _report(result, token, p["visual_scale"])


def revise(payload: dict) -> dict:
    p = options(payload)
    original, old_token = _solve(p)
    revised_input = dict(p)
    if p["source"] == "generated":
        revision_mm = int(_choice(payload, "revision_web_mm", ALLOWED_WEB_MM, 12))
        if revision_mm == p["web_mm"]:
            raise ValueError("The revised CAD web thickness must differ from the original")
        revised_input["web_mm"] = revision_mm
    else:
        rev_token = payload.get("revision_token")
        if rev_token == old_token:
            raise ValueError("Revised STEP must differ from the original")
        get_step(rev_token)
        revised_input["token"] = rev_token
    new, new_token = _solve(revised_input)
    if new.mesh.source_sha256 == original.mesh.source_sha256:
        raise ValueError("The revised STEP has the same source SHA-256 as the original")
    return {
        "workspace": "cad",
        "original": _report(original, old_token, p["visual_scale"], False),
        "revision": _report(new, new_token, p["visual_scale"], True),
        "mass_delta_percent": 100 * (new.mass_kg / original.mass_kg - 1),
        "model_note": "Both actual STEP geometries were meshed and solved independently "
                      "under the same assumed material, fixture and transverse loading.",
    }


def audit_json(current: dict, revision: dict | None = None) -> str:
    return json.dumps({"original": current, "revision": revision,
                       "scope": "Unvalidated linear elastic FEA; no certification"}, indent=2)
