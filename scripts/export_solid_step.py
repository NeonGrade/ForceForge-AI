"""Optional STEP/STL CAD export matching the true 3D FE mesh geometry.

Requires the external CadQuery package; not required by the base FEA app:
    python -m pip install cadquery
    python scripts/export_solid_step.py --thickness 12 --out ./cad-out

Geometry is an original *computational benchmark*: a straight 120mm long
30mm wide constant-thickness prismatic cantilever. The 3D FEA mesher uses
the same dimensions but currently does NOT import the STEP BRep.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--thickness",type=float,default=12.0,
                   help="Section thickness in mm, e.g. 12 or 13")
    p.add_argument("--out",type=Path,default=Path("./cad-out"))
    args=p.parse_args()
    if not 8<=args.thickness<=20:
        raise SystemExit("Supported thickness range 8–20mm")
    try:
        import cadquery as cq
    except ImportError as exc:
        raise SystemExit("CAD export is optional: install CadQuery first") from exc
    args.out.mkdir(parents=True,exist_ok=True)
    solid=cq.Workplane("XY").box(30,args.thickness,120,
                                 centered=(True,True,False))
    label=f"ForceForge_Solid_120x30x{args.thickness:g}mm"
    step=args.out/(label+".step")
    stl=args.out/(label+".stl")
    cq.exporters.export(solid,str(step))
    cq.exporters.export(solid,str(stl),tolerance=.02)
    body=cq.importers.importStep(str(step)).val()
    bbox=body.BoundingBox()
    assert abs(bbox.zlen-120)<1e-5
    assert abs(bbox.xlen-30)<1e-5
    assert abs(bbox.ylen-args.thickness)<1e-5
    print("STEP:",step,"| STL:",stl)
    print("Volume (mm^3):",body.Volume())


if __name__=="__main__":
    main()
