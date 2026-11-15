"""Physically-fixed 3D Gauss stress probes, independent of FE mesh IDs.

The probe is a fixed fractional band of the original STEP bounding span,
not a changing set of "most stressed elements". The volume-weighted
sample statistics estimate a finite physical response; they do not
regularize singular stresses caused by idealized clamp/point constraints.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import numpy as np


PROBE_START_FRACTION = .05
PROBE_END_FRACTION = .30
PROBE_Q = .90
MIN_GAUSS_SAMPLES = 12
MIN_PROBE_VOLUME_FRACTION = .005


@dataclass(frozen=True)
class StressProbe:
    start_fraction: float
    end_fraction: float
    gauss_samples: int
    volume_fraction_percent: float
    mean_von_mises_mpa: float
    p90_von_mises_mpa: float
    max_sample_von_mises_mpa: float
    peak_location_mm: tuple[float, float, float]
    global_peak_location_mm: tuple[float, float, float]
    global_peak_support_distance_fraction: float
    global_peak_zone: str

    def as_dict(self):
        return asdict(self)


def weighted_percentile(values: np.ndarray, weights: np.ndarray,
                        q: float) -> float:
    values=np.asarray(values,dtype=float)
    weights=np.asarray(weights,dtype=float)
    if (values.ndim!=1 or values.shape!=weights.shape
            or not len(values) or not 0<=q<=1
            or not np.isfinite(values).all()
            or not np.isfinite(weights).all()
            or np.any(weights<=0)):
        raise ValueError("Weighted stress percentile requires positive finite weights")
    order=np.argsort(values)
    v=values[order]
    w=weights[order]
    # Weighted empirical CDF, intentionally no interpolation across
    # independently sampled elements. Defined reproducibly for this mesh.
    idx=int(np.searchsorted(np.cumsum(w),q*float(w.sum()),side="left"))
    return float(v[min(idx,len(v)-1)])


def probe_stress(result, *, start: float=PROBE_START_FRACTION,
                 end: float=PROBE_END_FRACTION) -> StressProbe:
    if not 0 <= start < end <= 1:
        raise ValueError("Invalid physical probe band")
    loc=np.asarray(result.gauss_points_m,dtype=float)
    vm=np.asarray(result.gauss_von_mises_pa,dtype=float)
    weights=np.asarray(result.gauss_weights_m3,dtype=float)
    if loc.ndim!=2 or loc.shape[1]!=3 or len(loc)!=len(vm) or len(loc)!=len(weights):
        raise ValueError("FE result has no consistent 3D Gauss stress sample arrays")
    if len(loc)!=4*result.mesh.num_tets:
        raise ValueError("FE stress quadrature samples do not match tetra count")
    if not np.isfinite(loc).all() or not np.isfinite(vm).all():
        raise ValueError("Non-finite stress or sample position")
    if np.any(weights<=0) or not np.isfinite(weights).all():
        raise ValueError("Non-positive Gauss integration volume")
    total=float(weights.sum())
    if not np.isclose(total,result.mesh.mesh_volume_m3,rtol=1e-7,atol=1e-12):
        raise ValueError("Gauss sample weights do not integrate to the actual mesh volume")

    axis=result.load.boundary_axis
    z0,z1=result.mesh.bbox_m[:,axis]
    length=float(z1-z0)
    if length<=0:
        raise ValueError("Invalid specimen span in the selected support direction")
    fraction=(loc[:,axis]-z0)/length
    mask=(fraction>=start)&(fraction<=end)
    n=int(mask.sum())
    selected_weights=weights[mask]
    vf=float(selected_weights.sum()/total) if n else 0.
    if n<MIN_GAUSS_SAMPLES or vf<MIN_PROBE_VOLUME_FRACTION:
        raise ValueError(
            "Fixed physical stress probe does not contain sufficient "
            f"Gauss samples/volume (samples={n}, volume fraction={vf:.2%}). "
            "No local-stress stability claim can be made."
        )
    sampled_vm=vm[mask]
    mean=float(np.dot(sampled_vm,selected_weights)/selected_weights.sum())/1e6
    p90=weighted_percentile(sampled_vm,selected_weights,PROBE_Q)/1e6
    peak_local=int(np.argmax(sampled_vm))
    peak_location=loc[mask][peak_local]
    global_peak=np.asarray(result.sampled_peak_location_m,dtype=float)
    if global_peak.shape!=(3,):
        raise ValueError("Missing global stress hotspot physical coordinate")
    peak_fraction=float((global_peak[axis]-z0)/length)
    if peak_fraction<=.05:
        category="NEAR_IDEALIZED_FIXED_FACE"
    elif peak_fraction>=.95:
        category="NEAR_APPLIED_TRACTION_FACE"
    else:
        category="INTERIOR_OR_OTHER_CAD_FEATURE"
    return StressProbe(
        start_fraction=float(start),end_fraction=float(end),
        gauss_samples=n,volume_fraction_percent=100*vf,
        mean_von_mises_mpa=mean,
        p90_von_mises_mpa=p90,
        max_sample_von_mises_mpa=float(sampled_vm.max())/1e6,
        peak_location_mm=tuple(float(v*1000) for v in peak_location),
        global_peak_location_mm=tuple(float(v*1000) for v in global_peak),
        global_peak_support_distance_fraction=peak_fraction,
        global_peak_zone=category
    )


@dataclass(frozen=True)
class FixedHotspotRegion:
    """Finite physical sphere around one candidate stress hotspot."""
    center_mm: tuple[float,float,float]
    radius_mm: float
    gauss_samples: int
    sampled_volume_percent: float
    weighted_mean_mpa: float
    weighted_p90_mpa: float
    sampled_peak_mpa: float

    def as_dict(self):
        return asdict(self)


def probe_physical_hotspot(result, center_m, *, radius_mm=7.0) -> FixedHotspotRegion:
    """Stress within a physically fixed 3D ball, not selected mesh elements.

    The same center, radius, source STEP and load must be used across all FE
    meshes being compared. Reject insufficient quadrature support instead
    of extrapolating a fabricated stress at an unsampled point.
    """
    center=np.asarray(center_m,dtype=float)
    loc=np.asarray(result.gauss_points_m,dtype=float)
    vm=np.asarray(result.gauss_von_mises_pa,dtype=float)
    volume=np.asarray(result.gauss_weights_m3,dtype=float)
    if center.shape!=(3,) or not np.isfinite(center).all():
        raise ValueError("Invalid physical hotspot XYZ center")
    if not 3.<=radius_mm<=15.:
        raise ValueError("Hotspot probe radius must be within 3–15 mm")
    if (loc.ndim!=2 or loc.shape[1]!=3 or len(loc)!=len(vm)
            or len(loc)!=len(volume)
            or not np.isfinite(loc).all() or
            not np.isfinite(vm).all() or
            not np.isfinite(volume).all() or np.any(volume<=0)):
        raise ValueError("Corrupt 3D Gauss stress quadrature samples")
    distance=np.linalg.norm(loc-center[None,:],axis=1)
    mask=distance<=radius_mm*.001
    count=int(mask.sum())
    total=float(volume.sum())
    inside=float(volume[mask].sum()) if count else 0.
    if count<MIN_GAUSS_SAMPLES or inside/total<MIN_PROBE_VOLUME_FRACTION:
        raise ValueError(
            "Physical 3D hotspot probe is undersampled by this mesh "
            f"(n={count}, volume={inside/total:.2%}); "
            "cannot compare different mesh local peaks reliably."
        )
    a=vm[mask]
    w=volume[mask]
    return FixedHotspotRegion(
        center_mm=tuple(float(x*1000) for x in center),
        radius_mm=float(radius_mm),
        gauss_samples=count,
        sampled_volume_percent=100*inside/total,
        weighted_mean_mpa=float(np.dot(a,w)/inside)/1e6,
        weighted_p90_mpa=weighted_percentile(a,w,.90)/1e6,
        sampled_peak_mpa=float(a.max())/1e6,
    )
