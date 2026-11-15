"""Offline CAD input proposals and critiques grounded in completed FE evidence.

No function here runs CAD, FEA or an LLM. An input proposal must be confirmed
against the exact original inputs before a caller explicitly starts a solve.
The 2D truss surrogate is deliberately not used for STEP/tetra10 predictions.
"""
from dataclasses import asdict
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, FiniteFloat

from .provenance import context_id


class CadProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Literal["studio", "stable"]
    input_id: str
    changes: dict[str, FiniteFloat]


def _validate_changes(changes, current, profile):
    bounds = {"force_n": (20, 2000), "mesh_size_mm": (2, 20) if profile == "studio" else (5, 15),
              "E_gpa": (10, 400), "yield_mpa": (10, 1800), "web_mm": (8, 14)}
    if not changes:
        raise ValueError("No supported CAD parameters found; specify force, mesh size, web thickness, E or yield with units")
    for key, value in changes.items():
        if key not in bounds or not math.isfinite(value) or not bounds[key][0] <= value <= bounds[key][1]:
            raise ValueError(f"Unsupported or out-of-range CAD parameter: {key}")
        if key == "web_mm":
            if current.get("source", "generated") != "generated":
                raise ValueError("Imported STEP geometry cannot be changed by a web-thickness instruction; upload revised CAD")
            if value not in (8, 10, 12, 14):
                raise ValueError("Generated bracket web must be 8, 10, 12 or 14 mm")


def propose_cad_inputs(prompt: str, current: dict, *, profile="studio") -> CadProposal:
    """Extract explicit labeled values only, without guessing truss defaults."""
    if profile not in ("studio", "stable"):
        raise ValueError("Unknown CAD input profile")
    if not isinstance(prompt, str) or not 0 < len(prompt) <= 4000:
        raise ValueError("Design brief must contain 1–4000 characters")
    prompt = prompt.replace("−", "-")
    number = r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    fields = {
        "force_n": (r"\bforce\b|\bload\b|载荷|荷载|力", r"kN|N|千牛|牛顿", {"kn":1000, "n":1, "千牛":1000, "牛顿":1}),
        "mesh_size_mm": (r"\bmesh(?:\s+size)?\b|网格(?:尺寸)?", r"mm|cm|m|毫米|厘米|米", {"mm":1, "cm":10, "m":1000, "毫米":1, "厘米":10, "米":1000}),
        "web_mm": (r"\bweb(?:\s+thickness)?\b|腹板(?:厚度)?", r"mm|cm|m|毫米|厘米|米", {"mm":1, "cm":10, "m":1000, "毫米":1, "厘米":10, "米":1000}),
        "E_gpa": (r"\bYoung(?:'s)?(?:\s+modulus)?\b|\bmodulus\b|\bE\b|弹性模量", r"GPa|MPa", {"gpa":1, "mpa":.001}),
        "yield_mpa": (r"\byield(?:\s+(?:stress|limit))?\b|屈服(?:应力|强度)?", r"GPa|MPa", {"gpa":1000, "mpa":1}),
    }
    changes = {}
    for key, (label, units, factors) in fields.items():
        pattern = (rf"(?:{label})\s*(?:(?:to|of|is|为|设为|改为|=|:|：)\s*)?"
                   rf"{number}\s*({units})(?![A-Za-z])")
        matches = list(re.finditer(pattern, prompt, re.I))
        if re.search(label, prompt, re.I) and not matches:
            raise ValueError(f"Specify an explicit numeric value and supported unit for {key}")
        values = [float(m.group(1)) * factors[m.group(2).lower()] for m in matches]
        if values:
            if not all(math.isclose(v, values[0], rel_tol=1e-12, abs_tol=1e-12) for v in values):
                raise ValueError(f"Conflicting values for {key}")
            changes[key] = values[0]
    _validate_changes(changes, current, profile)
    return CadProposal(profile=profile, input_id=context_id(current), changes=changes)


def confirm_cad_inputs(proposal: CadProposal, current: dict) -> dict:
    """Return confirmed parameters; the caller still chooses when to solve."""
    proposal = CadProposal.model_validate(proposal)
    if proposal.input_id != context_id(current):
        raise ValueError("Inputs changed after the proposal; preview it again before confirming")
    _validate_changes(proposal.changes, current, proposal.profile)
    return {**current, **proposal.changes}


