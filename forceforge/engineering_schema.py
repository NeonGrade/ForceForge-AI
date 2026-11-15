"""Versioned, unit-explicit input contract for the ForceForge natural-language CAD pipeline.

Only explicitly registered mechanical product families can execute. Unknown
families and missing physics assumptions remain unresolved; no invented
loads, pressures, CFD contours or mesh convergence claims are permitted.
"""
from __future__ import annotations

from enum import Enum
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ProductFamily(str, Enum):
    L_BRACKET = "l_bracket"
    WALL_FAN = "wall_fan"


class AnalysisIntent(_Strict):
    structural_fea: bool = False
    fluid_cfd: bool = False
    thermal: bool = False


class BracketGeometry(_Strict):
    family: Literal["l_bracket"] = "l_bracket"
    web_thickness_mm: Literal[8, 10, 12, 14] | None = None


class FanGeometry(_Strict):
    family: Literal["wall_fan"] = "wall_fan"
    diameter_mm: float | None = Field(default=None, ge=100, le=800)
    rpm: float | None = Field(default=None, ge=0, le=5000)
    blade_count: int | None = Field(default=None, ge=3, le=9)
    hub_diameter_mm: float | None = Field(default=None, ge=20, le=350)
    blade_pitch_deg: float | None = Field(default=None, ge=5, le=45)

    @model_validator(mode="after")
    def check_hub(self):
        if (self.diameter_mm is not None
                and self.hub_diameter_mm is not None
                and self.hub_diameter_mm >= .55*self.diameter_mm):
            raise ValueError("Fan hub diameter must be less than 55% of fan diameter")
        return self


class MaterialData(_Strict):
    E_gpa: float | None = Field(default=None, gt=0, le=400)
    poisson: float | None = Field(default=None, gt=0, lt=.49)
    density_kg_m3: float | None = Field(default=None, gt=0, le=20000)
    yield_mpa: float | None = Field(default=None, gt=0, le=1800)


class MechanicalLoads(_Strict):
    force_n: float | None = Field(default=None, gt=0, le=50000)
    force_axis: Literal["X", "Y", "Z"] | None = None
    support_axis: Literal["X", "Y", "Z"] | None = None
    # Wall-fan mounting loads/anchors cannot be inferred from RPM alone.
    anchor_specification: str | None = Field(default=None, max_length=180)


class EngineeringRequest(_Strict):
    schema_version: Literal["1.0"] = "1.0"
    prompt: str = Field(min_length=3, max_length=1200)
    family: ProductFamily
    geometry: BracketGeometry | FanGeometry = Field(discriminator="family")
    analyses: AnalysisIntent = Field(default_factory=AnalysisIntent)
    loads: MechanicalLoads = Field(default_factory=MechanicalLoads)
    material: MaterialData = Field(default_factory=MaterialData)
    mesh_size_mm: float = Field(default=12., ge=5, le=15)
    assumptions: tuple[str, ...] = ()
    concept_assumptions_confirmed: bool = False
    extraction_mode: Literal["EXPLICIT_RULE_EXTRACTION", "LLM_CLASSIFICATION_RULE_VALUES"] = "EXPLICIT_RULE_EXTRACTION"

    @model_validator(mode="after")
    def matched_family(self):
        if self.family.value != self.geometry.family:
            raise ValueError("Selected product family and geometry parameters disagree")
        return self


class Interpretation(_Strict):
    request: EngineeringRequest | None = None
    issues: tuple[str, ...] = ()
    supported_families: tuple[str, ...] = ("l_bracket", "wall_fan")


def _length_mm(raw: str, unit: str) -> float:
    val = float(raw)
    if unit in ("cm", "厘米", "公分"):
        return val * 10
    if unit in ("m", "米"):
        return val * 1000
    if unit in ("in", "inch", "英寸"):
        return val * 25.4
    return val


_LENGTH_UNIT = r"(mm|毫米|cm|厘米|公分|(?<!m)m|米|in|inch|英寸)"
_NUMBER = r"([0-9]+(?:\.[0-9]+)?)"


def _extract_length(text: str, words: str) -> float | None:
    """Extract only dimension numbers literally attributed to a feature."""
    m = re.search(
        rf"(?:{words})\s*(?:about|around|approximately|大约|大概|约|为|是|:|：|=)?"
        rf"\s*{_NUMBER}\s*{_LENGTH_UNIT}", text, re.I,
    )
    return _length_mm(m.group(1), m.group(2)) if m else None


