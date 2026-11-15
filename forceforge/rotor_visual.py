"""Time-explicit kinematic preview of REAL STEP-derived rotor STL triangles.

Geometry motion is mathematically exact rigid rotation about the actual
rotor axis, but contains NO CFD field. Physics visualisation is strictly
from forceforge.rotating_cfd's verified OpenFOAM U/p output and separate.
"""
from __future__ import annotations
import math
import numpy as np


def sample_real_stl_triangles(data:bytes,max_faces:int=1300) -> np.ndarray:
    if not isinstance(data,bytes) or not data.startswith(b"solid fan"):
        raise ValueError("Actual ASCII rotor STL export is required")
    if not 100<=max_faces<=3000 or len(data)>24*1024*1024:
        raise ValueError("STL preview exceeds safe browser complexity")
    coords=[]
    for line in data.splitlines():
        item=line.strip()
        if item.startswith(b"vertex "):
            values=item.split()
            if len(values)!=4:
                raise ValueError("Malformed source STEP-derived STL triangle")
            coords.append([float(v) for v in values[1:]])
    if not coords or len(coords)%3:
        raise ValueError("Actual CAD STL has no valid triangle facets")
    pts=np.asarray(coords,dtype=float).reshape(-1,3,3)
    if not np.all(np.isfinite(pts)):
        raise ValueError("Non-finite CAD STL vertex")
    indices=np.linspace(0,len(pts)-1,min(max_faces,len(pts))).astype(int)
    return pts[indices].copy()


def rotating_triangle_frames(
    triangles:np.ndarray,*,rpm:float,duration_s:float,
    center_m:tuple[float,float,float]=(-3.,2.,2.6),
    count:int=15,
) -> tuple[np.ndarray,np.ndarray]:
    tri=np.asarray(triangles,dtype=float)
    if tri.ndim!=3 or tri.shape[1:]!=(3,3) or not 1<=len(tri)<=3000:
        raise ValueError("Expected bounded actual STL triangle coordinates")
    if not np.isfinite(tri).all():
        raise ValueError("Non-finite physical CAD triangles")
    if not 100<=rpm<=2400 or not .008<=duration_s<=.08 or not 2<=count<=24:
        raise ValueError("Rigid-body motion preview exceeds bounded parameters")
    center=np.asarray(center_m,dtype=float)
    if center.shape!=(3,) or not np.isfinite(center).all():
        raise ValueError("Invalid source rotor placement")
    times=np.linspace(0,duration_s,count)
    result=[]
    flat=tri.reshape(-1,3)-center
    for t in times:
        theta=2*math.pi*(rpm/60)*t
        c,s=math.cos(theta),math.sin(theta)
        rotated=np.stack([
            c*flat[:,0]-s*flat[:,1],
            s*flat[:,0]+c*flat[:,1],
            flat[:,2],
        ],axis=1)+center
        result.append(rotated)
    return times,np.stack(result)
