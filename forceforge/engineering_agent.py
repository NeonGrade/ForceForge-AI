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
        "force_n": (r"\bforce\b|\bload\b|\bapply(?:\s+a)?\b|载荷|荷载|力", r"kN|newtons?|N|千牛|牛顿", {"kn":1000, "newton":1, "newtons":1, "n":1, "千牛":1000, "牛顿":1}),
        "mesh_size_mm": (r"\bmesh(?:\s+(?:size|spacing))?\b|\belement\s+size\b|网格(?:尺寸)?", r"mm|cm|m|毫米|厘米|米", {"mm":1, "cm":10, "m":1000, "毫米":1, "厘米":10, "米":1000}),
        "web_mm": (r"\bweb(?:\s+thickness)?\b|腹板(?:厚度)?", r"mm|cm|m|毫米|厘米|米", {"mm":1, "cm":10, "m":1000, "毫米":1, "厘米":10, "米":1000}),
        "E_gpa": (r"\bYoung(?:'s)?(?:\s+modulus)?\b|\bmodulus\b|\bE\b|弹性模量", r"GPa|MPa", {"gpa":1, "mpa":.001}),
        "yield_mpa": (r"\byield(?:\s+(?:stress|limit))?\b|屈服(?:应力|强度)?", r"GPa|MPa", {"gpa":1000, "mpa":1}),
    }
    changes = {}
    for key, (label, units, factors) in fields.items():
        pattern = (rf"(?:{label})\s*(?:(?:is\s+set\s+to|should\s+be|to|at|of|is|为|设为|改为|=|:|：)\s*)?"
                   rf"{number}\s*({units})(?![A-Za-z])")
        matches = list(re.finditer(pattern, prompt, re.I))
        # English commonly puts a value before its noun: 'a 12 mm mesh'.
        suffix = rf"{number}\s*({units})(?![A-Za-z])\s+(?:{label})"
        matches += list(re.finditer(suffix, prompt, re.I))
        values = [float(m.group(1)) * factors[m.group(2).lower()] for m in matches]
        percentages = list(re.finditer(
            rf"\b(increase|raise|reduce|decrease|lower)\s+(?:the\s+)?(?:{label})\s+by\s+{number}\s*(?:%|percent\b)",
            prompt, re.I))
        multipliers = list(re.finditer(rf"\b(double|halve)\s+(?:the\s+)?(?:{label})", prompt, re.I))
        if percentages or multipliers:
            base = current.get(key)
            if isinstance(base, bool) or not isinstance(base, (int, float)) or not math.isfinite(base):
                raise ValueError(f"Relative changes require a finite current {key}")
            for match in percentages:
                percent = float(match.group(2))
                if not math.isfinite(percent) or percent < 0:
                    raise ValueError("Percentage must be finite and nonnegative")
                sign = 1 if match.group(1).lower() in ("increase", "raise") else -1
                values.append(base * (1 + sign * percent / 100))
            for match in multipliers:
                values.append(base * (2 if match.group(1).lower() == "double" else .5))
        if re.search(label, prompt, re.I) and not values:
            raise ValueError(f"Specify an explicit numeric value and supported unit for {key}")
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


def is_parameter_request(prompt: str) -> bool:
    """Route ordinary English questions separately from bounded input changes."""
    if not isinstance(prompt, str) or not 0 < len(prompt) <= 4000:
        raise ValueError("Engineering question must contain 1–4000 characters")
    polite_change = re.match(r"\s*(?:(?:can|could|would)\s+you\s+(?:please\s+)?|what\s+if\s+I\s+)(?:set|change|increase|raise|reduce|decrease|lower|double|halve|apply)\b", prompt, re.I)
    if not polite_change and re.match(r"\s*(?:why|what|how|is|are|has|have|which|can|could|would|does|do)\b", prompt, re.I):
        return False
    return bool(re.search(r"\d|\b(?:double|halve)\b", prompt, re.I))


