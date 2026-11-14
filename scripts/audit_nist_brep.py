"""CI verification of the genuine NIST AMB2022-01 downloaded STEP.

This job has its own status; a generative L-bracket cannot substitute for
verifying access to the actual NIST source geometry.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import gmsh
from scripts.fetch_nist_step import fetch_bytes
from forceforge.step_mesh import NIST_BRIDGE_URL, _validate_step

def main():
    source=fetch_bytes(NIST_BRIDGE_URL)
    _validate_step(source)
    with tempfile.TemporaryDirectory() as folder:
        step=Path(folder)/'NIST-original.step'
        step.write_bytes(source)
        gmsh.initialize()
        try:
            gmsh.option.setNumber('General.Terminal',0)
            gmsh.model.add('NIST published real bridge geometry')
            gmsh.model.occ.importShapes(str(step))
            gmsh.model.occ.synchronize()
            solids=gmsh.model.getEntities(3)
            if not solids:
                raise ValueError('NIST STEP import produced no watertight CAD solids')
            masses=[float(gmsh.model.occ.getMass(3,s[1])) for s in solids]
            bbox=gmsh.model.getBoundingBox(-1,-1)
            report={
                'source':'Official NIST PDR original STEP',
                'doi':'10.18434/mds2-2607',
                'url':NIST_BRIDGE_URL,'sha256':sha256(source).hexdigest(),
                'bytes':len(source),'solid_count':len(solids),
                'per_solid_cad_volume_mm3':masses,
                'bbox_native':list(bbox),
                'mesh_status':'BRep import only; complex thin wall tetra meshing still pending',
                'measured_static_loading':'None assumed'
            }
            print(json.dumps(report,indent=2))
            Path('nist_cad_import_audit.json').write_text(json.dumps(report,indent=2))
        finally:
            gmsh.finalize()

if __name__=='__main__':
    main()
