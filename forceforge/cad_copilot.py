"""Bounded AI-to-CAD proposal layer; ONLY real tetra10 FEM may score designs.

Designed for the existing drilled L-bracket parametric STEP generator. The
optional language model is limited to suggesting an evaluation ORDER and
reasoning, never stress/mass/displacement numbers, geometry bytes, file paths
or unrestricted arbitrary Python. Every available different thickness is
independently CAD-generated and FEM-checked before selection.

The no-key/no-API path is explicitly a rule-based exhaustive search, not AI.
All numerical verdicts remain preliminary under idealized boundary conditions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
from typing import Any

from pydantic import BaseModel, Field

THICKNESSES_MM = (8, 10, 12, 14)


@dataclass(frozen=True)
class DesignLimits:
    max_tip_mm: float
    max_sampled_stress_mpa: float
    max_mass_increase_percent: float

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a number")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if not .001 <= self.max_tip_mm <= 20:
            raise ValueError("Tip displacement limit must be between 0.001 and 20 mm")
        if not 1 <= self.max_sampled_stress_mpa <= 1800:
            raise ValueError("Sampled stress limit must be between 1 and 1800 MPa")
        if not 0 <= self.max_mass_increase_percent <= 250:
            raise ValueError("Mass budget must be 0-250% above starting design")


class LLMProposal(BaseModel):
    """An LLM describes intent and ordering, NOT verified physics values."""
    candidate_thickness_mm: list[int] = Field(
        description="Two or three distinct sizes selected from the allowed sizes, ordered by preference"
    )
    rationale: str = Field(
        description="One or two sentences explaining why these CAD parameter changes might help; no invented numerical results"
    )


@dataclass(frozen=True)
class DesignProposal:
    mode: str
    candidates_mm: tuple[int, ...]
    llm_priorities_mm: tuple[int, ...]
    rationale: str
    message: str
    model_name: str | None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CandidateEvidence:
    thickness_mm: int
    source_sha256: str
    tetrahedra: int
    mass_kg: float
    mass_change_pct: float
    tip_mm: float
    peak_von_mises_mpa: float
    reaction_residual: float
    volume_difference_pct: float
    min_shape_quality: float
    numerical_qa_pass: bool
    constraints_pass: bool
    status: str
    failure_reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


def _allowed_after_baseline(original_thickness_mm: int) -> tuple[int, ...]:
    if original_thickness_mm not in THICKNESSES_MM:
        raise ValueError("This CAD copilot supports the editable 8/10/12/14 mm L-bracket only")
    return tuple(t for t in THICKNESSES_MM if t != original_thickness_mm)


def _llm_proposal(*, brief: str, original: int, allowed: tuple[int, ...],
                  baseline: Any, limits: DesignLimits, api_key: str) -> LLMProposal:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, timeout=12., max_retries=0)
    result = client.responses.parse(
        model=os.environ.get("FORCEFORGE_CAD_MODEL", "gpt-4o-mini"),
        input=[
            {"role": "system", "content": (
                "You are a design-IDEA assistant in a controlled engineering demo. "
                "You may prioritize ONLY two or three DISTINCT bracket web thickness "
                "options from the allowed list, to be generated as real STEP solids "
                "and physically analyzed by an independent tetra10 FEA solver. "
                "Do not calculate, predict, infer or invent masses, strains, "
                "stress, displacements, convergence or safety approval. "
                "Do not change loads, support, materials, geometry family, or "
                "ask to execute code. The code will assess all available options "
                "regardless of your order. Keep a short rationale; uncertainty "
                "and physical validation limitations must be acknowledged."
            )},
            {"role": "user", "content": (
                f"Design brief: {brief[:500]}\n"
                f"Original web: {original} mm. Allowed alternatives: {list(allowed)} mm.\n"
                f"Existing tetra10 FEA outputs: mass {baseline.mass_kg:.5g} kg, "
                f"tip displacement {baseline.tip_mm:.5g} mm, "
                f"sampled von Mises {baseline.peak_von_mises_mpa:.5g} MPa.\n"
                f"Illustrative limits: max tip {limits.max_tip_mm:g} mm, "
                f"max sampled stress {limits.max_sampled_stress_mpa:g} MPa, "
                f"max mass increase {limits.max_mass_increase_percent:g}%. "
                "Provide only candidate thicknesses and a qualitative rationale."
            )},
        ],
        text_format=LLMProposal,
    )
    if result.output_parsed is None:
        raise ValueError("AI returned no structured CAD proposal")
    return result.output_parsed


def propose_designs(*, brief: str, original_thickness_mm: int,
                    baseline: Any, limits: DesignLimits, use_api: bool=False,
                    api_key: str | None=None) -> DesignProposal:
    """Return exhaustive CAD options, optionally ordered by strict LLM output.

    No FEM happens here. The caller MUST separately regenerate STEP, remesh,
    and solve every candidate. The order cannot override physical screening.
    """
    allowed = _allowed_after_baseline(original_thickness_mm)
    brief = str(brief or "").strip()
    if len(brief) > 500:
        raise ValueError("Design brief is limited to 500 characters")
    if not math.isfinite(baseline.mass_kg) or baseline.mass_kg <= 0:
        raise ValueError("Baseline FEA mass must be finite and positive")
    for value in (baseline.tip_mm, baseline.peak_von_mises_mpa):
        if not math.isfinite(value) or value < 0:
            raise ValueError("Baseline FEA values must be valid")
    prioritized: tuple[int, ...] = ()
    mode = "RULE_BASED_FULL_SEARCH"
    model_name = None
    message = "No AI API used. All bounded parametric CAD designs are checked with real FEA."
    rationale = (
        "Sweep each alternate bracket thickness to evaluate the actual "
        "stiffness/mass/stress trade-off under the same assumed loading."
    )
    if use_api:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if key:
            try:
                suggestion = _llm_proposal(
                    brief=brief, original=original_thickness_mm,
                    allowed=allowed, baseline=baseline,
                    limits=limits, api_key=key,
                )
                raw = suggestion.candidate_thickness_mm
                if (not isinstance(raw, list) or len(raw) not in (2, 3)
                        or any(type(t) is not int for t in raw)
                        or len(set(raw)) != len(raw)
                        or any(t not in allowed for t in raw)):
                    raise ValueError("AI proposed unsupported or duplicate CAD dimensions")
                prioritized = tuple(raw)
                rationale = suggestion.rationale[:400].strip()
                if not rationale:
                    raise ValueError("AI provided no engineering rationale")
                mode = "LLM_PRIORITIZED_WITH_REAL_FEA"
                model_name = os.environ.get("FORCEFORGE_CAD_MODEL", "gpt-4o-mini")
                message = (
                    "Validated structured LLM proposal. The software will also "
                    "test remaining allowed sizes; only measured FEA results "
                    "determine design feasibility."
                )
            except Exception as exc:
                message = (
                    "AI unavailable or invalid ("
                    + type(exc).__name__
                    + "); switched to explicit rules-based exhaustive search."
                )
        else:
            message = (
                "AI requested but no API key is present. "
                "Running the explicitly labeled rules-based search."
            )
    # All alternative dimensions are always independently evaluated; LLM
    # determines only search priority, NEVER a numerical PASS or stress result.
    ordered = prioritized + tuple(t for t in allowed if t not in prioritized)
    return DesignProposal(mode, ordered, prioritized, rationale, message, model_name)


def evaluate_candidate(*, original: Any, candidate: Any,
                       thickness_mm: int, limits: DesignLimits) -> CandidateEvidence:
    """Consume ONLY real computed FEA outcomes; never calculate pseudo-stress."""
    if thickness_mm not in THICKNESSES_MM:
        raise ValueError("Candidate must be a supported parametric CAD thickness")
    if original.mesh.source_sha256 == candidate.mesh.source_sha256:
        raise ValueError("CAD did not change: source STEP SHA-256 hashes are identical")
    if original.load != candidate.load:
        raise ValueError("Cannot compare different assumed material/force/support parameters")
    values = (original.mass_kg, candidate.mass_kg, candidate.tip_mm,
              candidate.peak_von_mises_mpa,
              candidate.relative_reaction_residual,
              candidate.mesh.relative_volume_difference,
              candidate.mesh.min_shape_quality)
    if not all(math.isfinite(float(v)) for v in values) or original.mass_kg <= 0:
        raise ValueError("Non-finite or invalid FEA candidate results")
    mass_change = 100*(candidate.mass_kg/original.mass_kg-1)
    reason = []
    numerical = (
        candidate.mesh.num_tets > 0 and
        candidate.relative_reaction_residual <= 1e-5 and
        candidate.mesh.relative_volume_difference <= .20 and
        candidate.mesh.min_shape_quality > 0
    )
    if not numerical:
        reason.append("Numerical/mesh/force-balance quality gate did not pass")
    if candidate.tip_mm > limits.max_tip_mm:
        reason.append("Displacement exceeds illustrative limit")
    if candidate.peak_von_mises_mpa > limits.max_sampled_stress_mpa:
        reason.append("Sampled stress exceeds illustrative limit")
    if mass_change > limits.max_mass_increase_percent:
        reason.append("Mass increase exceeds budget")
    if candidate.peak_von_mises_mpa * 1e6 > candidate.load.yield_pa:
        reason.append("Elastic stress exceeds assumed yield; linear model invalid")
    passed = not reason
    return CandidateEvidence(
        thickness_mm=int(thickness_mm),
        source_sha256=str(candidate.mesh.source_sha256),
        tetrahedra=int(candidate.mesh.num_tets),
        mass_kg=float(candidate.mass_kg),
        mass_change_pct=float(mass_change),
        tip_mm=float(candidate.tip_mm),
        peak_von_mises_mpa=float(candidate.peak_von_mises_mpa),
        reaction_residual=float(candidate.relative_reaction_residual),
        volume_difference_pct=float(100*candidate.mesh.relative_volume_difference),
        min_shape_quality=float(candidate.mesh.min_shape_quality),
        numerical_qa_pass=bool(numerical),
        constraints_pass=bool(passed),
        status="PRELIMINARY_MODEL_CONSTRAINTS_MET" if passed
            else "REJECTED_BY_MODEL_SCREEN",
        failure_reasons=tuple(reason),
    )


def pick_lightest_feasible(rows: list[CandidateEvidence] | tuple[CandidateEvidence, ...]) -> int | None:
    """Winner among actually tested discrete designs; none if no candidate passes."""
    valid = [x for x in rows if x.constraints_pass and x.numerical_qa_pass]
    return min(valid, key=lambda x: (x.mass_kg, x.tip_mm)).thickness_mm if valid else None
