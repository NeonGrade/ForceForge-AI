# ForceForge X — v0.2: Real 3D Fan Air-Domain Mesh, CFD Still Blocked

This extends **PR #16 / feature/stress-local-validation-v11** without
removing or modifying the previously verified L-bracket tetra10 FEA,
dual-hotspot, Design Copilot, or original experimental modes.

## What actually runs

**First action:** Create the registered conceptual wall-fan STEP from
ordinary-language parameters, only after explicit approval of inferred
blade geometry. The CAD artifact is a real OpenCASCADE multi-body STEP
with its SHA-256.

**Second action:** Press **Build real 3D Gmsh fluid mesh + tagged boundary
regions**. ForceForge launches a **separate, bounded native worker**,
reimports the exact STEP file for provenance, and makes an *independent*
simplified 3D AIR domain. It is a **two-zone idealized actuator-region
preprocessor**. It does **not** subtract rotor blades or the wall plate.
This restriction must remain visible during the live demo.

The exported MSH 2.2 ASCII file contains **genuine 4-node tetrahedral
volume elements** with a conformal internal rotor-source region and
proper Gmsh **Physical Groups**:

| Dim | Physical tag | Actual entity | Interpretation |
|---|---:|---|---|
| 2 | 101 | upstream_open | conceptual upstream open face |
| 2 | 102 | downstream_open | conceptual downstream open face |
| 2 | 103 | lateral_farfield | four farfield box faces |
| 2 | 104 | rotor_interface | conforming rotor-zone / ambient-air interface |
| 3 | 201 | rotor_source_zone | cylindrical *air* actuator region, no blades |
| 3 | 202 | ambient_air_zone | surrounding box of *air* |

Dimensions for an explicitly provided rotor diameter **D** (all in
millimeters):
- Box x/y from -1.5 D to +1.5 D.
- Upstream extent z = -1.0 D, downstream z = +2.5 D.
- Cylindrical rotor-volume radius = 0.5 D and axial thickness = 0.3 D.
- Gmsh tetra target edge ≈ max(45 mm, D/2.8). Bounded nodes,
  volume conservation and surface-face groups are checked.
- **The box represents an open-domain abstract fan study, not the wall
  behind a wall-mounted fan.** This should not be misconstrued as a wall
  or mounting-plate CFD flow simulation.

All native operations are in an isolated Python child process with a
strict timeout. A mesh failure produces an explicit error but leaves
the previous CAD result intact. The Streamlit page **does not**
automatically remesh on routine reruns, switching tabs or download.
It displays an ACTUAL meshed rotor-zone interface (one color, no CFD
velocity stress legend), with an idealized air-box wireframe.

### Numerical evidence available for download
- Exact source STEP SHA-256 and fluid mesh SHA-256
- True 3D tetrahedron and node counts
- Actual CAD vs tetrahedral-volume conservation
- Named boundary patch triangle counts and physical IDs
- Gmsh MSH 2.2 (independent import is CI-tested)
- JSON with the **unsolved** Navier–Stokes status

## What has NOT been solved

There is **no velocity field, air-flow rate, pressure distribution,
temperature, fan aerodynamic thrust, wall/anchor stress or certified
Navier–Stokes CFD solution**. These values MUST NOT be inferred from
geometry, RPM or this mesh.

To activate a real CFD solver in a later step:
1. Specify a physically meaningful fan pressure–flow curve, actuator
   forcing distribution, or resolved blade/rotating-zone method;
2. Establish a relevant wall-aware fluid domain, actual inlet/outlet
   boundary conditions, fluid material data and turbulence treatment;
3. Import the tagged mesh to an explicitly installed, documented solver
   (e.g., OpenFOAM gmshToFoam), correctly handle internal face zones;
4. Run an actual Navier–Stokes calculation, check solver residuals,
   conservation and mesh sensitivity before showing pressure/velocity;
5. Transfer verified loads to a validated joint/anchor/contact FEA if
   mounting stress is needed. Current tetra10 solver cannot do that.

A Gmsh Physical Group alone is **not** an OpenFOAM-ready boundary
condition, and a mesh alone is **not** a CFD result.

## Reproduce

\`\`\`bash
git switch feature/stress-local-validation-v11
git pull --ff-only origin feature/stress-local-validation-v11
source .venv/bin/activate
python -m pip install -r requirements.txt 'gmsh>=4.12,<5'
python -m streamlit run app.py --server.fileWatcherType none
\`\`\`

In the **Natural Language Engineering** page, input:

> 帮我设计直径30厘米、1500 RPM的壁挂风扇，研究气流和墙体受力。

Interpret the requirements, confirm labeled concept assumptions, create
the STEP, then click **Build real 3D Gmsh fluid mesh + tagged boundary
regions**. Export the mesh and JSON. Wall stress and actual CFD remain
**BLOCKED** in the task graph.

CI:

\`\`\`bash
python -m pytest -q tests/test_engineering_pipeline.py
python -m pytest -q tests/test_real_fluid_domain.py
\`\`\`

The first tests do not require Gmsh; the second uses a real Gmsh Python
wheel plus native libraries and reimports the written MSH. The
\`natural-language-engineering.yml\` workflow includes Linux and macOS
native validation. Repeat the manual Mac browser run before the demo.
