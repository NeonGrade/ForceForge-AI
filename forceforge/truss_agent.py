"""English-first, offline truss assistance; no solver or model calls here."""
import math
import re

from pydantic import BaseModel, ConfigDict, FiniteFloat

from .provenance import context_id


class TrussProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_id: str
    changes: dict[str, FiniteFloat]


FIELDS = {
    "span_m": (r"\bspan\b", r"metres?|meters?|cm|m", {"metre":1, "metres":1, "meter":1, "meters":1, "cm":.01, "m":1}),
    "base_load_n": (r"\b(?:central\s+)?(?:load|force)\b|\bunder\b|\bapply(?:\s+a)?\b", r"kN|newtons?|N", {"kn":1000, "newton":1, "newtons":1, "n":1}),
    "max_displacement_mm": (r"\b(?:displacement|deflection)(?:\s+limit)?\b", r"mm|millimetres?|millimeters?", {"mm":1, "millimetre":1, "millimetres":1, "millimeter":1, "millimeters":1}),
    "height_m": (r"\bheight\b", r"metres?|meters?|cm|m", {"metre":1, "metres":1, "meter":1, "meters":1, "cm":.01, "m":1}),
    "area_mm2": (r"\b(?:section\s+)?area\b", r"mm(?:\^?2|²)", {"mm2":1, "mm^2":1, "mm²":1}),
}


def propose_truss_inputs(prompt: str, current: dict) -> TrussProposal:
    """Change only explicitly specified fields, keeping all other inputs."""
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1600:
        raise ValueError("Enter an English question or request (1–1600 characters)")
    prompt = prompt.replace("−", "-")
    # Reject unsupported physics rather than silently converting it to a central load.
    if re.search(r"\b(?:distributed|uniformly distributed|udl|temperature|thermal|plastic|fatigue|wind|lateral|material|topology|support|uncertainty|modulus|yield)\b|\bsafety\s+factor\b", prompt, re.I):
        raise ValueError("This brief supports central load, span, height, section area and displacement limit only; use the workspace controls for other supported settings")
    number = r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    changes = {}
    for key, (label, units, factors) in FIELDS.items():
        patterns = [
            rf"(?:{label})\s*(?:(?:is\s+set\s+to|should\s+be|to|at|of|is|=|:)\s*)?{number}\s*({units})(?![A-Za-z0-9/])",
            rf"{number}\s*({units})(?![A-Za-z0-9/])\s+(?:{label})",
        ]
        if key == "span_m":
            patterns.append(rf"{number}\s*({units})(?![A-Za-z0-9/])\s+(?:truss|bridge)\b")
        matches = [m for pattern in patterns for m in re.finditer(pattern, prompt, re.I)]
        values = [float(m.group(1)) * factors[m.group(2).lower()] for m in matches]
        relative = list(re.finditer(
            rf"\b(increase|raise|reduce|decrease|lower)\s+(?:the\s+)?(?:{label})\s+by\s+{number}\s*(?:%|percent\b)", prompt, re.I))
        multipliers = list(re.finditer(rf"\b(double|halve)\s+(?:the\s+)?(?:{label})", prompt, re.I))
        for match in relative:
            percent = float(match.group(2))
            if not math.isfinite(percent) or percent < 0:
                raise ValueError("Percentage must be finite and nonnegative")
            sign = 1 if match.group(1).lower() in ("increase", "raise") else -1
            values.append(current[key] * (1 + sign * percent / 100))
        for match in multipliers:
            values.append(current[key] * (2 if match.group(1).lower() == "double" else .5))
        if re.search(label, prompt, re.I) and not values:
            raise ValueError(f"Specify one explicit value and supported unit for {key}")
        if values:
            if not all(math.isfinite(v) and math.isclose(v, values[0], rel_tol=1e-12, abs_tol=1e-12) for v in values):
                raise ValueError(f"Conflicting or non-finite values for {key}")
            changes[key] = values[0]
    if not changes:
        raise ValueError("Specify a central load, span, height, section area or displacement limit with units")
    return TrussProposal(input_id=context_id(current), changes=changes)


def confirm_truss_inputs(proposal: dict, current: dict) -> dict:
    proposal = TrussProposal.model_validate(proposal)
    if proposal.input_id != context_id(current):
        raise ValueError("Inputs changed after preview; understand the request again")
    if not proposal.changes or not set(proposal.changes) <= FIELDS.keys():
        raise ValueError("Unsupported truss parameter changes")
    return {**current, **proposal.changes}


