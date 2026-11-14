"""Optional structured-requirements AI Agent with reliable offline fallback.

LLM is NOT permitted to calculate structural results or bypass physics checks.
Only bounded load/span/deflection values are used downstream.
"""
import os
import re
from pydantic import BaseModel, Field


class ProposedRequirements(BaseModel):
    span_m: float = Field(description="Bridge span in metres")
    load_n: float = Field(description="Vertical applied load in Newtons")
    max_displacement_mm: float = Field(description="Allowable node displacement in millimetres")
    rationale: str = Field(description="One-sentence interpretation of the requirement")


def _validate(x: ProposedRequirements) -> ProposedRequirements:
    if not 0.25 <= x.span_m <= 5:
        raise ValueError("Span must be within 0.25-5 metres for this prototype")
    if not 10 <= x.load_n <= 5000:
        raise ValueError("Load must be within 10-5000 N for this prototype")
    if not 0.1 <= x.max_displacement_mm <= 20:
        raise ValueError("Displacement limit must be within 0.1-20 mm")
    return x


def parse_offline(prompt: str) -> ProposedRequirements:
    def search(pattern: str, default: float) -> float:
        m = re.search(pattern, prompt, re.I)
        return float(m.group(1)) if m else default
    span = search(r"(\d+(?:\.\d+)?)\s*(?:metres?|meters?|m\b)", 2.0)
    load = search(r"(\d+(?:\.\d+)?)\s*(?:n\b|newtons?)", 1000.0)
    displacement = search(r"(?:deflection|displacement|limit|deformation)[^\d]{0,30}(\d+(?:\.\d+)?)\s*mm", 2.0)
    return _validate(ProposedRequirements(
        span_m=span, load_n=load,
        max_displacement_mm=displacement,
        rationale="Offline deterministic parser. Verify values against manual inputs before optimization.",
    ))


def interpret(prompt: str, *, use_api: bool = False) -> ProposedRequirements:
    if not use_api or not os.environ.get("OPENAI_API_KEY"):
        return parse_offline(prompt)
    from openai import OpenAI
    client = OpenAI()
    response = client.responses.parse(
        model=os.getenv("FORCEFORGE_MODEL", "gpt-4o-mini"),
        input=[
            {"role": "system", "content": (
                "Convert structural design requests into valid numerical inputs for a "
                "2D linear truss demo. Do not invent engineering calculations. "
                "Use defaults: span=2m, load=1000N, maximum displacement=2mm "
                "when not specified; state defaults clearly in rationale. "
                "All loads are point loads at the implemented central node; "
                "do not infer other supports or load cases.")},
            {"role": "user", "content": prompt},
        ],
        text_format=ProposedRequirements,
    )
    if response.output_parsed is None:
        raise ValueError("AI returned no parseable design requirements")
    return _validate(response.output_parsed)


def explain_design(design: dict | None) -> str:
    if design is None:
        return "No candidate satisfies all specified scenarios. Relax constraints or enlarge the search range."
    util_names = {
        "worst_stress_util": "axial stress", "worst_displacement_util": "displacement",
        "worst_buckling_util": "idealized member buckling"
    }
    limiting = max(util_names, key=lambda name: design[name])
    return (
        f"FEA-verified {design['topology']} design: height {design['height_m']:.3f} m, "
        f"uniform round-bar section {design['area_mm2']:.1f} mm^2, "
        f"nominal mass {design['mass_kg']:.3f} kg. "
        f"Controlling scenario check: {util_names[limiting]} "
        f"at utilization {design[limiting]:.3f} (<= 1 passes). "
        "This is a preliminary linear-elastic truss screen, not a certified safe design."
    )
