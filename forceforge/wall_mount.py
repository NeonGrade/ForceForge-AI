"""Rigid-wall four-anchor free-body load transfer, SI units throughout.

This is an analytically balanced *load distribution* for a rigid rectangular
mounting plate with four bilateral anchors. It is NOT finite-element wall
deformation, fastener slip, fatigue, wall pullout capacity or CFD-derived thrust.
The user must provide an independently measured/integrated aerodynamic load.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite, hypot
from hashlib import sha256
import csv
import io
import numpy as np


@dataclass(frozen=True)
class WallMountInputs:
    mass_kg: float
    center_offset_mm: float
    anchor_spacing_x_mm: float
    anchor_spacing_y_mm: float
    axial_thrust_n: float
    motor_reaction_torque_nm: float = 0.0
    lateral_force_x_n: float = 0.0
    lateral_force_y_n: float = 0.0
    aerodynamic_moment_x_nm: float = 0.0
    aerodynamic_moment_y_nm: float = 0.0
    thrust_source: str = "user_supplied_or_measured"

    def __post_init__(self):
        attrs=(
            self.mass_kg,self.center_offset_mm,self.anchor_spacing_x_mm,
            self.anchor_spacing_y_mm,self.axial_thrust_n,
            self.motor_reaction_torque_nm,self.lateral_force_x_n,
            self.lateral_force_y_n,self.aerodynamic_moment_x_nm,
            self.aerodynamic_moment_y_nm,
        )
        if not all(isfinite(x) for x in attrs):
            raise ValueError("All mass, geometry and loads must be finite")
        if not .01<=self.mass_kg<=100:
            raise ValueError("Fan+mount mass must be 0.01 to 100 kg")
        if not 0<=self.center_offset_mm<=1000:
            raise ValueError("Center of mass offset must be 0 to 1000 mm")
        if not 20<=self.anchor_spacing_x_mm<=600 or not 20<=self.anchor_spacing_y_mm<=600:
            raise ValueError("Anchor center spacing must be 20 to 600 mm")
        if max(abs(self.axial_thrust_n),abs(self.lateral_force_x_n),
               abs(self.lateral_force_y_n))>10000:
            raise ValueError("Explicit aerodynamic force exceeds 10 kN bound")
        if max(abs(self.motor_reaction_torque_nm),
               abs(self.aerodynamic_moment_x_nm),
               abs(self.aerodynamic_moment_y_nm))>1000:
            raise ValueError("Applied moments exceed 1000 Nm bound")
        if self.thrust_source not in (
            "user_supplied_or_measured","externally_integrated_cfd",
            "uploaded_patch_csv_pressure_only","unverified_example"
        ):
            raise ValueError("Unrecognized thrust source declaration")


@dataclass(frozen=True)
class AnchorReaction:
    x_mm: float
    y_mm: float
    reaction_x_n: float
    reaction_y_n: float
    reaction_z_n: float
    shear_demand_n: float
    tension_demand_n: float
    compressive_reaction_n: float


@dataclass(frozen=True)
class WallMountResult:
    inputs: WallMountInputs
    anchors: tuple[AnchorReaction, ...]
    applied_force_xyz_n: tuple[float, float, float]
    applied_moment_xyz_nm: tuple[float, float, float]
    force_balance_error_n: float
    moment_balance_error_nm: float
    max_anchor_shear_n: float
    max_anchor_tension_n: float
    numerical_scope: str = (
        "STATIC FOUR-ANCHOR FREE BODY: ideal rigid plate and equal sharing; "
        "anchors may develop both axial signs. Compression is not wall-contact "
        "FEA. Requires independently measured/integrated thrust and true "
        "anchor capacities for installation assessment. Not certified."
    )

    def as_dict(self) -> dict:
        return {
            "inputs":asdict(self.inputs),
            "anchors":[asdict(a) for a in self.anchors],
            "applied_force_xyz_n":list(self.applied_force_xyz_n),
            "applied_moment_xyz_nm":list(self.applied_moment_xyz_nm),
            "force_balance_error_n":self.force_balance_error_n,
            "moment_balance_error_nm":self.moment_balance_error_nm,
            "max_anchor_shear_n":self.max_anchor_shear_n,
            "max_anchor_tension_n":self.max_anchor_tension_n,
            "numerical_scope":self.numerical_scope,
        }


def analyze_wall_mount(spec: WallMountInputs) -> WallMountResult:
    """Balance gravity + user-supplied fan forces/torque over 4 anchors.

    Axes: X horizontal, Y upward, Z outward normal to vertical wall.
    Fan force is applied at (0,0,e); gravity force acts at the same offset.
    The applied torque is about wall-normal +Z. Anchor points lie on Z=0.
    The model assumes equal in-plane translational stiffness and identical
    axial stiffness for the four anchors, including compression. All loads
    are signed; a negative Z reaction is outward bolt *tension demand*.
    """
    if not isinstance(spec,WallMountInputs):
        raise TypeError("Validated WallMountInputs required")
    a=spec.anchor_spacing_x_mm/2000.
    b=spec.anchor_spacing_y_mm/2000.
    e=spec.center_offset_mm/1000.
    positions=np.asarray([
        (-a,-b,0),(a,-b,0),(-a,b,0),(a,b,0)
    ],dtype=float)
    applied=np.asarray([
        spec.lateral_force_x_n,
        spec.lateral_force_y_n-9.80665*spec.mass_kg,
        spec.axial_thrust_n,
    ],dtype=float)
    moment=np.cross(np.array([0.,0.,e]),applied)+np.array([
        spec.aerodynamic_moment_x_nm,
        spec.aerodynamic_moment_y_nm,
        spec.motor_reaction_torque_nm
    ])
    sx2=float((positions[:,0]**2).sum())
    sy2=float((positions[:,1]**2).sum())
    polar=sx2+sy2
    assert sx2>0 and sy2>0 and polar>0
    loads=np.zeros((4,3),dtype=float)
    loads[:,0]=-applied[0]/4.
    loads[:,1]=-applied[1]/4.
    # Opposite in-plane tangential reaction closes applied Z-axis torque.
    loads[:,0]+=moment[2]*positions[:,1]/polar
    loads[:,1]-=moment[2]*positions[:,0]/polar
    # Axial anchor reactions close force and pitch/yaw moments.
    loads[:,2]=-applied[2]/4.-moment[0]*positions[:,1]/sy2+moment[1]*positions[:,0]/sx2
    re_force=loads.sum(axis=0)
    re_moment=np.cross(positions,loads).sum(axis=0)
    ferror=float(np.linalg.norm(re_force+applied))
    merror=float(np.linalg.norm(re_moment+moment))
    scale_f=max(1.,float(np.linalg.norm(applied)))
    scale_m=max(1.,float(np.linalg.norm(moment)))
    if ferror>1e-10*scale_f or merror>1e-10*scale_m:
        raise ArithmeticError("Wall free-body force/moment equilibrium failed")
    table=tuple(
        AnchorReaction(
            x_mm=float(r[0]*1000),y_mm=float(r[1]*1000),
            reaction_x_n=float(f[0]),reaction_y_n=float(f[1]),
            reaction_z_n=float(f[2]),
            shear_demand_n=float(hypot(f[0],f[1])),
            tension_demand_n=float(max(0.,-f[2])),
            compressive_reaction_n=float(max(0.,f[2]))
        )
        for r,f in zip(positions,loads)
    )
    return WallMountResult(
        inputs=spec,anchors=table,
        applied_force_xyz_n=tuple(float(x) for x in applied),
        applied_moment_xyz_nm=tuple(float(x) for x in moment),
        force_balance_error_n=ferror,moment_balance_error_nm=merror,
        max_anchor_shear_n=max(x.shear_demand_n for x in table),
        max_anchor_tension_n=max(x.tension_demand_n for x in table),
    )


def integrate_pressure_traction(
    face_centroids_m: np.ndarray,
    outward_unit_normals: np.ndarray,
    face_areas_m2: np.ndarray,
    kinematic_pressure_m2_s2: np.ndarray,
    *,
    air_density_kg_m3: float,
    reference_point_m: tuple[float,float,float]=(0.,0.,0.),
) -> tuple[np.ndarray,np.ndarray]:
    """Integrate actual patch pressure *if externally supplied*.

    OpenFOAM incompressible p has kinematic units m^2/s^2; multiplying by
    density converts to Pa. Face centroid, normal, area and p must refer
    to the SAME real wetted rotor surface and same physical solver time.
    Arbitrary U/p scatter samples cannot be used for surface tractions.
    """
    x=np.asarray(face_centroids_m,dtype=float)
    n=np.asarray(outward_unit_normals,dtype=float)
    area=np.asarray(face_areas_m2,dtype=float)
    p=np.asarray(kinematic_pressure_m2_s2,dtype=float)
    ref=np.asarray(reference_point_m,dtype=float)
    if (x.ndim!=2 or x.shape[1]!=3 or n.shape!=x.shape or
            area.shape!=(len(x),) or p.shape!=(len(x),) or
            ref.shape!=(3,) or len(x)<1):
        raise ValueError("Face centroid/normals/area/pressure arrays have invalid geometry")
    if not all(np.isfinite(z).all() for z in (x,n,area,p,ref)):
        raise ValueError("Nonfinite CFD patch pressure input")
    if not isfinite(air_density_kg_m3) or not .1<=air_density_kg_m3<=20.:
        raise ValueError("Physical air density must be 0.1 to 20 kg/m^3")
    if np.any(area<=0):
        raise ValueError("Wetted surface face areas must be positive")
    if np.max(np.abs(np.linalg.norm(n,axis=1)-1))>1e-4:
        raise ValueError("CFD patch face normals must be unit vectors")
    traction=-air_density_kg_m3*(p*area)[:,None]*n
    return traction.sum(axis=0),np.cross(x-ref,traction).sum(axis=0)



@dataclass(frozen=True)
class PressurePatchEvidence:
    source_sha256: str
    face_count: int
    solver_time_s: float
    pressure_only: bool
    air_density_kg_m3: float
    force_xyz_n: tuple[float,float,float]
    moment_xyz_nm: tuple[float,float,float]
    limitation: str = (
        "Pressure contribution of user-uploaded face data ONLY. No automatic "
        "source-job linkage or verification of real wetted surface identity, "
        "face normals, viscous shear, pressure reference, or wall FEM."
    )

    def as_dict(self) -> dict:
        return asdict(self)


def parse_openfoam_pressure_patch_csv(
    payload: bytes,*,air_density_kg_m3: float,
    reference_point_m: tuple[float,float,float]=(0.,0.,0.),
) -> PressurePatchEvidence:
    """Convert a user-provided solver surface-pressure export to SI loads.

    The CSV MUST contain one physical solver time with the columns:
    time_s,x_m,y_m,z_m,nx,ny,nz,area_m2,p_kinematic_m2_s2

    User must verify matching source geometry/time and outward surface
    normals. This interface does NOT create pressure data from samples.
    """
    if not isinstance(payload,bytes) or not 20<len(payload)<=4_000_000:
        raise ValueError("Only a 20 B–4 MB UTF-8 pressure patch CSV is allowed")
    try:
        content=payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Pressure patch CSV must use UTF-8") from exc
    required=(
        "time_s","x_m","y_m","z_m","nx","ny","nz",
        "area_m2","p_kinematic_m2_s2",
    )
    reader=csv.DictReader(io.StringIO(content),skipinitialspace=True)
    if reader.fieldnames is None or not set(required).issubset(set(reader.fieldnames)):
        raise ValueError("CSV missing mandatory solver time/face/normal/pressure columns")
    records=[]
    for index,line in enumerate(reader):
        if index>=20000:
            raise ValueError("Pressure patch exceeds 20,000-face interactive cap")
        try:
            records.append(tuple(float(line[field]) for field in required))
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError(f"Invalid pressure face row {index+2}") from exc
    if not records:
        raise ValueError("Pressure patch contains no physical faces")
    values=np.asarray(records,dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Invalid nonfinite patch time/face coordinates or pressure")
    times=values[:,0]
    if not np.allclose(times,times[0],rtol=0,atol=1e-8):
        raise ValueError("All CFD patch faces must be from the SAME solver time")
    force,moment=integrate_pressure_traction(
        values[:,1:4],values[:,4:7],values[:,7],values[:,8],
        air_density_kg_m3=air_density_kg_m3,
        reference_point_m=reference_point_m,
    )
    return PressurePatchEvidence(
        source_sha256=sha256(payload).hexdigest(),
        face_count=len(records),solver_time_s=float(times[0]),
        pressure_only=True,air_density_kg_m3=float(air_density_kg_m3),
        force_xyz_n=tuple(float(x) for x in force),
        moment_xyz_nm=tuple(float(x) for x in moment),
    )