def answer_cad_question(question: str, review: dict) -> dict:
    """Answer English engineering questions only from a completed solver review."""
    if not isinstance(question, str) or not 0 < len(question) <= 4000:
        raise ValueError("Engineering question must contain 1–4000 characters")
    evidence = {key:value for key,value in review.items() if key != "review_id"}
    if review.get("review_id") != context_id(evidence):
        raise ValueError("Review evidence has changed; obtain a fresh solver review")
    text = question.lower()
    m, source = review["metrics"], review["source_sha256"]
    citation = ["source_sha256", "assumed_load_and_material.force_n"]
    load = review["assumed_load_and_material"]["force_n"]
    if re.search(r"\bsafe\b|certif|real.world|physical.*valid|measured", text):
        topic = "validation_scope"
        answer = "This computed result cannot establish real-world safety or certification. " + " ".join(review["limitations"])
        citation += ["limitations"]
    elif re.search(r"\bml\b|surrogate|machine learning", text):
        topic = "ml_scope"
        answer = ("The Random Forest surrogate is trained for the three 2D truss families, not imported STEP "
                  "or tetra10 CAD solids. Use the actual CAD FE solver for this case; its results cannot be "
                  "replaced by the truss model's accuracy metrics.")
        citation += ["limitations"]
    elif re.search(r"\bfail|\bpass|\bwhy\b|\bproblem|wrong", text) and not re.search(r"mesh|converg|accurac|reliab", text):
        topic = "diagnosis"
        ratio = m["sampled_von_mises_mpa"] / m["assumed_yield_mpa"]
        answer = (f"The reported sampled elastic stress is {m['sampled_von_mises_mpa']:.3f} MPa "
                  f"against an assumed yield of {m['assumed_yield_mpa']:.3f} MPa (ratio {ratio:.3f}). ")
        answer += ("That exceeds the assumed yield; the linear-elastic result is insufficient. " if ratio > 1 else
                   "It does not exceed that particular assumed limit; this is not an overall safety pass. ")
        answer += "Review findings: " + ("; ".join(review["issues"]) or "only a preliminary numerical screen is available") + "."
        citation += ["metrics.sampled_von_mises_mpa", "metrics.assumed_yield_mpa", "issues"]
    elif re.search(r"mesh|converg|accurac|reliab", text):
        topic = "mesh_evidence"
        answer = (f"Mesh assessment: {review['mesh_assessment']}. "
                  f"This solve uses {review['tetrahedra']} input tetrahedra at target size {review['mesh_size_mm']:g} mm. "
                  "Use the source-locked three-mesh study to check sensitivity. Global displacement stability "
                  "does not establish convergence of local peak stress.")
        citation += ["mesh_assessment", "tetrahedra", "mesh_size_mm"]
        if "stress_assessment" in review:
            stress = review["stress_assessment"]
            answer += (f" Local peak stress: {stress['local_peak_status']}; fixed physical band: "
                       f"{stress['physical_band_stress_status']}; overall evidence: {stress['engineering_evidence_status']}.")
            if stress.get("fine_vs_medium_stress_percent") is not None:
                answer += f" Fine-to-medium sampled peak-stress change: {stress['fine_vs_medium_stress_percent']:.2f}%."
            citation += ["stress_assessment"]
    elif re.search(r"lighter|optimi|redesign|improv|next|recommend|reduce.*mass", text):
        topic = "next_steps"
        answer = (f"The reported mass is {m['mass_kg']:.5f} kg. To assess a lighter design, use the CAD revision "
                  "workflow to independently remesh and solve candidate geometry under the same load, material "
                  "and supports, then compare mass, displacement and sampled stress. Run the mesh-sensitivity "
                  "study as a separate evidence check. No improved candidate has been calculated by this answer.")
        citation += ["metrics.mass_kg", "mesh_assessment"]
    elif re.search(r"stress|von.?mises|displacement|deflection|movement|mass|result", text):
        topic = "results"
        answer = (f"Reported tip displacement: {m['tip_displacement_mm']:.5f} mm; "
                  f"maximum nodal displacement: {m['max_displacement_mm']:.5f} mm; "
                  f"sampled von Mises: {m['sampled_von_mises_mpa']:.3f} MPa; mass: {m['mass_kg']:.5f} kg. "
                  "These are FE predictions, not physical measurements.")
        citation += ["metrics.tip_displacement_mm", "metrics.max_displacement_mm", "metrics.sampled_von_mises_mpa", "metrics.mass_kg"]
    else:
        topic = "clarification"
        answer = ("I can explain this completed result, diagnose assumed-limit or mesh-evidence gaps, and "
                  "suggest a verified redesign workflow. Try 'Why is this design failing?', 'Has the mesh "
                  "converged?', or 'How can I make this lighter?'. For a new calculation, specify a change "
                  "such as 'Increase the load to 300 N' and confirm the extracted parameters.")
    return {"language":"en", "topic":topic,
            "text": f"For the completed {load:g} N case (CAD {source[:12]}): " + answer,
            "evidence_fields":citation, "review_id":review["review_id"],
            "note":"No new solve was run. Change requests require parameter preview and confirmation."}


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
    stress_assessment = {"local_peak_status":"NOT_EVALUATED", "physical_band_stress_status":"NOT_EVALUATED",
                         "engineering_evidence_status":"NOT_EVALUATED"}
    if mesh_evidence is not None:
        if mesh_evidence.source_sha256 != mesh.source_sha256 or mesh_evidence.load != load:
            raise ValueError("Mesh evidence belongs to a different CAD or engineering context")
        if not any(math.isclose(row.target_size_mm, mesh.mesh_size_mm)
                   and row.tetrahedra == mesh.num_tets
                   and math.isclose(row.tip_mm, result.tip_mm, rel_tol=1e-9, abs_tol=1e-12)
                   for row in mesh_evidence.ordered_rows):
            raise ValueError("The current FE solve is not a baseline in this mesh study")
        mesh_status = mesh_evidence.decision
        # v1.1 adds separate stress screens; v1.0 cannot imply their presence.
        for field in stress_assessment:
            value = getattr(mesh_evidence, field, "NOT_EVALUATED")
            if not isinstance(value, str):
                raise ValueError("Invalid local-stress evidence status")
            stress_assessment[field] = value
        for field in ("fine_vs_medium_stress_percent", "fine_medium_probe_mean_percent",
                      "fine_medium_probe_p90_percent", "fine_medium_hotspot_drift_mm"):
            value = getattr(mesh_evidence, field, None)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("Invalid local-stress evidence metric")
            stress_assessment[field] = value
        for field in ("local_peak_status", "physical_band_stress_status"):
            status = stress_assessment[field]
            if status != "NOT_EVALUATED" and not status.startswith("PRELIMINARY_"):
                issues.append("Local stress study: " + status)
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
        "stress_assessment": stress_assessment,
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