def _extract_rpm(text: str) -> float | None:
    patterns = (
        rf"(?:转速|speed|rotation)\s*(?:about|around|约|为|是|:|：|=)?\s*{_NUMBER}\s*(?:rpm|r/min|转/分钟|转每分钟|转)?",
        rf"{_NUMBER}\s*(?:rpm|r/min|转/分钟|转每分钟)",
        rf"每分钟\s*{_NUMBER}\s*转",
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return float(m.group(1))
    return None


def _extract_force_n(text: str) -> float | None:
    patterns = (
        rf"(?:载荷|施加力|施加|force|load)\s*(?:about|around|约|为|是|:|：|=)?\s*{_NUMBER}\s*(n|牛顿|kn)",
        rf"{_NUMBER}\s*(n|牛顿|kn)\s*(?:载荷|力|force|load)?",
    )
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return float(m.group(1))*(1000 if m.group(2).lower()=="kn" else 1)
    return None


def interpret_text(text: str) -> Interpretation:
    """Deterministic conservative fallback; no inference of missing numbers.

    Handles a small documented subset of Chinese/English mechanical requests.
    Novel product families are explicit unsupported extensions, not silently
    mapped to a bracket or an unrelated fake model.
    """
    text = " ".join(str(text).split())
    if not 3 <= len(text) <= 1200:
        return Interpretation(issues=("Enter a 3-1200 character engineering description.",))
    fan = re.search(r"(wall[- ]?mounted fan|wall fan|axial fan|electric fan|风扇|电扇|风机|轴流)", text, re.I)
    bracket = re.search(r"(l[- ]?bracket|l[- ]?shaped bracket|l型支架|l形支架|l 型支架|支架)", text, re.I)
    if fan:
        family = ProductFamily.WALL_FAN
        dia = _extract_length(text, r"(?<!轮毂)(?:叶轮|扇叶)?直径|(?<!hub )diameter|外径")
        # Also recognize "30 cm diameter" and Chinese "直径大概30厘米"
        if dia is None:
            m = re.search(rf"{_NUMBER}\s*{_LENGTH_UNIT}\s*(?:直径|diameter)", text, re.I)
            dia = _length_mm(m.group(1), m.group(2)) if m else None
        blades = re.search(r"(?:叶片|扇叶|blades?)\s*(?:数量|数|count|:|：|=)?\s*([3-9])(?:\s*片)?", text, re.I)
        if blades is None:
            blades = re.search(r"([3-9])\s*(?:片|blades?)", text, re.I)
        hub = _extract_length(text, r"轮毂直径|hub diameter")
        pitch = re.search(r"(?:叶片角度|桨距角|blade pitch|pitch)\s*(?:about|约|为|是|:|：|=)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:deg|°|度)?", text, re.I)
        try:
            geometry = FanGeometry(
                diameter_mm=dia, rpm=_extract_rpm(text),
                blade_count=int(blades.group(1)) if blades else None,
                hub_diameter_mm=hub,
                blade_pitch_deg=float(pitch.group(1)) if pitch else None,
            )
        except ValidationError as exc:
            return Interpretation(issues=(
                "Fan dimensions exceed the geometry limits: "
                + "; ".join(e["msg"] for e in exc.errors())[:450],
            ))
    elif bracket:
        family = ProductFamily.L_BRACKET
        web = _extract_length(text, r"腹板厚度|厚度|web thickness|thickness")
        if web is None:
            m=re.search(rf"{_NUMBER}\s*{_LENGTH_UNIT}\s*(?:厚|thick)",text,re.I)
            web=_length_mm(m.group(1),m.group(2)) if m else None
        if web is not None and web not in (8,10,12,14):
            return Interpretation(issues=(
                f"Requested bracket thickness {web:g} mm is outside the current editable 8/10/12/14 mm generator. No geometry was substituted.",
            ))
        geometry=BracketGeometry(web_thickness_mm=int(web) if web is not None else None)
    else:
        return Interpretation(issues=(
            "Unregistered mechanical product. Add a validated product schema and CAD generator; arbitrary text-to-any-CAD is not yet implemented.",
        ))
    wants_fea=bool(re.search(r"(受力|应力|强度|结构|墙壁|墙体|固定|fea|stress|deflection|deformation|structural|wall load)",text,re.I))
    wants_cfd=bool(re.search(r"(流体|流场|风速|气流|风量|吹得|cfd|airflow|velocity field|fluid|flow|pressure|wake)",text,re.I))
    wants_thermal=bool(re.search(r"(温度|散热|热流|thermal|cooling|temperature|heat)",text,re.I))
    force=_extract_force_n(text)
    try:
        req=EngineeringRequest(
            prompt=text,
            family=family, geometry=geometry,
            analyses=AnalysisIntent(
                structural_fea=wants_fea,fluid_cfd=wants_cfd,thermal=wants_thermal
            ),
            loads=MechanicalLoads(force_n=force),
        )
    except ValidationError as exc:
        return Interpretation(issues=(
            "Extracted inputs exceed bounded product/physics schema: "
            + "; ".join(e["msg"] for e in exc.errors())[:450],
        ))
    issues=[]
    if isinstance(geometry,FanGeometry):
        if geometry.diameter_mm is None:
            issues.append("Fan diameter is missing; a CAD size cannot be invented.")
        if geometry.blade_count is None or geometry.hub_diameter_mm is None or geometry.blade_pitch_deg is None:
            issues.append("Concept fan blade count, hub diameter and/or pitch are unspecified; explicitly approve demonstration geometry assumptions before CAD export.")
    else:
        if geometry.web_thickness_mm is None:
            issues.append("Bracket web thickness is missing; choose one of 8, 10, 12, 14 mm.")
    return Interpretation(request=req,issues=tuple(issues))


def approve_demo_assumptions(request: EngineeringRequest) -> EngineeringRequest:
    """Only an explicit user's opt-in may insert visibly labeled demo defaults."""
    req=request.model_copy(deep=True)
    notes=list(req.assumptions)
    if isinstance(req.geometry,FanGeometry):
        if req.geometry.diameter_mm is None:
            raise ValueError("A fan diameter is required even for a concept model")
        if req.geometry.blade_count is None:
            req.geometry.blade_count=5
            notes.append("CONCEPT ONLY: assumed 5 flat blades")
        if req.geometry.hub_diameter_mm is None:
            req.geometry.hub_diameter_mm=round(.25*req.geometry.diameter_mm,2)
            notes.append("CONCEPT ONLY: assumed hub diameter = 25% of fan diameter")
        if req.geometry.blade_pitch_deg is None:
            req.geometry.blade_pitch_deg=20.
            notes.append("CONCEPT ONLY: assumed flat blade pitch = 20 degrees; no aerodynamic validation")
        notes.append("CONCEPT ONLY: simplified guard ring and wall plate derived from rotor diameter; no screws, joints or aerodynamics")
    elif isinstance(req.geometry,BracketGeometry):
        if req.geometry.web_thickness_mm is None:
            raise ValueError("Select an allowed L-bracket web thickness")
        if req.loads.force_n is None:
            req.loads.force_n=250
            notes.append("DEMO FEA: assumed 250 N transverse load")
        if req.loads.force_axis is None:
            req.loads.force_axis="X"
            notes.append("DEMO FEA: assumed +X load")
        if req.loads.support_axis is None:
            req.loads.support_axis="Z"
            notes.append("DEMO FEA: assumed fixed minimum-Z face, loaded maximum-Z face")
        defaults={"E_gpa":200.,"poisson":.29,"density_kg_m3":8190.,"yield_mpa":900.}
        for key,value in defaults.items():
            if getattr(req.material,key) is None:
                setattr(req.material,key,value)
                notes.append(f"DEMO FEA: assumed material {key} = {value:g} (not measured)")
    req.assumptions=tuple(dict.fromkeys(notes))
    req.concept_assumptions_confirmed=True
    return EngineeringRequest.model_validate(req.model_dump())


def preflight_missing(request: EngineeringRequest) -> tuple[str, ...]:
    """Required CAD parameters only (solver-specific requirements are in DAG)."""
    g=request.geometry
    if isinstance(g,BracketGeometry):
        return ("web_thickness_mm",) if g.web_thickness_mm is None else ()
    fields=("diameter_mm","blade_count","hub_diameter_mm","blade_pitch_deg")
    return tuple(k for k in fields if getattr(g,k) is None)
