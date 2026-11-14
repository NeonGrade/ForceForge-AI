"""Source-traceable STEP -> 3D tetrahedral mesh and parametric bracket BRep.

Gmsh is optional. Curved STEP faces are approximated with straight-sided
linear tets before being enriched to quadratic FE displacement elements.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from contextlib import contextmanager
from threading import RLock
import tempfile
import numpy as np

# The Gmsh Python API changes process-wide state; serialize CAD/mesh calls
# across concurrent Streamlit sessions. Calling initialize() with the default
# interruptible=True changes SIGINT handlers, which Python forbids in
# Streamlit's non-main ScriptRunner thread (especially on macOS/Python 3.13).
_GMSH_LOCK = RLock()

@contextmanager
def _gmsh_session(gmsh):
    with _GMSH_LOCK:
        gmsh.initialize(interruptible=False)
        try:
            yield gmsh
        finally:
            gmsh.finalize()


NIST_BRIDGE_URL = 'https://data.nist.gov/od/ds/ark:/88434/mds2-2607/CAD_Geometry/AMB2022-01-AMMT-PartCAD.STEP'
NIST_BRIDGE_HASH_URL = NIST_BRIDGE_URL + '.sha256'
# Exact publicly downloaded file verified by independent GitHub runner (2026-11-14).
NIST_PINNED_SHA256 = '623ee615d015bb231accdff3594592c3c7c563d98c463bd21680da2c0005d055'
NIST_DATASET_DOI = '10.18434/mds2-2607'
MAX_CAD_BYTES=32*1024*1024

@dataclass
class CadMesh:
    nodes_m: np.ndarray
    tets4: np.ndarray
    source_sha256: str
    source_label: str
    mesh_size_mm: float
    cad_volume_m3: float
    mesh_volume_m3: float
    bbox_m: np.ndarray
    relative_volume_difference: float
    min_shape_quality: float
    @property
    def num_tets(self):
        return len(self.tets4)


def _validate_step(data: bytes):
    if not 100 < len(data) <= MAX_CAD_BYTES:
        raise ValueError('STEP must be between 100 bytes and 32 MiB')
    if b'ISO-10303-21' not in data[:1000].upper():
        raise ValueError('Not an ISO-10303-21 STEP Part 21 file')


def _extract_tets(gmsh, scale, file_hash, label, size_mm, volume_native, max_tets):
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    tags=np.asarray(node_tags,dtype=np.int64)
    xyz=np.asarray(coords,dtype=float).reshape(-1,3)
    order=np.argsort(tags)
    sorted_tags=tags[order]
    element_types, _, arrays=gmsh.model.mesh.getElements(3)
    cells=[]
    for typ, raw in zip(element_types,arrays):
        if int(typ)!=4:
            raise ValueError('Expected 4-node straight tetrahedra from Gmsh')
        raw=np.asarray(raw,dtype=np.int64).reshape(-1,4)
        pos=np.searchsorted(sorted_tags,raw)
        if np.any(pos>=len(sorted_tags)) or np.any(sorted_tags[pos]!=raw):
            raise ValueError('Invalid Gmsh mesh node labels')
        cells.append(order[pos])
    if not cells:
        raise ValueError('No solid volume tetrahedra produced')
    tets=np.vstack(cells)
    if len(tets)>max_tets:
        raise ValueError(f'Generated {len(tets)} tetrahedra, above interactive cap {max_tets}; coarsen CAD mesh or isolate a smaller solid. No elements were silently removed.')
    points=xyz*scale
    corners=points[tets]
    jac=np.stack((corners[:,1]-corners[:,0],corners[:,2]-corners[:,0],corners[:,3]-corners[:,0]),axis=-1)
    volumes=np.abs(np.linalg.det(jac))/6
    if np.any(volumes<=1e-19):
        raise ValueError('Degenerate tetrahedral volume in CAD mesh')
    lengths=[np.linalg.norm(corners[:,j]-corners[:,i],axis=1) for i,j in ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))]
    longest=np.maximum.reduce(lengths)
    quality=(6*volumes)/np.maximum(longest**3,1e-30)
    mesh_vol=float(np.sum(volumes))
    cad_vol=volume_native*scale**3
    delta=abs(mesh_vol-cad_vol)/cad_vol
    if delta>.20:
        raise ValueError(f'CAD solid volume differs from tetrahedral mesh volume by {delta:.1%}, above 20% topology/mesh guard')
    return CadMesh(points,tets,file_hash,label,float(size_mm),float(cad_vol),mesh_vol,
                   np.vstack((points.min(axis=0),points.max(axis=0))),float(delta),float(quality.min()))


def mesh_step_bytes(data:bytes, *, source_label='STEP',mesh_size_mm=5.,unit='mm',max_tets=5000):
    _validate_step(data)
    if unit not in ('mm','m'):
        raise ValueError('Units must be mm or m')
    if not .2<=mesh_size_mm<=30:
        raise ValueError('Mesh size must be between 0.2 and 30 mm')
    try:
        import gmsh
    except ImportError as exc:
        raise RuntimeError('Install optional Gmsh: python -m pip install gmsh') from exc
    with tempfile.TemporaryDirectory(prefix='ffstep_') as folder:
        src=Path(folder)/'source.step'
        src.write_bytes(data)
        with _gmsh_session(gmsh):
            gmsh.option.setNumber('General.Terminal',0)
            gmsh.model.add('STEP imported CAD')
            gmsh.model.occ.importShapes(str(src))
            gmsh.model.occ.synchronize()
            volumes=gmsh.model.getEntities(3)
            if len(volumes)!=1:
                raise ValueError(f'STEP has {len(volumes)} separate solids; multi-body contact is not supported, no automatic gluing')
            volume_native=float(gmsh.model.occ.getMass(3,volumes[0][1]))
            scale=.001 if unit=='mm' else 1.
            size_native=mesh_size_mm if unit=='mm' else mesh_size_mm/1000
            for key,value in [('Mesh.MeshSizeMin',size_native),('Mesh.MeshSizeMax',size_native),
                              ('Mesh.MeshSizeFromPoints',0),('Mesh.MeshSizeFromCurvature',0),
                              ('Mesh.MeshSizeExtendFromBoundary',0)]:
                gmsh.option.setNumber(key,value)
            gmsh.model.mesh.generate(3)
            return _extract_tets(gmsh,scale,sha256(data).hexdigest(),source_label,
                                 mesh_size_mm,volume_native,max_tets)


def generated_bracket_step(*,web_mm=8.):
    """New editable L bracket with 3 drilled holes; NOT a measured NIST specimen."""
    if web_mm not in (8.,10.,12.,14.):
        raise ValueError('Bracket web thickness must be 8, 10, 12 or 14 mm')
    try:
        import gmsh
    except ImportError as exc:
        raise RuntimeError('Install optional Gmsh first') from exc
    with tempfile.TemporaryDirectory(prefix='ffbracket_') as folder:
        path=Path(folder)/'bracket.step'
        with _gmsh_session(gmsh):
            gmsh.option.setNumber('General.Terminal',0)
            gmsh.model.add('Parametric demonstration bracket')
            a=gmsh.model.occ.addBox(0,0,0,75,40,8)
            b=gmsh.model.occ.addBox(0,0,8,web_mm,40,50)
            fused,_=gmsh.model.occ.fuse([(3,a)],[(3,b)])
            cutters=[gmsh.model.occ.addCylinder(53,y,-1,0,0,10,3.) for y in (10,30)]
            cutters.append(gmsh.model.occ.addCylinder(-1,20,43,web_mm+2,0,0,4.))
            gmsh.model.occ.cut(fused,[(3,h) for h in cutters])
            gmsh.model.occ.synchronize()
            if len(gmsh.model.getEntities(3))!=1:
                raise ValueError('Bracket is not one watertight solid')
            gmsh.write(str(path))
            return path.read_bytes()
