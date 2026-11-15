"""Capability-driven CAD / CFD / FEA orchestration for the NL engineering studio.

DAG stages are created from the versioned EngineeringRequest. Only a
registered CAD generator may create geometry. The ONLY currently executable
physics job is the pre-existing isolated L-bracket tetra10 FEA. CFD, thermal
analysis and multi-body wall-fan loads are BLOCKED with actionable reasons,
never silently converted into invented plots or numerical estimates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .engineering_schema import (
    EngineeringRequest, BracketGeometry, FanGeometry, preflight_missing,
)
from .product_cad import CADProduct, generate_product


class TaskState(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    NOT_REQUESTED = "NOT_REQUESTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RegisteredFamily:
    family: str
    generator: str
    geometry_level: str
    structural_solver: str | None
    fluid_solver: str | None


FAMILY_REGISTRY: dict[str, RegisteredFamily] = {
    "l_bracket": RegisteredFamily(
        "l_bracket", "Gmsh OpenCASCADE single-body parametric STEP",
        "editable solid BRep", "forceforge isolated quadratic tetra10", None,
    ),
    "wall_fan": RegisteredFamily(
        "wall_fan", "Gmsh OpenCASCADE conceptual multi-body STEP",
        "concept assembly only", None, None,
    ),
    "hollow_shaft": RegisteredFamily(
        "hollow_shaft", "Gmsh OCC parametric annular solid STEP",
        "real single solid; no supported mechanics solver", None, None,
    ),
    "mounting_plate": RegisteredFamily(
        "mounting_plate", "Gmsh OCC plate or four-hole through-cut STEP",
        "real single solid; no supported mechanics solver", None, None,
    ),
}


@dataclass(frozen=True)
class EngineeringTask:
    name: str
    status: TaskState
    depends_on: tuple[str, ...] = ()
    reason: str = ""
    missing_inputs: tuple[str, ...] = ()

    def as_dict(self):
        payload=asdict(self)
        payload["status"]=self.status.value
        return payload


@dataclass(frozen=True)
class EngineeringPlan:
    schema_version: str
    family: str
    tasks: tuple[EngineeringTask, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]

    def task(self,name:str) -> EngineeringTask:
        return next(t for t in self.tasks if t.name==name)

    def as_dict(self):
        return {
            "schema_version":self.schema_version,
            "family":self.family,
            "tasks":[task.as_dict() for task in self.tasks],
            "assumptions":list(self.assumptions),
            "warnings":list(self.warnings),
        }


@dataclass
class EngineeringExecution:
    plan: EngineeringPlan
    cad: CADProduct
    structural_fea: Any | None
    stage_results: tuple[EngineeringTask, ...]
    fluid_domain: Any | None = None

    def evidence(self) -> dict:
        result={
            "input_schema_version":self.plan.schema_version,
            "family":self.plan.family,
            "stages":[task.as_dict() for task in self.stage_results],
            "cad":self.cad.metadata(),
            "assumptions":list(self.plan.assumptions),
            "warnings":list(self.plan.warnings),
            "structural_fea":None,
            "fluid_domain":self.fluid_domain.as_dict() if self.fluid_domain is not None else None,
            "fluid_cfd":None,
            "thermal":None,
        }
        if self.structural_fea is not None:
            fea=self.structural_fea
            result["structural_fea"]={
                "solver":"existing Gmsh STEP -> quadratic tetra10 FEM",
                "provenance_sha256":fea.mesh.source_sha256,
                "input_tetrahedra":int(fea.mesh.num_tets),
                "tip_displacement_mm":float(fea.tip_mm),
                "sampled_von_mises_mpa":float(fea.peak_von_mises_mpa),
                "mass_kg":float(fea.mass_kg),
                "reaction_equilibrium_residual":float(fea.relative_reaction_residual),
                "mesh_volume_relative_error":float(fea.mesh.relative_volume_difference),
                "numerical_scope":"preliminary linear elastic; not convergence, contact or safety certified",
            }
        return result


def _ready_or_blocked(ready: bool, message: str, missing=()) -> tuple[TaskState,str,tuple[str,...]]:
    return (
        (TaskState.READY,"",()) if ready else
        (TaskState.BLOCKED,message,tuple(missing))
    )


def plan_engineering(request: EngineeringRequest) -> EngineeringPlan:
    if not isinstance(request,EngineeringRequest):
        raise TypeError("Validated engineering schema required")
    fam=request.family.value
    if fam not in FAMILY_REGISTRY:
        raise ValueError("Unregistered mechanical product family")
    missing_cad=preflight_missing(request)
    cad_status,cad_reason,cad_missing=_ready_or_blocked(
        not missing_cad,
        "CAD requires explicit parameters or confirmed, labeled concept defaults",
        missing_cad,
    )
    tasks=[
        EngineeringTask("interpret_requirements",TaskState.COMPLETED,
                        reason="Rules-extracted, versioned engineering request"),
        EngineeringTask("generate_cad",cad_status,
                        depends_on=("interpret_requirements",),
                        reason=cad_reason,missing_inputs=cad_missing),
    ]
    warnings=[]
    if fam=="wall_fan":
        tasks.append(EngineeringTask(
            "solid_mesh",TaskState.BLOCKED,
            depends_on=("generate_cad",),
            reason="A concept assembly is not a tied/contact-validated single solid for structural FEM.",
        ))
    elif fam=="l_bracket":
        tasks.append(EngineeringTask(
            "solid_mesh",cad_status,
            depends_on=("generate_cad",),reason=cad_reason,
            missing_inputs=cad_missing,
        ))
    else:
        tasks.append(EngineeringTask(
            "solid_mesh",TaskState.BLOCKED,
            depends_on=("generate_cad",),
            reason="A STEP alone is not a validated 3D tetra meshing/FEA workflow for this product",
            missing_inputs=("validated_mesh_adapter",),
        ))
    if request.analyses.structural_fea:
        if fam=="wall_fan":
            tasks.append(EngineeringTask(
                "structural_fea",TaskState.BLOCKED,
                depends_on=("generate_cad","solid_mesh"),
                reason=(
                    "Wall-fan mounting FEA needs measured mass/center of gravity, "
                    "bolt/anchor layout, wall stiffness, actual contacts and a "
                    "validated connected structural mesh. The current tetra10 "
                    "single-body bracket solver cannot model this assembly."
                ),
                missing_inputs=(
                    "mass_and_center_of_gravity","mounting_anchor_geometry",
                    "wall_and_contact_materials","structural_load_path",
                ),
            ))
        elif fam!="l_bracket":
            tasks.append(EngineeringTask(
                "structural_fea",TaskState.BLOCKED,
                depends_on=("generate_cad","solid_mesh"),
                reason=(
                    "This real STEP has no validated material, loading, "
                    "fixture and tetra10 finite-element adapter. "
                    "No stress or safety values are computed."
                ),
                missing_inputs=(
                    "validated_fea_adapter","fixture_load_path",
                    "material_and_loads",
                ),
            ))
        else:
            props = {
                "force_n":request.loads.force_n,
                "force_axis":request.loads.force_axis,
                "support_axis":request.loads.support_axis,
                "E_gpa":request.material.E_gpa,
                "poisson":request.material.poisson,
                "density_kg_m3":request.material.density_kg_m3,
                "yield_mpa":request.material.yield_mpa,
            }
            missing=tuple(key for key,val in props.items() if val is None)
            if not missing and request.loads.force_axis==request.loads.support_axis:
                missing=("distinct_force_and_support_axes",)
            ready=not missing and cad_status==TaskState.READY
            tasks.append(EngineeringTask(
                "structural_fea",TaskState.READY if ready else TaskState.BLOCKED,
                depends_on=("generate_cad","solid_mesh"),
                reason="" if ready else (
                    "Real structural FEA requires explicit load/material/fixture "
                    "inputs or user-approved demo assumptions, and valid CAD."
                ),
                missing_inputs=missing+cad_missing,
            ))
    else:
        tasks.append(EngineeringTask("structural_fea",TaskState.NOT_REQUESTED))
    if request.analyses.fluid_cfd:
        if fam=="wall_fan" and cad_status==TaskState.READY and request.concept_assumptions_confirmed:
            tasks.append(EngineeringTask(
                "fluid_domain",TaskState.READY,depends_on=("generate_cad",),
                reason=(
                    "Real Gmsh idealized 3D farfield + cylindrical rotor actuator "
                    "zone preprocessor is available. It does NOT resolve blades, "
                    "the wall or any actual fluid solution."
                ),
            ))
            tasks.append(EngineeringTask(
                "fluid_mesh",TaskState.READY,
                depends_on=("fluid_domain",),
                reason="Isolated Gmsh conforming 3D tetra mesh + physical patch groups; explicit second button",
            ))
        else:
            reason=(
                "Only a user-approved bounded wall-fan diameter can produce "
                "the current conceptual actuator air-domain mesh. No generic "
                "blade-resolved or arbitrary STEP-to-CFD geometry yet."
            )
            missing=(
                ("confirmed_concept_geometry",)
                if fam=="wall_fan" else ("supported_fluid_domain_generator",)
            )
            tasks.append(EngineeringTask(
                "fluid_domain",TaskState.BLOCKED,depends_on=("generate_cad",),
                reason=reason,missing_inputs=missing,
            ))
            tasks.append(EngineeringTask(
                "fluid_mesh",TaskState.BLOCKED,
                depends_on=("fluid_domain",),
                reason="Real air volume must be explicitly generated before meshing",
                missing_inputs=missing,
            ))
        tasks.append(EngineeringTask(
            "fluid_cfd",TaskState.BLOCKED,
            depends_on=("fluid_mesh",),
            reason=(
                "No validated incompressible Navier-Stokes/OpenFOAM runtime, "
                "pressure-flow fan curve, momentum source, wall influence, "
                "boundary conditions or solver residuals are supplied. "
                "A real 3D air mesh does NOT imply velocities or pressures."
            ),
            missing_inputs=(
                "validated_cfd_solver","fan_curve_or_rotor_source",
                "boundary_conditions","mesh_convergence",
            ),
        ))
    else:
        tasks.append(EngineeringTask("fluid_domain",TaskState.NOT_REQUESTED))
        tasks.append(EngineeringTask("fluid_mesh",TaskState.NOT_REQUESTED))
        tasks.append(EngineeringTask("fluid_cfd",TaskState.NOT_REQUESTED))
    if request.analyses.thermal:
        tasks.append(EngineeringTask(
            "thermal",TaskState.BLOCKED,
            depends_on=("generate_cad",),
            reason="No validated thermal model, heat source or heat-transfer boundary adapter is connected.",
            missing_inputs=("heat_sources","thermal_boundary_conditions","thermal_solver"),
        ))
    else:
        tasks.append(EngineeringTask("thermal",TaskState.NOT_REQUESTED))
    if fam=="wall_fan":
        warnings.append(
            "The generated wall-fan STEP is a simplified conceptual multi-body assembly. "
            "No aerodynamic performance, motor torque, fastener loads, fluid forces or "
            "wall safety is inferred from its diameter and RPM."
        )
    elif fam=="l_bracket":
        warnings.append(
            "Bracket FEA assumes a single linear-elastic body with idealized fixed "
            "support and applied traction. Real joint/bolt/fatigue validation is absent."
        )
    else:
        warnings.append(
            "Parametric STEP geometry is generated from explicit dimensions. "
            "This product has no validated FEA, CFD, contact, fatigue or "
            "certified safety result; requested physics remain BLOCKED."
        )
    if request.assumptions:
        warnings.append(
            "User-approved demo assumptions are not measured data: "
            + "; ".join(request.assumptions)
        )
    return EngineeringPlan(
        schema_version=request.schema_version,family=fam,
        tasks=tuple(tasks),assumptions=request.assumptions,
        warnings=tuple(warnings),
    )


def run_engineering(request: EngineeringRequest) -> EngineeringExecution:
    """Explicit user action only. Generate genuine STEP, then ready FEA jobs."""
    plan=plan_engineering(request)
    if plan.task("generate_cad").status != TaskState.READY:
        raise ValueError(
            "CAD task is blocked: "
            + ", ".join(plan.task("generate_cad").missing_inputs)
        )
    cad=generate_product(request)
    stage_results=[]
    for task in plan.tasks:
        if task.name=="generate_cad":
            stage_results.append(EngineeringTask(
                "generate_cad",TaskState.COMPLETED,
                depends_on=task.depends_on,reason="Real STEP generated with SHA-256",
            ))
        elif task.name=="solid_mesh" and request.family.value=="l_bracket" and not request.analyses.structural_fea:
            stage_results.append(EngineeringTask(
                "solid_mesh",TaskState.NOT_REQUESTED,
                reason="No FEA requested; a STEP export does not require a volume mesh",
            ))
        else:
            stage_results.append(task)
    fea=None
    step=plan.task("structural_fea")
    if step.status==TaskState.READY:
        from .cad_solid import CadLoad
        from .isolated_cad import analyze_step_safely
        assert isinstance(request.geometry,BracketGeometry)
        ax={"X":0,"Y":1,"Z":2}
        case=CadLoad(
            force_n=float(request.loads.force_n),
            force_axis=ax[request.loads.force_axis],
            boundary_axis=ax[request.loads.support_axis],
            E_pa=float(request.material.E_gpa)*1e9,
            nu=float(request.material.poisson),
            density=float(request.material.density_kg_m3),
            yield_pa=float(request.material.yield_mpa)*1e6,
        )
        fea=analyze_step_safely(
            cad.step_bytes,
            source_label=f"Natural-language {request.family.value} STEP",
            mesh_size_mm=float(request.mesh_size_mm),
            unit="mm",load=case,
        )
        if fea.mesh.source_sha256!=cad.sha256:
            raise ValueError("FEA source STEP SHA mismatch; reject numerical result")
        if (fea.relative_reaction_residual>1e-5 or
                fea.mesh.relative_volume_difference>.20 or
                fea.mesh.min_shape_quality<=0):
            raise ValueError("Real FEA evidence failed force/volume/mesh quality")
        stage_results=[
            EngineeringTask(
                t.name,TaskState.COMPLETED if t.name in ("solid_mesh","structural_fea") else t.status,
                depends_on=t.depends_on,
                reason=("Real tetra10 numerical output with checked source SHA / equilibrium"
                        if t.name=="structural_fea" else t.reason),
                missing_inputs=t.missing_inputs,
            ) for t in stage_results
        ]
    return EngineeringExecution(plan,cad,fea,tuple(stage_results))


def mesh_registered_fluid_domain(
    request: EngineeringRequest,
    execution: EngineeringExecution,
) -> EngineeringExecution:
    """Explicit *second* user action, preserving the existing CAD/FEA result.

    Every mesh is provenance-linked to the exact generated STEP. Never
    schedule CFD without a solver. If a native mesh fails, the original
    CAD/FEA session stays intact and reports the real exception.
    """
    from hashlib import sha256
    from .fluid_domain import generate_fan_air_domain_safely
    if request.family.value!=execution.plan.family:
        raise ValueError("Fluid mesh request does not match the current CAD study")
    expected=sha256(execution.cad.step_bytes).hexdigest()
    if expected!=execution.cad.sha256:
        raise ValueError("CAD source hash changed before air meshing")
    plan=plan_engineering(request)
    if plan.task("fluid_mesh").status!=TaskState.READY:
        raise ValueError(
            "3D air-domain meshing is BLOCKED until geometry assumptions "
            "and the fluid-domain stage are explicitly accepted"
        )
    result=generate_fan_air_domain_safely(request,execution.cad.step_bytes)
    if result.cad_source_sha256!=execution.cad.sha256:
        raise ValueError("3D fluid mesh does not match the generated CAD SHA")
    execution.fluid_domain=result
    execution.stage_results=tuple(
        EngineeringTask(
            name=t.name,
            status=(TaskState.COMPLETED if t.name in ("fluid_domain","fluid_mesh") else t.status),
            depends_on=t.depends_on,
            reason=(
                "Genuine 3D Gmsh tetra mesh and named physical patches; "
                "NO CFD physics were solved"
                if t.name in ("fluid_domain","fluid_mesh") else t.reason
            ),
            missing_inputs=(
                () if t.name in ("fluid_domain","fluid_mesh") else t.missing_inputs
            ),
        ) for t in execution.stage_results
    )
    return execution
