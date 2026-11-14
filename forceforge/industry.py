"""ForceForge X cross-industry simulation routing and evidence tracking.

All built-in inputs are *illustrative*. This module reuses existing numerical
truss and Euler-Bernoulli frame backends, and does not perform formal code
checks or issue engineering approvals. Different sectors are not equivalent
in geometry, loads, materials or acceptance criteria.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Literal

import numpy as np

from .advanced_frame import (
    FrameMaterial, FrameMember, FrameModel, cantilever_demo, circular_section,
    solve_frame,
)
from .design import make_truss
from .fatigue import SNModel, StressBlock, miner_damage
from .physics import Material, solve

Sector = Literal["Building", "Industrial", "Automotive"]
SECTORS: tuple[Sector, ...] = ("Building", "Industrial", "Automotive")


@dataclass(frozen=True)
class CaseInputs:
    sector: Sector
    load_scale: float = 1.0
    temperature_change_k: float = 50.0
    joint_stiffness_nm_rad: float = 200_000.0
    service_cycles: int = 200_000
    section_scale: float = 1.0  # dimensionless uniform section radius ratio

    def __post_init__(self) -> None:
        if self.sector not in SECTORS:
            raise ValueError("Unknown sector")
        if not (0.1 <= self.load_scale <= 3.0):
            raise ValueError("Load multiplier must be in [0.1,3.0]")
        if not (-100 <= self.temperature_change_k <= 250):
            raise ValueError("Temperature difference must be in [-100,250] K")
        if self.joint_stiffness_nm_rad <= 0:
            raise ValueError("Rotational joint stiffness must be positive")
        if not (1 <= self.service_cycles <= 100_000_000):
            raise ValueError("Service cycles must be 1..100 million")
        if not (0.55 <= self.section_scale <= 3.0):
            raise ValueError("Section radius ratio must be in [0.55, 3.0]")


@dataclass
class CaseReport:
    sector: str
    title: str
    description: str
    solver: str
    fidelity: str
    design_inputs: dict
    scenarios: list[dict]
    governing: dict
    figures: dict
    verification: list[dict]
    gaps: list[str]
    trace_id: str = ""
    certification_status: str = "NOT CERTIFIED — no standards approval or professional sign-off"

    def serializable(self) -> dict:
        return asdict(self)


def _trace(report: CaseReport) -> CaseReport:
    # Identifies the exact dataset and model assumptions; not a legal signature.
    payload = report.serializable()
    payload.pop("trace_id", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    report.trace_id = "FFX-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()
    return report


def _evidence(sector: Sector) -> tuple[list[dict], list[str]]:
    common = [
        ("Numerical solver", "CALCULATED", "Solver outputs computed for stated idealizations"),
        ("Analytical benchmarks", "BENCHMARK-AVAILABLE", "Beam / truss test cases are supplied; this specific design has no independent validation"),
        ("Material pedigree", "MISSING", "No certificates or independently tested properties"),
        ("Experimental correlation", "MISSING", "No physical specimen test or measured load response"),
        ("Applicable design code", "NOT REVIEWED", "Authority, adopted edition and clause mapping absent"),
        ("Independent engineering approval", "MISSING", "No authorized independent reviewer or signature"),
    ]
    extra = {
        "Building": [
            ("Site-specific load combinations", "MISSING", "Wind, snow, occupancy, seismic and geographic basis not supplied"),
            ("Steel connections and stability", "MISSING", "No gusset/bolt/weld, lateral bracing or effective length verification"),
        ],
        "Industrial": [
            ("Anchors and bolt preload", "MISSING", "Spring surrogate does not resolve anchors or real connection response"),
            ("Duty cycle / shock qualification", "MISSING", "No measured forces, impact spectrum or equipment acceptance limits"),
        ],
        "Automotive": [
            ("Full 3D load paths and bushings", "MISSING", "Current planar surrogate omits ball joints, bushings, contact and geometric kinematics"),
            ("OEM road-load / fatigue qualification", "MISSING", "No road loads, validated S–N details or proving-ground test"),
        ],
    }[sector]
    all_evidence = common + extra
    return ([{"gate": a, "status": b, "evidence": c} for a, b, c in all_evidence],
            [a for a, b, c in all_evidence if b in {"MISSING", "NOT REVIEWED"}])


def _truss_buckling_ratio(force_n: np.ndarray, pcr_n: np.ndarray,
                          safety_factor: float = 2.0) -> float:
    comp = np.asarray(force_n) < -1e-10
    if not np.any(comp):
        return 0.0
    return float(np.max(safety_factor * np.abs(force_n[comp]) / pcr_n[comp]))


def _building(inputs: CaseInputs) -> CaseReport:
    # Generic roof-truss point-load *example*, not full roof wind/snow analysis.
    E, rho, sy = 200e9, 7850., 250e6
    truss = make_truss("Warren-2", span_m=6.0, height_m=2.0,
                       area_mm2=1000.*inputs.section_scale**2, load_n=5_000*inputs.load_scale,
                       material=Material(E, rho, sy))
    load_node = int(np.argmin(truss.forces_n[:, 1]))
    case_patterns = [
        ("Vertical point load", 1.0, 0.0),
        ("Vertical + lateral point load", 1.0, 0.35),
        ("Illustrative uplift", -0.35, 0.20),
    ]
    rows = []
    governing = None
    fig = None
    for title, f_y, f_x in case_patterns:
        truss.forces_n[:, :] = 0.
        truss.forces_n[load_node] = [f_x * 5_000 * inputs.load_scale,
                                    -f_y * 5_000 * inputs.load_scale]
        result = solve(truss)
        max_u_mm = result.max_disp_m * 1000
        checks = {
            "Axial yield": float(result.max_stress_pa * 2 / sy),
            "Nodal displacement": float(max_u_mm / 12.0),
            "Ideal bar buckling": _truss_buckling_ratio(result.force_n, result.buckling_critical_n),
        }
        max_util = float(max(checks.values()))
        rows.append({"scenario": title, "max_displacement_mm": round(max_u_mm, 4),
                     "peak_stress_mpa": round(result.max_stress_pa / 1e6, 4),
                     "max_utilization": round(max_util, 4),
                     "controlling_check": max(checks, key=checks.get),
                     "numerical_screen": "WITHIN ILLUSTRATIVE LIMITS" if max_util <= 1 else "EXCEEDS ILLUSTRATIVE LIMITS",
                     "checks": {k: round(v, 5) for k, v in checks.items()}})
        if governing is None or max_util > governing["max_utilization"]:
            governing = rows[-1].copy()
        if title == "Vertical point load":
            fig = {
                "nodes": truss.nodes_m.tolist(),
                "members": [list(e) for e in truss.elements],
                "displaced": (truss.nodes_m + result.disp_m).tolist(),
                "member_values_mpa": (np.abs(result.stress_pa) / 1e6).tolist(),
                "mass_kg": result.mass_kg,
            }
    assert governing is not None and fig is not None
    evidence, gaps = _evidence("Building")
    report = CaseReport(
        sector="Building", title="Michigan steel roof-truss load-path screen",
        description="2D pin-jointed truss subjected to hypothetical point-load cases.",
        solver="2D linear truss FEA / ideal Euler compression screen",
        fidelity="Reduced-order global axial load paths; no real roof wind/snow distribution",
        design_inputs={"span_m": 6.0, "height_m": 2.0, "area_mm2": 1000.0*inputs.section_scale**2,
                       "section_radius_ratio": inputs.section_scale,
                       "point_load_n": 5_000.0*inputs.load_scale, "E_gpa": 200.0,
                       "yield_mpa": 250.0, "illustrative_displacement_limit_mm": 12.0},
        scenarios=rows, governing=governing, figures=fig,
        verification=evidence, gaps=gaps,
    )
    return _trace(report)


def _frame_run(model: FrameModel) -> tuple:
    a = solve_frame(model)
    b = solve_frame(model, second_order=True)
    if not b.converged:
        raise ValueError("Second-order iteration did not converge")
    return a, b


def _industrial(inputs: CaseInputs) -> CaseReport:
    scenarios = [
        ("Continuous service", 1.0, inputs.temperature_change_k),
        ("Startup / transient load", 1.35, inputs.temperature_change_k),
        ("High-temperature case", 1.0, inputs.temperature_change_k+30.),
    ]
    rows, governing, fig = [], None, None
    for name, load_factor, delta_t in scenarios:
        model = cantilever_demo(
            length_m=1.2, radius_m=.030*inputs.section_scale,
            tip_force_n=1_200. * inputs.load_scale * load_factor,
            axial_force_n=-7_000. * inputs.load_scale * load_factor,
            temp_rise_k=delta_t,
            rotational_spring_nm_rad=inputs.joint_stiffness_nm_rad,
        )
        linear, second = _frame_run(model)
        max_stress_mpa = float(np.max(second.member_max_stress_pa) / 1e6)
        d_mm = float(np.linalg.norm(second.u[:, :2], axis=1).max() * 1000)
        pdelta = abs(second.u[1, 1]/linear.u[1, 1]) if linear.u[1, 1] else 1.0
        checks = {
            "Nominal axial+bending stress": max_stress_mpa / (250/2),
            "Illustrative nodal displacement": d_mm / 20.0,
        }
        max_util = max(checks.values())
        rows.append({"scenario": name, "max_displacement_mm": round(d_mm, 4),
                     "peak_stress_mpa": round(max_stress_mpa, 4),
                     "p_delta_amplification": round(float(pdelta), 5),
                     "max_utilization": round(float(max_util), 4),
                     "controlling_check": max(checks, key=checks.get),
                     "numerical_screen": "WITHIN ILLUSTRATIVE LIMITS" if max_util <= 1 else "EXCEEDS ILLUSTRATIVE LIMITS",
                     "checks": {k: round(v, 5) for k, v in checks.items()}})
        if governing is None or max_util > governing["max_utilization"]:
            governing = rows[-1].copy()
        if name == "Continuous service":
            fig = {
                "nodes": model.nodes_m.tolist(),
                "members": [[m.node_i, m.node_j] for m in model.members],
                "displaced": (model.nodes_m + second.u[:, :2]).tolist(),
                "member_values_mpa": (second.member_max_stress_pa / 1e6).tolist(),
                "mass_kg": float(second.mass_kg),
            }
    assert governing is not None and fig is not None
    # Illustrative 0-to-peak cycle, NOT calibrated component/joint fatigue.
    peak = float(governing["peak_stress_mpa"]) * 1e6
    damage = miner_damage(SNModel(120e6, 1e6, 3.0, 450e6),
                          [StressBlock(peak/2, peak/2, inputs.service_cycles)])
    governing["hypothetical_miner_damage"] = float(damage["miner_damage"])
    evidence, gaps = _evidence("Industrial")
    return _trace(CaseReport(
        sector="Industrial", title="Industrial machine mounting bracket",
        description="2D semi-rigid cantilever under mechanical, compressive and thermal loads.",
        solver="2D Euler–Bernoulli frame FEA + P–Δ + thermal + illustrative fatigue",
        fidelity="Global beam and equivalent rotational joint spring; no bolt/contact model",
        design_inputs={"length_m": 1.2, "solid_round_radius_mm": 30.0*inputs.section_scale,
                       "section_radius_ratio": inputs.section_scale,
                       "joint_stiffness_nm_rad": inputs.joint_stiffness_nm_rad,
                       "thermal_delta_k": inputs.temperature_change_k,
                       "reference_lateral_n": 1_200*inputs.load_scale,
                       "reference_compression_n": 7_000*inputs.load_scale,
                       "hypothetical_sn_reference_mpa": 120,
                       "hypothetical_sn_reference_cycles": 1_000_000,
                       "service_cycles": inputs.service_cycles},
        scenarios=rows, governing=governing, figures=fig,
        verification=evidence, gaps=gaps,
    ))


def _automotive_proxy(inputs: CaseInputs) -> CaseReport:
    """Explicitly *planar frame surrogate* for a tubular suspension arm.

    No wheel multibody dynamics, ball joint, bushings, contact or multiaxial
    fatigue. This is a mathematical screening case, not a real automotive FEA.
    """
    E, rho, yield_pa = 70e9, 2700.0, 260e6
    mat = FrameMaterial(E_pa=E, rho_kg_m3=rho, alpha_per_k=23e-6,
                        yield_pa=yield_pa, ultimate_pa=330e6)
    area, inertia = circular_section(.018*inputs.section_scale)
    nodes = np.array([[0.0, -0.20], [0., 0.20], [0.70, 0.]], float)
    members = [FrameMember(0, 2, area, inertia, inputs.temperature_change_k),
               FrameMember(1, 2, area, inertia, inputs.temperature_change_k),
               FrameMember(0, 1, area, inertia, inputs.temperature_change_k)]
    patterns = [
        ("Vertical road-load projection", -3_000., 0.),
        ("Cornering + vertical projection", -3_500., 2_500.),
        ("Braking + vertical projection", -2_200., -3_200.),
    ]
    rows, governing, fig = [], None, None
    for name, fy, fx in patterns:
        forces = np.zeros((3,3))
        forces[2] = [fx*inputs.load_scale, fy*inputs.load_scale, 0.]
        model = FrameModel(
            nodes_m=nodes, members=members, nodal_forces=forces,
            supports=[(0, True, True, False), (1, True, True, False)],
            rotational_springs_nm_rad={0: inputs.joint_stiffness_nm_rad,
                                       1: inputs.joint_stiffness_nm_rad},
            material=mat,
        )
        linear, second = _frame_run(model)
        peak_mpa = float(second.member_max_stress_pa.max()/1e6)
        d_mm = float(np.linalg.norm(second.u[:, :2],axis=1).max()*1000)
        checks = {
            "Nominal axial+bending stress": peak_mpa / (yield_pa/2/1e6),
            "Illustrative component displacement": d_mm / 8.0,
        }
        max_util = max(checks.values())
        rows.append({"scenario":name,"max_displacement_mm":round(d_mm,4),
                     "peak_stress_mpa":round(peak_mpa,4),
                     "max_utilization":round(max_util,4),
                     "controlling_check":max(checks,key=checks.get),
                     "numerical_screen":"WITHIN ILLUSTRATIVE LIMITS" if max_util<=1 else "EXCEEDS ILLUSTRATIVE LIMITS",
                     "checks":{k:round(v,5) for k,v in checks.items()}})
        if governing is None or max_util>governing["max_utilization"]:
            governing=rows[-1].copy()
        if name == "Vertical road-load projection":
            fig={"nodes":nodes.tolist(),"members":[[m.node_i,m.node_j] for m in members],
                 "displaced":(nodes+second.u[:,:2]).tolist(),
                 "member_values_mpa":(second.member_max_stress_pa/1e6).tolist(),
                 "mass_kg":float(second.mass_kg)}
    assert governing is not None and fig is not None
    peak = governing["peak_stress_mpa"]*1e6
    damage = miner_damage(SNModel(100e6,1e6,3.0,330e6),
                          [StressBlock(peak/2,peak/2,inputs.service_cycles)])
    governing["hypothetical_miner_damage"] = float(damage["miner_damage"])
    evidence,gaps=_evidence("Automotive")
    return _trace(CaseReport(
        sector="Automotive",title="Suspension link: planar A-arm load-path surrogate",
        description="Two-dimensional representation of a triangular tubular link and projected load cases.",
        solver="2D frame FEA / elastic bending / projected road loads / illustrative S–N",
        fidelity="Planar structural surrogate only; not a validated 3D suspension component model",
        design_inputs={"projection_span_m": 0.70,"mount_spacing_m":0.40,
                       "equivalent_rod_radius_mm":18.0*inputs.section_scale,
                       "section_radius_ratio": inputs.section_scale,"E_gpa":70.0,"yield_mpa":260,
                       "joint_stiffness_nm_rad":inputs.joint_stiffness_nm_rad,
                       "thermal_delta_k":inputs.temperature_change_k,
                       "service_cycles":inputs.service_cycles,
                       "hypothetical_sn_reference_mpa":100},
        scenarios=rows,governing=governing,figures=fig,
        verification=evidence,gaps=gaps,
    ))


def run_industry_case(inputs: CaseInputs) -> CaseReport:
    if inputs.sector == "Building":
        return _building(inputs)
    if inputs.sector == "Industrial":
        return _industrial(inputs)
    return _automotive_proxy(inputs)


def platform_summary(inputs: CaseInputs) -> list[dict]:
    rows=[]
    for sector in SECTORS:
        report=run_industry_case(CaseInputs(
            sector=sector, load_scale=inputs.load_scale,
            temperature_change_k=inputs.temperature_change_k,
            joint_stiffness_nm_rad=inputs.joint_stiffness_nm_rad,
            service_cycles=inputs.service_cycles,
            section_scale=inputs.section_scale,
        ))
        rows.append({"sector":report.sector,"solver":report.solver,
                     "case":report.title,"model_mass_kg":round(report.figures["mass_kg"],3),
                     "governing_numerical_utilization":round(report.governing["max_utilization"],3),
                     "scenario_count":len(report.scenarios),
                     "missing_evidence":len(report.gaps),
                     "formal_approval":"NOT CERTIFIED"})
    return rows