def review_cad_result(result, *, mesh_evidence=None, expected_source=None,
                      expected_load=None) -> dict:
    """Explain a completed CADFEAResult; never promote numerical evidence to safety."""
    mesh, load = result.mesh, result.load
    if not re.fullmatch(r"[a-f0-9]{64}", mesh.source_sha256):
        raise ValueError("Missing exact CAD source SHA-256")
    if expected_source is not None and mesh.source_sha256 != expected_source:
        raise ValueError("CAD result is stale: source SHA-256 mismatch")
    if expected_load is not None and load != expected_load:
        raise ValueError("CAD result is stale: load/material/constraint mismatch")
    metrics = {
        "tip_displacement_mm": float(result.tip_mm),
        "max_displacement_mm": float(result.max_displacement_m * 1000),
        "sampled_von_mises_mpa": float(result.peak_von_mises_mpa),
        "mass_kg": float(result.mass_kg),
        "reaction_residual": float(result.relative_reaction_residual),
        "volume_difference_percent": float(mesh.relative_volume_difference * 100),
        "minimum_quality_proxy": float(mesh.min_shape_quality),
        "strain_energy_j": float(result.strain_energy_j),
        "assumed_yield_mpa": float(load.yield_pa / 1e6),
    }
    if any(not math.isfinite(v) or v < 0 for v in metrics.values()) or metrics["assumed_yield_mpa"] <= 0:
        raise ValueError("Non-finite or invalid FE evidence; no critique can assert valid results")
    issues = []
    if metrics["reaction_residual"] > 1e-5:
        issues.append("Reaction equilibrium exceeds the solver tolerance")
    if metrics["volume_difference_percent"] > 20 or metrics["minimum_quality_proxy"] <= 0:
        issues.append("CAD-to-mesh volume/quality screen failed")
    if metrics["sampled_von_mises_mpa"] > metrics["assumed_yield_mpa"]:
        issues.append("Sampled elastic stress exceeds the assumed yield; linear elasticity is insufficient")
    mesh_status = "NOT_EVALUATED"
    if mesh_evidence is not None:
        if mesh_evidence.source_sha256 != mesh.source_sha256 or mesh_evidence.load != load:
            raise ValueError("Mesh evidence belongs to a different CAD or engineering context")
        if not any(math.isclose(row.target_size_mm, mesh.mesh_size_mm)
                   and row.tetrahedra == mesh.num_tets
                   and math.isclose(row.tip_mm, result.tip_mm, rel_tol=1e-9, abs_tol=1e-12)
                   for row in mesh_evidence.ordered_rows):
            raise ValueError("The current FE solve is not a baseline in this mesh study")
        mesh_status = mesh_evidence.decision
        if mesh_status != "PRELIMINARY_GLOBAL_DISPLACEMENT_STABILITY":
            issues.append("Mesh study: " + mesh_status)
    else:
        issues.append("Mesh sensitivity has not been evaluated for this exact solve")
    review = {
        "source_sha256": mesh.source_sha256,
        "assumed_load_and_material": asdict(load),
        "solver": "3D linear-elastic tetra10",
        "mesh_size_mm": float(mesh.mesh_size_mm),
        "tetrahedra": int(mesh.num_tets),
        "metrics": metrics,
        "mesh_assessment": mesh_status,
        "assessment": "REVIEW_REQUIRED" if issues else "PRELIMINARY_NUMERICAL_SCREEN_ONLY",
        "issues": issues,
        "summary": (
            f"Completed tetra10 FEA: tip displacement {result.tip_mm:.5f} mm, "
            f"sampled von Mises {result.peak_von_mises_mpa:.3f} MPa against "
            f"assumed yield {load.yield_pa/1e6:.3f} MPa; mass {result.mass_kg:.5f} kg. "
            f"Mesh assessment: {mesh_status}."
        ),
        "limitations": [
            "Static load, material and fixture parameters are assumptions, not physical measurements.",
            "A three-mesh global-displacement screen does not establish local peak-stress convergence.",
            "Published modal/manufacturing observations do not validate this static load case.",
            "The 2D truss ML model is not applicable to imported CAD or tetra10 solids; no safety certification.",
        ],
    }
    review["review_id"] = context_id(review)
    return review
