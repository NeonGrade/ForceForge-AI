"""Evidence-first cross-industry design decisions. Every proposal reruns FEA.

Outputs are MODEL SCREENS under illustrative assumed loads, not approvals.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Mapping

from .industry import CaseInputs, CaseReport, run_industry_case


@dataclass(frozen=True)
class UserMission:
    industry: str
    headline: str
    question: str
    use_case: str
    plain_failure: str
    fidelity: str


MISSIONS: Mapping[str, UserMission] = {
    "Building": UserMission(
        "Building", "Roof support",
        "Could a light steel truss handle a heavier roof load?",
        "A roof structure must carry changing service and environmental loads without excessive stress, movement or bar instability.",
        "Axial stress, joint displacement, or ideal member buckling could exceed the illustrative bound.",
        "2D global truss load-path example; actual snow, wind, bracing and joint design are not modeled.",
    ),
    "Industrial": UserMission(
        "Industrial", "Machine support",
        "What if a machine bracket sees a stronger startup force?",
        "Mounting hardware can bend and rotate under mechanical loads. A flexible connection may govern the response even if the beam is thickened.",
        "The beam may bend too far or exceed the illustrative axial+bending stress limit.",
        "2D beam and equivalent joint spring; no real anchors, bolts or contact mechanics.",
    ),
    "Automotive": UserMission(
        "Automotive", "Suspension link",
        "How does a suspension link respond to stronger road loads?",
        "A suspension component must manage combinations of vertical, braking and cornering loads. This example compares projected planar load paths.",
        "Illustrative member stress or displacement could exceed a selected bound.",
        "2D planar link proxy. No wheel dynamics, 3D contact, bushings or road durability validation.",
    ),
}

# Uniform RADIUS scaling of solid-round sections: area scales r^2; I scales r^4.
RADIUS_OPTIONS = (0.70, 0.80, 0.85, 0.90, 1.00, 1.10, 1.20, 1.35, 1.50, 1.80, 2.10)
JOINT_OPTIONS = (1.0, 2.5, 5.0)


@dataclass
class Improvement:
    baseline: CaseReport
    redesigned: CaseReport | None
    design_inputs: CaseInputs | None
    alternatives_checked: int
    feasible_candidates: int
    search_scope: str
    lessons: tuple[str, ...]

    @property
    def mass_delta_percent(self) -> float | None:
        if self.redesigned is None:
            return None
        m0 = self.baseline.figures["mass_kg"]
        return 100 * (self.redesigned.figures["mass_kg"] / m0 - 1)


def demo_case(sector: str, *, load_scale: float = 1.0) -> CaseInputs:
    """Purpose-specific example assumptions, not measured engineering data."""
    if sector not in MISSIONS:
        raise ValueError(f"Unknown sector: {sector}")
    # Default automotive thermal change to zero to isolate mechanical road-load effects.
    delta_t = 0.0 if sector == "Automotive" else 50.0
    return CaseInputs(sector=sector, load_scale=load_scale,
                      temperature_change_k=delta_t,
                      joint_stiffness_nm_rad=200_000.0,
                      service_cycles=200_000, section_scale=1.0)


def model_margin(report: CaseReport) -> float:
    return 1.0 - float(report.governing["max_utilization"])


def failure_explanation(report: CaseReport) -> str:
    limit = float(report.governing["max_utilization"])
    check = report.governing["controlling_check"]
    if limit > 1.0:
        return f"Modeled limit exceeded ({check}, {limit:.2f}x of the illustrative allowance)."
    return f"Within modeled limits ({check} is controlling, {limit:.2f}x of the illustrative allowance)."


def recommend_design(inputs: CaseInputs,
                     *, radii: tuple[float, ...] = RADIUS_OPTIONS,
                     joint_options: tuple[float, ...] | None = None) -> Improvement:
    """Enumerate section radii and support-spring alternatives, FEA-verifying all.

    The mass objective covers members ONLY. Changing a support joint stiffness
    requires unmodeled connection hardware and cost; it is NOT a cost optimum.
    """
    baseline = run_industry_case(inputs)
    if joint_options is None:
        joint_options = (1.0,) if inputs.sector == "Building" else JOINT_OPTIONS
    checked = 0
    options = []
    for radius in radii:
        for multiplier in joint_options:
            settings = replace(inputs, section_scale=float(radius),
                               joint_stiffness_nm_rad=inputs.joint_stiffness_nm_rad * float(multiplier))
            checked += 1
            try:
                result = run_industry_case(settings)
            except (ValueError, ArithmeticError, OverflowError, FloatingPointError):
                continue
            if model_margin(result) >= -1e-10:
                options.append((result.figures["mass_kg"], multiplier,
                                result.governing["max_utilization"], settings, result))
    if not options:
        return Improvement(baseline, None, None, checked, 0,
            "Discrete section-radius and joint-spring grid, exact solver recomputation",
            ("No sampled combination met the illustrative limits.",
             "Change geometry, supports or assumptions; do not extrapolate a failed model."))
    options.sort(key=lambda row: (row[0], row[1], row[2]))
    _, joint_mult, _, settings, selected = options[0]
    lessons = [
        "Every suggested candidate was checked against the same three modeled load cases by FEA.",
        "Member mass only is optimized; this excludes connections, fabrication and labor.",
    ]
    if joint_mult != 1.0:
        lessons.append(f"Modeled joint rotational stiffness increases {joint_mult:g}x; no physical reinforcement has been designed or priced.")
    return Improvement(baseline, selected, settings, checked, len(options),
        "Discrete section-radius and joint-spring grid, exact solver recomputation",
        tuple(lessons))
