"""Attempt actual NIST bridge STEP tetrahedralization and optional 3D FE.

Never claim success if CAD thin-wall features fail meshing or exceed resource
caps. The load is illustrative only, NOT NIST residual-strain validation.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
from forceforge.step_mesh import (
    NIST_BRIDGE_URL, NIST_BRIDGE_HASH_URL, mesh_step_bytes
)
from scripts.fetch_nist_step import fetch_bytes, parse_sha

def main():
    raw=fetch_bytes(NIST_BRIDGE_URL)
    checksum=sha256(raw).hexdigest()
    report={'origin':'NIST AMB2022-01 original STEP',
            'doi':'10.18434/mds2-2607',
            'sha256':checksum,'bytes':len(raw),
            'static_load_scope':'User-defined example; no corresponding physical static test',
            'trial_meshes':[]}
    try:
        digest=parse_sha(fetch_bytes(NIST_BRIDGE_HASH_URL))
        report['publisher_hash_matches']=(digest==checksum)
        if digest!=checksum:
            raise ValueError('Official NIST SHA-256 mismatch')
    except Exception as exc:
        if 'mismatch' in str(exc):
            raise
        report['publisher_checksum_note']='Unable to access/parse publisher checksum: '+str(exc)
    success=None
    for size in (6.,10.,15.):
        try:
            m=mesh_step_bytes(raw,source_label='NIST original AMB2022-01 STEP',
                              mesh_size_mm=size,max_tets=10000)
            record={
                'mesh_size_mm':size,'status':'ACCEPTED',
                'tet4_count':m.num_tets,
                'cad_volume_mm3':m.cad_volume_m3*1e9,
                'mesh_volume_mm3':m.mesh_volume_m3*1e9,
                'volume_error_percent':m.relative_volume_difference*100,
                'min_shape_quality':m.min_shape_quality}
            success=m
            report['trial_meshes'].append(record)
            break
        except Exception as exc:
            report['trial_meshes'].append({
                'mesh_size_mm':size,'status':'REJECTED',
                'type':type(exc).__name__,'reason':str(exc)})
    if success is not None and success.num_tets<=3000:
        try:
            from forceforge.cad_solid import CadLoad,solve_cad_mesh
            result=solve_cad_mesh(success,CadLoad(force_n=50,force_axis=0,
                                                  force_sign=1,boundary_axis=2))
            report['illustrative_static_fem']={
                'status':'COMPUTED WITH ASSUMED CONDITIONS',
                'load_n':50,'tip_mm':result.tip_mm,
                'sampled_von_mises_mpa':result.peak_von_mises_mpa,
                'global_reaction_error':result.relative_reaction_residual,
                'mesh_nodes':len(result.nodes_m)}
        except Exception as exc:
            report['illustrative_static_fem']={
                'status':'FAILED / UNSUPPORTED','reason':str(exc)}
    elif success is not None:
        report['illustrative_static_fem']={
            'status':'NOT RUN',
            'reason':'Real source mesh has too many elements for rapid optional CI solve'}
    else:
        report['illustrative_static_fem']={
            'status':'NOT RUN: no mesh passed volume/cap checks'}
    Path('nist_original_real_mesh_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