def answer_truss_question(question: str, evidence: dict) -> dict:
    """Explain a server-held, completed nominal + scenario result in English."""
    a, r = evidence["analysis"], evidence["robust"]
    text = question.lower()
    checks = {"axial stress": r["worst_stress_util"], "displacement": r["worst_displacement_util"],
              "idealized member buckling": r["worst_buckling_util"]}
    governing = max(checks, key=checks.get)
    fields = ["robust.worst_utilization"]
    if re.search(r"\bsafe\b|certif|physical|plastic|fatigue|3d|cad|support|distributed", text):
        topic = "validation_scope"
        answer = ("This is an idealized 2D pin-jointed, linear-elastic axial-bar model with a central point load. "
                  "Its scenario checks do not establish real-world safety, joints, fatigue, plasticity or out-of-plane behavior. "
                  "Use the separate 3D Studio for its supported solid/CAD workflows; truss results cannot validate those solids.")
        fields = ["context.solver", "context.requirements"]
    elif re.search(r"\bml\b|surrogate|machine learning|holdout|accuracy", text):
        topic = "ml_scope"
        answer = ("The Random Forest screens only these implemented 2D truss families under the current load, material, "
                  "constraints and solver version. In ML Verify, compare grouped-design and whole-height holdouts, "
                  "the training-mean baseline and prediction-versus-FEA error. Every shortlisted candidate is solved again. "
                  "A holdout score does not validate new topology families or 3D CAD; no new ML run was performed by this answer.")
        fields = ["context"]
    elif re.search(r"uncertain|scenario|robust|safety factor", text):
        topic = "scenarios"
        req = evidence["context"]["requirements"]
        answer = (f"The scenario screen combines load up to +{100*req['load_uncertainty']:g}%, modulus down to "
                  f"−{100*req['e_uncertainty']:g}% and section area down to −{100*req['area_uncertainty']:g}%. "
                  f"Yield and Euler buckling safety factors are {req['yield_safety_factor']:g} and {req['buckling_safety_factor']:g}. "
                  f"The governing scenario check is {governing}, utilization {checks[governing]:.3f}; a value <= 1 passes that check.")
        fields += ["context.requirements", "robust.worst_stress_util", "robust.worst_displacement_util", "robust.worst_buckling_util"]
    elif re.search(r"lighter|redesign|optimi|improv|recommend|next|reduce.*mass", text):
        topic = "next_steps"
        answer = (f"The current nominal mass is {a['mass_kg']:.3f} kg and the governing scenario check is {governing} "
                  f"at {checks[governing]:.3f}. Use Optimize or ML Verify to screen and FEA-check candidates under the same "
                  "requirements, then review all three constraints before applying a design. No improved candidate was computed by this answer.")
        fields += ["analysis.mass_kg"]
    elif re.search(r"fail|pass|why|buckl|govern|limit|problem", text):
        topic = "diagnosis"
        answer = (f"The scenario screen {'passes' if r['feasible'] else 'fails'}: {governing} governs at utilization "
                  f"{checks[governing]:.3f} (<= 1 passes). Axial stress {checks['axial stress']:.3f}, "
                  f"displacement {checks['displacement']:.3f}, idealized member buckling {checks['idealized member buckling']:.3f}. "
                  "These are worst-case scenario utilizations; the viewport shows nominal results. Passing is a preliminary screen, not certification.")
        fields += ["robust.feasible", "robust.worst_stress_util", "robust.worst_displacement_util", "robust.worst_buckling_util"]
    elif re.search(r"stress|displacement|deflection|mass|result|reaction|force", text):
        topic = "results"
        answer = (f"Nominal FEA reports mass {a['mass_kg']:.3f} kg, maximum displacement {a['max_displacement_mm']:.5f} mm, "
                  f"maximum axial stress {a['max_stress_mpa']:.3f} MPa and force-equilibrium residual "
                  f"{a['equilibrium_residual_n']:.3g} N. These are computed axial-bar results, not measured or von Mises solid stresses.")
        fields = ["analysis.mass_kg", "analysis.max_displacement_mm", "analysis.max_stress_mpa", "analysis.equilibrium_residual_n"]
    else:
        topic = "clarification"
        answer = ("I can explain the completed truss result, governing constraints, scenarios, ML scope and a verified redesign workflow. "
                  "Try 'Why does this design fail?' or 'What is the displacement?'. For a new calculation, try "
                  "'Increase the load by 20%' and review the proposed changes.")
        fields = []
    answer = f"For the completed {a['load_n']:g} N {a['topology']} case (span {a['span_m']:g} m, height {a['height_m']:g} m): " + answer
    return {"language":"en", "topic":topic, "text":answer, "evidence_fields":fields,
            "review_id":evidence["review_id"], "note":"No new FEA or ML run was performed. Answers refer to the completed current 2D case."}
